import os
import logging
import time
from typing import Optional
from datetime import datetime
from pyspark.sql import SparkSession
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "spark.log"))
    ]
)
logger = logging.getLogger(__name__)

def create_spark_session(app_name: str = "SecurityEventsAnalysis", 
                         master: Optional[str] = None) -> SparkSession:
    """
    Create and configure a Spark session with Kafka integration support.
    
    Args:
        app_name: Name of the Spark application
        master: Spark master URL (defaults to local[*] if not specified)
        
    Returns:
        Configured SparkSession
    """
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Use environment variable or default to local
    master = master or os.getenv("SPARK_MASTER", "local[*]")
    
    # Create a unique checkpoint directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    checkpoint_dir = os.getenv("CHECKPOINT_DIR", "/tmp/spark-checkpoints")
    unique_checkpoint_dir = f"{checkpoint_dir}_{timestamp}"
    
    logger.info(f"Creating Spark session with master: {master}")
    logger.info(f"Using checkpoint directory: {unique_checkpoint_dir}")
    
    # Set Java options for compatibility with newer Java versions
    os.environ['JAVA_OPTS'] = "-Dio.netty.tryReflectionSetAccessible=true"
    os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1 --conf spark.driver.extraJavaOptions="-Dio.netty.tryReflectionSetAccessible=true" --conf spark.executor.extraJavaOptions="-Dio.netty.tryReflectionSetAccessible=true" pyspark-shell'
    
    # Build Spark session
    spark = (SparkSession.builder
             .appName(app_name)
             .master(master)
             # Add necessary packages for Kafka integration - Updated to 3.4.1
             .config("spark.jars.packages", 
                     "org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1")
             # Add configurations for better performance
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.default.parallelism", "8")
             .config("spark.streaming.kafka.consumer.cache.enabled", "false")
             # Configure checkpointing for reliable processing
             .config("spark.sql.streaming.checkpointLocation", unique_checkpoint_dir)
             # Add Java options for compatibility with newer Java versions
             .config("spark.driver.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
             .config("spark.executor.extraJavaOptions", "-Dio.netty.tryReflectionSetAccessible=true")
             .getOrCreate())
    
    # Set log level
    spark.sparkContext.setLogLevel("WARN")
    
    logger.info(f"Spark session created successfully: {spark.version}")
    return spark

def stop_spark_session(spark: SparkSession) -> None:
    """
    Properly stop a Spark session.
    
    Args:
        spark: The SparkSession to stop
    """
    if spark is not None:
        logger.info("Stopping Spark session")
        spark.stop() 
 