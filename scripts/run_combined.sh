#!/bin/bash

# Run either Kafka-Spark integration or the unified processor
# This script supports two modes of operation:
# 1. Kafka + Spark streaming integration
# 2. Self-contained unified processor

SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR" || exit 1

# Create logs directory if it doesn't exist
mkdir -p logs

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    set -a
    source .env
    set +a
fi

# Check if Python virtual environment exists
if [ -d "venv" ]; then
    echo "Activating Python virtual environment..."
    source venv/bin/activate
fi

# Set a consistent Kafka topic name
export KAFKA_TOPIC=${KAFKA_TOPIC:-"dev_security_logs"}
export KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-"localhost:9092"}

# Display Kafka configuration for debugging
echo "Kafka Configuration:"
echo "KAFKA_BOOTSTRAP_SERVERS: $KAFKA_BOOTSTRAP_SERVERS"
echo "KAFKA_TOPIC: $KAFKA_TOPIC"

# Parse command line arguments
MODE="kafka-spark"  # Default mode
if [ "$1" == "--unified" ] || [ "$1" == "-u" ]; then
    MODE="unified"
fi

# Install required dependencies with updated Spark version
echo "Checking dependencies..."
pip install -q confluent-kafka python-dotenv pydantic pyspark==3.4.1 pandas termcolor tabulate

if [ "$MODE" == "kafka-spark" ]; then
    # Clean up any previous Spark checkpoint
    echo "Cleaning up previous checkpoint directories..."
    rm -rf /tmp/spark-checkpoints*

    # Download Spark Kafka connector if it doesn't exist
    SPARK_KAFKA_JAR="spark-sql-kafka-0-10_2.12-3.4.1.jar"
    if [ ! -f "jars/${SPARK_KAFKA_JAR}" ]; then
        echo "Downloading Spark Kafka connector..."
        mkdir -p jars
        curl -s -o "jars/${SPARK_KAFKA_JAR}" "https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.4.1/${SPARK_KAFKA_JAR}"
    fi

    # Export the Spark packages environment variable with updated version
    export PYSPARK_SUBMIT_ARGS="--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1 pyspark-shell"
    
    # Add Java options for compatibility with newer Java versions
    export JAVA_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
    export PYSPARK_DRIVER_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
    export PYSPARK_EXECUTOR_OPTS="-Dio.netty.tryReflectionSetAccessible=true"

    # Verify the Kafka topic setting
    echo "Using Kafka topic: $KAFKA_TOPIC"
    echo "Spark packages: $PYSPARK_SUBMIT_ARGS"

    # Start the direct Kafka-Spark processor
    echo "Starting Kafka-Spark processor..."
    echo "Press Ctrl+C to stop"
    echo ""

    # Run the direct Kafka-Spark processor
    python src/spark/direct_kafka_spark.py
else
    # Run the unified processor
    echo "Starting unified security events processor..."
    echo "Press Ctrl+C to stop"
    echo ""
    
    # Run the unified processor
    python src/unified_processor.py
fi 