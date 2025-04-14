#!/bin/bash
# Unified System Runner for Kafka-Spark Security Analytics System
# Runs all components together for cloud deployment

set -e  # Exit on any error

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Set default values if not in .env
KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-localhost:9092}
KAFKA_TOPIC=${KAFKA_TOPIC:-dev_security_logs}
EVENT_GENERATION_INTERVAL=${EVENT_GENERATION_INTERVAL:-1.0}
ACCESS_MODE=${ACCESS_MODE:-local}

# Create required directories
mkdir -p logs

# Trap for cleanup on exit
trap cleanup EXIT INT TERM

# Function to handle cleanup
cleanup() {
    echo "Shutting down services..."
    docker-compose -f docker/docker-compose.yml down
    # Kill any remaining Python processes
    pkill -f "python" || true
    echo "All services have been stopped."
}

echo "======================================================"
echo "  Kafka-Spark Security Analytics - Unified System"
echo "======================================================"
echo ""

# Determine the host for the Streamlit dashboard
if [ "$ACCESS_MODE" = "public" ] && [ -n "$EC2_PUBLIC_DNS" ]; then
    DASHBOARD_HOST="$EC2_PUBLIC_DNS"
    echo "Running in public access mode. Dashboard will be available at: http://$DASHBOARD_HOST:8501"
    STREAMLIT_ARGS="--server.address=0.0.0.0 --server.headless=true"
else
    DASHBOARD_HOST="localhost"
    echo "Running in local access mode. Dashboard will be available at: http://localhost:8501"
    STREAMLIT_ARGS=""
fi

# Start Kafka and Zookeeper using Docker
echo "Starting Kafka and Zookeeper..."
cd docker && docker-compose up -d
cd ..

# Wait for Kafka to be ready
echo "Waiting for Kafka to start (this may take up to 30 seconds)..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! nc -z localhost 9092 && [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 1
    RETRY_COUNT=$((RETRY_COUNT+1))
    echo -n "."
done
echo ""

if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "Error: Kafka did not start within the expected time."
    exit 1
fi

echo "Kafka is ready!"

# Ensure Python virtual environment is active
if [ ! -d "venv" ]; then
    echo "Setting up Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip setuptools wheel
    pip install -r requirements.txt || echo "No requirements.txt found, installing individually..."
    pip install confluent-kafka python-dotenv pydantic pyspark pandas termcolor tabulate streamlit
else
    source venv/bin/activate
fi

# Start the event generator
echo "Starting security event generator..."
python src/generator/generator.py --topic $KAFKA_TOPIC --interval $EVENT_GENERATION_INTERVAL > logs/generator.log 2>&1 &
GENERATOR_PID=$!
echo "Generator started with PID: $GENERATOR_PID"

# Start the Spark processor
echo "Starting Spark processor..."
python src/processor/spark_processor.py --topic $KAFKA_TOPIC > logs/spark_processor.log 2>&1 &
PROCESSOR_PID=$!
echo "Processor started with PID: $PROCESSOR_PID"

# Start the Streamlit dashboard
echo "Starting Streamlit dashboard..."
streamlit run streamlit_dashboard.py $STREAMLIT_ARGS > logs/dashboard.log 2>&1 &
DASHBOARD_PID=$!
echo "Dashboard started with PID: $DASHBOARD_PID"

echo ""
echo "======================================================"
echo "  System is now running!"
echo "======================================================"
echo ""
echo "Services:"
echo "- Kafka & Zookeeper: Running on $KAFKA_BOOTSTRAP_SERVERS"
echo "- Security Event Generator: Generating events every ${EVENT_GENERATION_INTERVAL}s to topic '$KAFKA_TOPIC'"
echo "- Spark Processor: Processing events from topic '$KAFKA_TOPIC'"
echo "- Streamlit Dashboard: http://$DASHBOARD_HOST:8501"
echo ""
echo "Logs:"
echo "- Generator: logs/generator.log"
echo "- Processor: logs/spark_processor.log"
echo "- Dashboard: logs/dashboard.log"
echo ""
echo "To stop all services, press Ctrl+C"
echo "======================================================"

# Keep script running
wait 