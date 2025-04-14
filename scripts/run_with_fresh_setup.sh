#!/bin/bash
# This script creates a fresh setup before running the application
# It cleans up any previous Spark checkpoints, Kafka logs, and ensures dependencies are installed

set -e  # Exit immediately if a command fails

echo "===== Starting Fresh Setup ====="

# Get the directory of the script and navigate to it
SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR" || exit 1

# Create logs directory and clear existing log files
echo "Setting up logs directory..."
mkdir -p logs
rm -f logs/*.log

# Check for Python virtual environment
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

# Clean up any Spark checkpoints
echo "Cleaning up previous Spark checkpoints..."
rm -rf /tmp/spark-checkpoints*

# Set Kafka topic consistently
export KAFKA_TOPIC="dev_security_logs"
echo "Setting Kafka topic to: $KAFKA_TOPIC"

# Install required dependencies with specific versions
# Updated to use Spark 3.4.1 for better Java 11+ compatibility
echo "Installing dependencies..."
pip install -q confluent-kafka==2.2.0 python-dotenv==1.0.0 pydantic==2.5.0 pyspark==3.4.1 pandas==1.5.3 termcolor==2.3.0 tabulate==0.9.0

# Download Spark Kafka connector if it doesn't exist
# Updated to use 3.4.1 version of the connector
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

# Display dependency versions for debugging
echo "===== Dependency Versions ====="
pip list | grep -E "confluent-kafka|python-dotenv|pydantic|pyspark|pandas|termcolor|tabulate"
java -version
echo "=============================="

# Ask the user which mode to run in
echo ""
echo "Choose which mode to run:"
echo "1) Kafka + Spark integration (direct_kafka_spark.py)"
echo "2) Self-contained processor (unified_processor.py)"
read -p "Enter your choice (1/2): " choice

case $choice in
    1)
        echo "Starting Kafka-Spark processor..."
        echo "Press Ctrl+C to stop"
        python direct_kafka_spark.py
        ;;
    2)
        echo "Starting unified processor..."
        echo "Press Ctrl+C to stop"
        python unified_processor.py
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac 