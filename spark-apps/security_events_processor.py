from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
import os
import json
import time
from datetime import datetime

# Get configurations from environment variables
kafka_bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
kafka_topic = os.environ.get("KAFKA_TOPIC", "security-events")
checkpoint_location = "/opt/spark/data/checkpoints"

# Define schema for security events
schema = StructType([
    StructField("event_id", StringType(), True),
    StructField("correlation_id", StringType(), True),
    StructField("timestamp", TimestampType(), True),
    StructField("event_type", StringType(), True),
    StructField("severity", StringType(), True),
    StructField("user_id", StringType(), True),
    StructField("user_type", StringType(), True),
    StructField("ip_address", StringType(), True),
    StructField("source_system", StringType(), True),
    StructField("target_system", StringType(), True),
    StructField("session_id", StringType(), True),
    StructField("status_code", IntegerType(), True),
    StructField("message", StringType(), True),
    StructField("geo_location", StructType([
        StructField("city", StringType(), True),
        StructField("country", StringType(), True),
        StructField("latitude", DoubleType(), True),
        StructField("longitude", DoubleType(), True)
    ]), True),
    StructField("tags", ArrayType(StringType()), True),
    StructField("additional_info", MapType(StringType(), StringType()), True),
])

def process_batch(df, epoch_id):
    """Process each batch of data"""
    # Count the number of records
    count = df.count()
    print(f"Batch {epoch_id}: Received {count} security events")
    
    if count > 0:
        # Display example records
        print("Sample events:")
        df.show(5, truncate=False)
        
        # Analyze event types
        print("Event Types Distribution:")
        df.groupBy("event_type").count().orderBy(desc("count")).show(10)
        
        # Analyze severity
        print("Severity Distribution:")
        df.groupBy("severity").count().orderBy(desc("count")).show()
        
        # Analyze suspicious activities
        print("Suspicious Activities (HIGH and CRITICAL severity):")
        df.filter(col("severity").isin(["HIGH", "CRITICAL"])) \
          .select("event_type", "user_id", "ip_address", "message", "timestamp") \
          .orderBy(desc("timestamp")) \
          .show(10, truncate=False)
        
        # Save suspicious events to file
        high_severity_events = df.filter(col("severity").isin(["HIGH", "CRITICAL"]))
        if high_severity_events.count() > 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            high_severity_events.write.mode("append").parquet(f"/opt/spark/data/high_severity_{timestamp}")
        
        # Analyze geo locations
        print("Geo Location Analysis:")
        df.filter(col("geo_location").isNotNull()) \
          .select("geo_location.country") \
          .groupBy("country") \
          .count() \
          .orderBy(desc("count")) \
          .show(10)
        
        # Log processing time
        print(f"Batch {epoch_id} processed at {datetime.now().isoformat()}")

def main():
    """Main function to run the Spark Streaming application"""
    print("Starting Security Events Spark Streaming Application")
    
    # Create Spark session
    spark = SparkSession.builder \
        .appName("SecurityEventsProcessor") \
        .master(os.environ.get("SPARK_MASTER", "spark://spark-master:7077")) \
        .config("spark.sql.shuffle.partitions", "2") \
        .config("spark.streaming.stopGracefullyOnShutdown", "true") \
        .getOrCreate()
    
    # Set log level
    spark.sparkContext.setLogLevel("WARN")
    
    # Read from Kafka
    df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", kafka_bootstrap_servers) \
        .option("subscribe", kafka_topic) \
        .option("startingOffsets", "latest") \
        .load()
    
    # Parse the value column from Kafka into the structured schema
    parsed_df = df.select(
        col("timestamp").cast("timestamp").alias("receive_time"),
        from_json(col("value").cast("string"), schema).alias("data")
    ).select(
        col("receive_time"),
        col("data.*")
    )
    
    # Process the data in streaming mode
    query = parsed_df \
        .writeStream \
        .foreachBatch(process_batch) \
        .outputMode("update") \
        .option("checkpointLocation", checkpoint_location) \
        .trigger(processingTime="10 seconds") \
        .start()
    
    # Wait for the query to terminate
    query.awaitTermination()

if __name__ == "__main__":
    main() 