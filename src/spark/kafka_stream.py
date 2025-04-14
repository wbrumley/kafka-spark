import os
import logging
import json
from typing import Dict, Any, Optional
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    from_json, col, window, count, expr, when, lit, 
    current_timestamp, to_timestamp, max as spark_max,
    min as spark_min, avg, explode, split
)
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, 
    TimestampType, ArrayType, MapType, BooleanType, FloatType
)

from src.config.settings import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "spark_stream.log"))
    ]
)
logger = logging.getLogger(__name__)

# Define schema for security events
security_event_schema = StructType([
    StructField("event_id", StringType(), False),
    StructField("timestamp", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("user_id", StringType(), False),
    StructField("user_type", StringType(), True),
    StructField("ip_address", StringType(), False),
    StructField("geo_location", StructType([
        StructField("country", StringType(), False),
        StructField("city", StringType(), True),
        StructField("latitude", FloatType(), True),
        StructField("longitude", FloatType(), True)
    ]), True),
    StructField("user_agent", StringType(), False),
    StructField("status_code", IntegerType(), False),
    StructField("message", StringType(), False),
    StructField("correlation_id", StringType(), True),
    StructField("session_id", StringType(), True),
    StructField("severity", StringType(), True),
    StructField("source_system", StringType(), True),
    StructField("target_system", StringType(), True),
    StructField("tags", ArrayType(StringType()), True),
    StructField("additional_info", MapType(StringType(), StringType()), True)
])

def create_kafka_stream(spark: SparkSession, 
                        topic: str = KAFKA_TOPIC,
                        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS) -> DataFrame:
    """
    Create a Spark streaming DataFrame from Kafka topic
    
    Args:
        spark: SparkSession
        topic: Kafka topic name
        bootstrap_servers: Kafka bootstrap servers
        
    Returns:
        Structured streaming DataFrame with parsed security events
    """
    logger.info(f"Creating Kafka stream from topic: {topic}")
    
    # Read from Kafka
    kafka_df = (spark
                .readStream
                .format("kafka")
                .option("kafka.bootstrap.servers", bootstrap_servers)
                .option("subscribe", topic)
                .option("startingOffsets", "latest")
                .option("failOnDataLoss", "false")
                .option("maxOffsetsPerTrigger", 10000)  # Control batch size
                .load())
    
    # Parse JSON values from Kafka
    parsed_df = (kafka_df
                .select(
                    col("key").cast("string").alias("user_id_key"),
                    col("value").cast("string").alias("json_value"),
                    col("topic").alias("source_topic"),
                    col("timestamp").alias("kafka_timestamp"),
                    col("offset").alias("kafka_offset")
                )
                .select(
                    "user_id_key", "source_topic", "kafka_timestamp", "kafka_offset",
                    from_json(col("json_value"), security_event_schema).alias("event")
                )
                .select("user_id_key", "source_topic", "kafka_timestamp", "kafka_offset", "event.*")
                .withColumn("event_timestamp", to_timestamp(col("timestamp")))
                .withColumn("processing_time", current_timestamp())
                .withColumn("processing_delay_ms", 
                           expr("(unix_timestamp(processing_time) - unix_timestamp(event_timestamp)) * 1000")))
    
    logger.info("Kafka stream created successfully")
    return parsed_df

def analyze_security_events(events_df: DataFrame) -> Dict[str, DataFrame]:
    """
    Analyze security events with various aggregations and metrics
    
    Args:
        events_df: DataFrame with parsed security events
        
    Returns:
        Dictionary of analysis DataFrames
    """
    logger.info("Creating security analytics dataframes")
    
    # Various analytics views
    analysis = {}
    
    # 1. Event type counts over 5-minute windows
    analysis["event_type_counts"] = (events_df
        .withWatermark("event_timestamp", "10 minutes")
        .groupBy(
            window(col("event_timestamp"), "5 minutes"),
            col("event_type")
        )
        .count()
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("event_type"),
            col("count")
        ))
    
    # 2. High severity events
    analysis["high_severity_events"] = (events_df
        .filter(col("severity").isin("HIGH", "CRITICAL"))
        .withWatermark("event_timestamp", "1 hour")
        .select("event_id", "event_timestamp", "event_type", "user_id", 
                "user_type", "ip_address", "message", "severity"))
    
    # 3. Login failures by user
    analysis["login_failures"] = (events_df
        .filter(col("event_type") == "LOGIN_FAILURE")
        .withWatermark("event_timestamp", "15 minutes")
        .groupBy(
            window(col("event_timestamp"), "5 minutes"),
            col("user_id"),
            col("ip_address")
        )
        .count()
        .filter(col("count") >= 3)  # Potential brute force attempts
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("user_id"),
            col("ip_address"),
            col("count").alias("failure_count")
        ))
    
    # 4. Geographic distribution
    analysis["geo_distribution"] = (events_df
        .filter(col("geo_location").isNotNull())
        .withWatermark("event_timestamp", "30 minutes")
        .groupBy(
            window(col("event_timestamp"), "15 minutes"),
            col("geo_location.country"),
            col("geo_location.city")
        )
        .count()
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("country"),
            col("city"),
            col("count")
        ))
    
    # 5. Potential security anomalies
    analysis["security_anomalies"] = (events_df
        .withColumn("is_anomaly", when(
            (col("event_type").isin("UNAUTHORIZED_ACCESS", "PRIVILEGE_ESCALATION", "DATA_EXFILTRATION")) |
            (col("severity").isin("HIGH", "CRITICAL")) |
            (col("status_code") >= 400), 
            lit(True)
        ).otherwise(lit(False)))
        .filter(col("is_anomaly") == True)
        .withWatermark("event_timestamp", "1 hour")
        .select("event_id", "event_timestamp", "event_type", "user_id", 
                "ip_address", "message", "severity", "status_code"))
    
    logger.info(f"Created {len(analysis)} analysis dataframes")
    return analysis

