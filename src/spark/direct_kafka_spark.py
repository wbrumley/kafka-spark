#!/usr/bin/env python3
"""
Direct Kafka to Spark processor that directly displays results
This bypasses the separate dashboard process for troubleshooting
"""
import os
import sys
import time
import logging
import argparse
from datetime import datetime

# Add the current directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "direct_kafka_spark.log"))
    ]
)
logger = logging.getLogger(__name__)

# Import necessary dependencies
try:
    from pyspark.sql import SparkSession
    from pyspark.sql.functions import col, from_json, to_timestamp, expr, current_timestamp
    from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType
    from tabulate import tabulate
    from termcolor import colored
    
    # Import settings with fallback values in case import fails
    try:
        from src.config.settings import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC
    except ImportError:
        logger.warning("Could not import settings, using default values")
        KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
        KAFKA_TOPIC = "dev_security_logs"
    
    logger.info("Successfully imported dependencies")
except ImportError as e:
    logger.error(f"Failed to import dependencies: {e}")
    sys.exit(1)

def create_spark_session():
    """Create a Spark session with Kafka packages"""
    logger.info("Creating Spark session")
    
    # Set Java options for compatibility with newer Java versions
    os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1 --conf spark.driver.extraJavaOptions="-Dio.netty.tryReflectionSetAccessible=true" --conf spark.executor.extraJavaOptions="-Dio.netty.tryReflectionSetAccessible=true" pyspark-shell'
    
    return (SparkSession.builder
            .appName("DirectKafkaSpark")
            .master("local[*]")
            .config("spark.sql.shuffle.partitions", "2")
            .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1")
            .config("spark.driver.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
            .config("spark.executor.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
            .getOrCreate())

def process_kafka_events(start_from_beginning=True):
    """Process Kafka events directly with Spark
    
    Args:
        start_from_beginning: If True, read from the beginning of the topic
    """
    # Create Spark session
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        # Define schema for security events
        schema = StructType([
            StructField("event_id", StringType(), True),
            StructField("timestamp", StringType(), True),
            StructField("event_type", StringType(), True),
            StructField("user_id", StringType(), True),
            StructField("user_type", StringType(), True),
            StructField("ip_address", StringType(), True),
            StructField("severity", StringType(), True),
            StructField("message", StringType(), True),
            StructField("source_system", StringType(), True),
            # Add more fields as needed
        ])
        
        # Determine starting offset based on argument
        starting_offsets = "earliest" if start_from_beginning else "latest"
        
        # Print Kafka configuration
        logger.info(f"Kafka Bootstrap Servers: {KAFKA_BOOTSTRAP_SERVERS}")
        logger.info(f"Kafka Topic: {KAFKA_TOPIC}")
        logger.info(f"Starting offsets: {starting_offsets}")
        
        # Create streaming DataFrame from Kafka
        df = (spark
              .readStream
              .format("kafka")
              .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
              .option("subscribe", KAFKA_TOPIC)
              .option("startingOffsets", starting_offsets)
              .load())
        
        # Parse JSON values
        parsed = (df
                 .selectExpr("CAST(value AS STRING) as json")
                 .select(from_json("json", schema).alias("data"))
                 .select("data.*"))
        
        # Print schema
        logger.info("DataFrame schema:")
        parsed.printSchema()
        
        # Define a function to process each batch
        def process_batch(batch_df, batch_id):
            count = batch_df.count()
            logger.info(f"Batch {batch_id}: {count} records")
            
            if count > 0:
                # Show batch data
                print("\n" + "="*80)
                print(colored(f"SECURITY EVENTS BATCH {batch_id}", "cyan", attrs=["bold"]))
                print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"Record count: {count}")
                print("="*80)
                
                # Show data as a table
                pandas_df = batch_df.toPandas()
                print(tabulate(pandas_df, headers="keys", tablefmt="psql", showindex=False))
        
        # Start streaming query with foreachBatch
        query = (parsed
                .writeStream
                .foreachBatch(process_batch)
                .outputMode("append")
                .start())
        
        # Keep the application running
        logger.info("Streaming query started. Press Ctrl+C to stop.")
        query.awaitTermination()
        
    except KeyboardInterrupt:
        logger.info("Streaming query terminated by user")
    except Exception as e:
        logger.error(f"Error in streaming query: {e}", exc_info=True)
    finally:
        logger.info("Stopping Spark session")
        spark.stop()

if __name__ == "__main__":
    # Add command line argument parsing
    parser = argparse.ArgumentParser(description='Direct Kafka-Spark processor')
    parser.add_argument('--from-beginning', action='store_true', default=True,
                        help='Start reading from the beginning of the topic (default: True)')
    parser.add_argument('--from-latest', action='store_true',
                        help='Start reading only new messages (overrides --from-beginning)')
    
    args = parser.parse_args()
    
    # Determine starting point (from-latest overrides from-beginning)
    start_from_beginning = args.from_beginning
    if args.from_latest:
        start_from_beginning = False
    
    # Run the processor with the specified starting point
    process_kafka_events(start_from_beginning) 
 