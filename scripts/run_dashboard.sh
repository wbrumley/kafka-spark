#!/bin/bash
# This script runs the Spark dashboard with proper Java and Spark compatibility settings

set -e  # Exit immediately if a command fails

echo "===== Starting Security Events Dashboard ====="

# Get the directory of the script and navigate to it
SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR" || exit 1

# Create logs directory if it doesn't exist
mkdir -p logs

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
echo "Installing dependencies..."
pip install -q confluent-kafka==2.2.0 python-dotenv==1.0.0 pydantic==2.5.0 \
    pyspark==3.4.1 pandas==1.5.3 termcolor==2.3.0 tabulate==0.9.0 streamlit==1.32.0

# Download Spark Kafka connector if it doesn't exist
SPARK_KAFKA_JAR="spark-sql-kafka-0-10_2.12-3.4.1.jar"
if [ ! -f "jars/${SPARK_KAFKA_JAR}" ]; then
    echo "Downloading Spark Kafka connector..."
    mkdir -p jars
    curl -s -o "jars/${SPARK_KAFKA_JAR}" "https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.4.1/${SPARK_KAFKA_JAR}"
fi

# Add Java options for compatibility with newer Java versions
export JAVA_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
export PYSPARK_DRIVER_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
export PYSPARK_EXECUTOR_OPTS="-Dio.netty.tryReflectionSetAccessible=true"

# Export the Spark packages environment variable
export PYSPARK_SUBMIT_ARGS="--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1 pyspark-shell"

# Check for fixed_dashboard.py file
if [ -f "src/spark/fixed_dashboard.py" ]; then
    DASHBOARD_PATH="src/spark/fixed_dashboard.py"
elif [ -f "src/spark/dashboard.py" ]; then
    DASHBOARD_PATH="src/spark/dashboard.py"
else
    echo "Error: Dashboard file not found."
    exit 1
fi

# Display dependency versions for debugging
echo "===== Dependency Versions ====="
pip list | grep -E "confluent-kafka|python-dotenv|pydantic|pyspark|pandas|termcolor|tabulate|streamlit"
java -version
echo "=============================="

# Run the dashboard
echo "Starting dashboard at ${DASHBOARD_PATH}..."
echo "Press Ctrl+C to stop"
python "${DASHBOARD_PATH}" 