#!/bin/bash
# Unified script to run the entire Kafka-Spark Security Analytics system
# This script starts all components: Kafka, Generator, Spark Processor, and Dashboard

set -e  # Exit on any error

echo "======================================================"
echo "  Kafka-Spark Security Analytics - Unified Launcher"
echo "======================================================"
echo ""

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    set -a
    source .env
    set +a
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Set default environment variables
export KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-"localhost:9092"}
export KAFKA_TOPIC=${KAFKA_TOPIC:-"dev_security_logs"}
export EVENT_GENERATION_INTERVAL=${EVENT_GENERATION_INTERVAL:-"1.0"}

# Function to check if Docker is installed and running
check_docker() {
    echo "Checking Docker..."
    if ! command -v docker &> /dev/null; then
        echo "Error: Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        echo "Error: Docker daemon is not running. Please start Docker."
        exit 1
    fi
    
    # Check for both docker-compose and the newer docker compose command
    DOCKER_COMPOSE_CMD=""
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
        echo "Using docker-compose command"
    elif docker compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
        echo "Using docker compose command (new format)"
    else
        echo "Error: Docker Compose is not available. Please install Docker Desktop for Mac or Docker Compose."
        exit 1
    fi
    
    echo "Docker is ready."
}

# Function to setup Python virtual environment
setup_python_env() {
    echo "Setting up Python environment..."
    
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
    pip install -q confluent-kafka python-dotenv pydantic pyspark==3.4.1 pandas termcolor tabulate streamlit
    
    echo "Python environment ready."
}

# Function to start Kafka and Zookeeper with Docker
start_kafka() {
    echo "Starting Kafka and Zookeeper..."
    
    # Navigate to docker directory if it exists, otherwise use current directory
    if [ -d "docker" ]; then
        cd docker
    fi
    
    # Start Kafka and Zookeeper
    $DOCKER_COMPOSE_CMD up -d zookeeper kafka
    
    # Check if Kafka is running
    echo "Waiting for Kafka to start..."
    for i in {1..30}; do
        if $DOCKER_COMPOSE_CMD logs kafka | grep -q "started"; then
            echo "Kafka is ready!"
            break
        fi
        echo -n "."
        sleep 1
        if [ $i -eq 30 ]; then
            echo "Error: Kafka did not start within 30 seconds."
            exit 1
        fi
    done
    
    # Return to original directory if moved to docker
    if [ -d "../docker" ]; then
        cd ..
    fi
}

# Function to start the security event generator
start_generator() {
    echo "Starting security event generator..."
    
    # Run the generator in the background
    python src/main.py > logs/generator.log 2>&1 &
    GENERATOR_PID=$!
    echo "Generator started with PID: $GENERATOR_PID"
    
    # Give the generator a moment to start
    sleep 2
    
    # Check if the generator is still running
    if ! ps -p $GENERATOR_PID > /dev/null; then
        echo "Error: Generator failed to start. Check logs/generator.log for details."
        exit 1
    fi
    
    echo $GENERATOR_PID > logs/generator.pid
    echo "Generator is running. Logs in logs/generator.log"
}

# Function to start the Spark processor
start_spark_processor() {
    echo "Starting Spark processor..."
    
    # Clean up any Spark checkpoints
    rm -rf /tmp/spark-checkpoints*
    
    # Download Spark Kafka connector if it doesn't exist
    SPARK_KAFKA_JAR="spark-sql-kafka-0-10_2.12-3.4.1.jar"
    if [ ! -f "jars/${SPARK_KAFKA_JAR}" ]; then
        echo "Downloading Spark Kafka connector..."
        mkdir -p jars
        curl -s -o "jars/${SPARK_KAFKA_JAR}" "https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.4.1/${SPARK_KAFKA_JAR}"
    fi
    
    # Export the Spark packages environment variable
    export PYSPARK_SUBMIT_ARGS="--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1 pyspark-shell"
    
    # Add Java options for compatibility with newer Java versions
    export JAVA_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
    export PYSPARK_DRIVER_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
    export PYSPARK_EXECUTOR_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
    
    # Run the processor in the background
    python src/spark/direct_kafka_spark.py --from-beginning > logs/spark_processor.log 2>&1 &
    PROCESSOR_PID=$!
    echo "Spark processor started with PID: $PROCESSOR_PID"
    
    # Give the processor a moment to start
    sleep 5
    
    # Check if the processor is still running
    if ! ps -p $PROCESSOR_PID > /dev/null; then
        echo "Error: Spark processor failed to start. Check logs/spark_processor.log for details."
        exit 1
    fi
    
    echo $PROCESSOR_PID > logs/processor.pid
    echo "Spark processor is running. Logs in logs/spark_processor.log"
}

