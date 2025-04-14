#!/bin/bash
# Run the Kafka consumer to receive security events

set -e  # Exit on any error

echo "===== Starting Kafka Consumer ====="

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    set -a
    source .env
    set +a
fi

# Set or override environment variables
export KAFKA_TOPIC=${KAFKA_TOPIC:-"dev_security_logs"}
export KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-"localhost:9092"}

# Check for Python virtual environment and activate or create it
if [ -d "venv" ]; then
    echo "Activating Python virtual environment..."
    source venv/bin/activate
else
    echo "Creating new Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    
    # Install base dependencies
    pip install --upgrade pip setuptools wheel
fi

# Install required dependencies
echo "Installing dependencies..."
pip install -q confluent-kafka python-dotenv pydantic pyspark==3.4.1 pandas termcolor tabulate

# Clean up any Spark checkpoint
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

# Display configuration
echo "Configuration:"
echo "KAFKA_BOOTSTRAP_SERVERS: $KAFKA_BOOTSTRAP_SERVERS"
echo "KAFKA_TOPIC: $KAFKA_TOPIC"

# Parse command line arguments
USE_LATEST=false
if [ "$1" == "--from-latest" ]; then
    USE_LATEST=true
    echo "Starting from latest messages only"
else
    echo "Starting from beginning of topic"
fi

echo "Starting Kafka consumer..."
echo "Press Ctrl+C to stop"

# Run the direct Kafka-Spark processor
if [ "$USE_LATEST" = true ]; then
    python direct_kafka_spark.py --from-latest
else
    python direct_kafka_spark.py --from-beginning
fi 