def start_streaming_queries(spark: SparkSession, 
                           analysis_dfs: Dict[str, DataFrame],
                           output_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Start streaming queries for each analysis DataFrame
    
    Args:
        spark: SparkSession
        analysis_dfs: Dictionary of analysis DataFrames
        output_path: Base directory for output (default uses memory sink)
        
    Returns:
        Dictionary of active streaming queries
    """
    queries = {}
    
    # Queries that have aggregations (use complete mode)
    aggregation_queries = ["event_type_counts", "login_failures", "geo_distribution"]
    
    # Queries that don't have aggregations (use append mode)
    non_aggregation_queries = ["high_severity_events", "security_anomalies"]
    
    # Get base checkpoint directory from Spark config 
    checkpoint_base = spark.conf.get("spark.sql.streaming.checkpointLocation")
    
    for name, df in analysis_dfs.items():
        logger.info(f"Starting streaming query for: {name}")
        
        # Determine output mode based on query type
        output_mode = "complete" if name in aggregation_queries else "append"
        logger.info(f"Using output mode '{output_mode}' for query: {name}")
        
        # Create specific checkpoint directory for this query
        query_checkpoint = f"{checkpoint_base}/{name}"
        
        if output_path is None:
            # Write to memory sink
            query = (df.writeStream
                     .queryName(name)
                     .format("memory")
                     .option("checkpointLocation", query_checkpoint)
                     .outputMode(output_mode)
                     .start())
        else:
            # Write to parquet files
            query_output_path = os.path.join(output_path, name)
            query = (df.writeStream
                     .queryName(name)
                     .format("parquet")
                     .option("path", query_output_path)
                     .option("checkpointLocation", query_checkpoint)
                     .outputMode(output_mode)
                     .trigger(processingTime="30 seconds")
                     .start())
        
        queries[name] = query
        logger.info(f"Query started: {name} [{query.id}]")
    
    return queries 
 