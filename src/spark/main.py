import os
import signal
import time
import logging
import argparse
import json
from typing import Dict, Any
from datetime import datetime

from src.spark.session import create_spark_session, stop_spark_session
from src.spark.kafka_stream import (
    create_kafka_stream, 
    analyze_security_events,
    start_streaming_queries
)
from src.config.settings import KAFKA_TOPIC, KAFKA_BOOTSTRAP_SERVERS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "spark_app.log"))
    ]
)
logger = logging.getLogger(__name__)

# Global variables for signal handling
queries = {}
spark = None
running = True

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    global running
    logger.info("Shutdown signal received, stopping Spark application...")
    running = False

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_output_dir(base_path: str = "spark_output") -> str:
    """Create output directory with timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(base_path, f"security_events_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Created output directory: {output_dir}")
    return output_dir

def print_query_status(queries: Dict[str, Any]) -> None:
    """Print status of active queries"""
    status_rows = []
    for name, query in queries.items():
        if query.isActive:
            progress = query.lastProgress
            if progress:
                num_input_rows = progress.get("numInputRows", 0)
                processing_rate = progress.get("processedRowsPerSecond", 0)
                status = f"Active - Rows: {num_input_rows}, Rate: {processing_rate:.2f} rows/sec"
            else:
                status = "Active - No progress data yet"
        else:
            status = "Inactive"
        
        status_rows.append(f"  {name}: {status}")
    
    if status_rows:
        logger.info("Query Status:\n" + "\n".join(status_rows))

def main():
    global spark, queries
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Spark Security Events Analyzer")
    parser.add_argument("--output", type=str, default=None, 
                        help="Output directory for analysis results")
    parser.add_argument("--batch-interval", type=int, default=30,
                        help="Processing interval in seconds")
    parser.add_argument("--memory-only", action="store_true",
                        help="Store results in memory only (for interactive querying)")
    args = parser.parse_args()
    
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Create output directory if needed
    output_path = None if args.memory_only else create_output_dir(args.output or "spark_output")
    
    try:
        # Initialize Spark
        spark = create_spark_session("SecurityEventsAnalyzer")
        
        # Create Kafka stream
        events_df = create_kafka_stream(
            spark=spark,
            topic=KAFKA_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS
        )
        
        # Create analytics
        analytics_dfs = analyze_security_events(events_df)
        
        # Start streaming queries
        queries = start_streaming_queries(
            spark=spark,
            analysis_dfs=analytics_dfs,
            output_path=output_path
        )
        
        # Write configuration metadata
        if output_path:
            metadata = {
                "timestamp": datetime.now().isoformat(),
                "kafka_topic": KAFKA_TOPIC,
                "kafka_bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
                "batch_interval_seconds": args.batch_interval,
                "queries": list(queries.keys())
            }
            
            with open(os.path.join(output_path, "metadata.json"), "w") as f:
                json.dump(metadata, f, indent=2)
        
        # Keep the application running and report status periodically
        logger.info("Spark application started. Press Ctrl+C to stop.")
        
        status_interval = 0
        while running:
            time.sleep(1)
            status_interval += 1
            
            # Print status every 30 seconds
            if status_interval >= args.batch_interval:
                print_query_status(queries)
                status_interval = 0
                
    except Exception as e:
        logger.error(f"Error in Spark application: {e}", exc_info=True)
    finally:
        # Stop all queries
        if queries:
            logger.info("Stopping streaming queries...")
            for name, query in queries.items():
                try:
                    query.stop()
                    logger.info(f"Query stopped: {name}")
                except Exception as e:
                    logger.error(f"Error stopping query {name}: {e}")
        
        # Stop Spark session
        if spark:
            stop_spark_session(spark)
        
        logger.info("Spark application shutdown complete")

if __name__ == "__main__":
    main() 
 