# Function to start the Streamlit dashboard
start_dashboard() {
    echo "Starting Streamlit dashboard..."
    
    # Find the dashboard file
    DASHBOARD_FILE=""
    if [ -f "src/dashboard/streamlit_dashboard.py" ]; then
        DASHBOARD_FILE="src/dashboard/streamlit_dashboard.py"
    elif [ -f "src/spark/streamlit_dashboard.py" ]; then
        DASHBOARD_FILE="src/spark/streamlit_dashboard.py"
    elif [ -f "src/spark/dashboard.py" ]; then
        DASHBOARD_FILE="src/spark/dashboard.py"
    else
        echo "Error: Dashboard file not found."
        exit 1
    fi
    
    # Run the dashboard in the background
    streamlit run $DASHBOARD_FILE > logs/dashboard.log 2>&1 &
    DASHBOARD_PID=$!
    echo "Dashboard started with PID: $DASHBOARD_PID"
    
    # Give the dashboard a moment to start
    sleep 5
    
    # Check if the dashboard is still running
    if ! ps -p $DASHBOARD_PID > /dev/null; then
        echo "Error: Dashboard failed to start. Check logs/dashboard.log for details."
        exit 1
    fi
    
    echo $DASHBOARD_PID > logs/dashboard.pid
    echo "Dashboard is running at http://localhost:8501"
    echo "Dashboard logs in logs/dashboard.log"
}

# Function to handle cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    
    # Stop the dashboard
    if [ -f "logs/dashboard.pid" ]; then
        DASHBOARD_PID=$(cat logs/dashboard.pid)
        if ps -p $DASHBOARD_PID > /dev/null; then
            echo "Stopping dashboard (PID: $DASHBOARD_PID)..."
            kill $DASHBOARD_PID
        fi
    fi
    
    # Stop the Spark processor
    if [ -f "logs/processor.pid" ]; then
        PROCESSOR_PID=$(cat logs/processor.pid)
        if ps -p $PROCESSOR_PID > /dev/null; then
            echo "Stopping Spark processor (PID: $PROCESSOR_PID)..."
            kill $PROCESSOR_PID
        fi
    fi
    
    # Stop the generator
    if [ -f "logs/generator.pid" ]; then
        GENERATOR_PID=$(cat logs/generator.pid)
        if ps -p $GENERATOR_PID > /dev/null; then
            echo "Stopping generator (PID: $GENERATOR_PID)..."
            kill $GENERATOR_PID
        fi
    fi
    
    # Stop Kafka and Zookeeper if --stop-kafka is specified
    if [ "$STOP_KAFKA" = true ]; then
        echo "Stopping Kafka and Zookeeper..."
        if [ -d "docker" ]; then
            cd docker
        fi
        $DOCKER_COMPOSE_CMD stop kafka zookeeper
        if [ -d "../docker" ]; then
            cd ..
        fi
    fi
    
    echo "Cleanup complete."
}

# Parse command-line arguments
STOP_KAFKA=false
DEMO_MODE=false

for arg in "$@"; do
    case $arg in
        --stop-kafka)
            STOP_KAFKA=true
            shift
            ;;
        --demo)
            DEMO_MODE=true
            shift
            ;;
        *)
            # Unknown option
            shift
            ;;
    esac
done

# Register the cleanup function to run on exit
trap cleanup EXIT

# Main script execution
echo "Starting all services..."

# Setup environment
check_docker
setup_python_env

# Start all components
start_kafka
sleep 5  # Give Kafka time to fully initialize
start_generator
start_spark_processor
start_dashboard

# Print access information
echo ""
echo "======================================================"
echo "  All services are now running!"
echo "======================================================"
echo ""
echo "Dashboard URL: http://localhost:8501"
echo "Kafka Topic: $KAFKA_TOPIC"
echo "Event Generation Rate: every ${EVENT_GENERATION_INTERVAL} seconds"
echo ""
echo "Use the following commands to view logs:"
echo "- Generator: tail -f logs/generator.log"
echo "- Spark Processor: tail -f logs/spark_processor.log"
echo "- Dashboard: tail -f logs/dashboard.log"
echo ""

if [ "$DEMO_MODE" = true ]; then
    # In demo mode, run for a limited time then exit
    echo "Running in demo mode for 10 minutes..."
    echo "Press Ctrl+C to stop sooner."
    sleep 600  # Run for 10 minutes
else
    # Keep the script running until interrupted
    echo "Press Ctrl+C to stop all services"
    
    # Keep the main script running
    while true; do
        sleep 10
        
        # Check if all components are still running
        if [ -f "logs/generator.pid" ] && ! ps -p $(cat logs/generator.pid) > /dev/null; then
            echo "Warning: Generator has stopped. Check logs/generator.log for details."
        fi
        
        if [ -f "logs/processor.pid" ] && ! ps -p $(cat logs/processor.pid) > /dev/null; then
            echo "Warning: Spark processor has stopped. Check logs/spark_processor.log for details."
        fi
        
        if [ -f "logs/dashboard.pid" ] && ! ps -p $(cat logs/dashboard.pid) > /dev/null; then
            echo "Warning: Dashboard has stopped. Check logs/dashboard.log for details."
        fi
    done
fi 