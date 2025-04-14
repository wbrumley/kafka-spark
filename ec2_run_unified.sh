#!/bin/bash
# EC2 Deployment Script for Kafka-Spark Security Analytics System
# This script is designed to run on an AWS EC2 instance
# It starts all components: Kafka, Generator, Spark Processor, and Dashboard

set -e  # Exit on any error

echo "======================================================"
echo "  Kafka-Spark Security Analytics - EC2 Launcher"
echo "======================================================"
echo ""

# Set EC2's public IP address for external access
EC2_PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)
if [ -z "$EC2_PUBLIC_IP" ]; then
    echo "Warning: Could not determine EC2 public IP. Using localhost instead."
    EC2_PUBLIC_IP="localhost"
fi
echo "EC2 Public IP: $EC2_PUBLIC_IP"

# Create logs directory if it doesn't exist
mkdir -p logs

# Load environment variables from .env file if it exists or create one
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    set -a
    source .env
    set +a
else
    echo "Creating .env file with EC2 settings..."
    cat > .env << EOF
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=${EC2_PUBLIC_IP}:9092
KAFKA_TOPIC=security_events

# Generator Configuration
EVENT_GENERATION_INTERVAL=1.0

# Spark Configuration
SPARK_MASTER=local[*]
SPARK_CHECKPOINT_DIR=/tmp/spark-checkpoints
EOF
    set -a
    source .env
    set +a
fi

# Update Kafka settings to use EC2 public IP
export KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-"${EC2_PUBLIC_IP}:9092"}
export KAFKA_TOPIC=${KAFKA_TOPIC:-"security_events"}
export EVENT_GENERATION_INTERVAL=${EVENT_GENERATION_INTERVAL:-"1.0"}

# Function to check if Docker is installed and running
check_docker() {
    echo "Checking Docker..."
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        sudo apt-get update
        sudo apt-get install -y docker.io
        sudo usermod -aG docker ubuntu
        sudo systemctl enable docker
        sudo systemctl start docker
        # Log out and back in for group changes to take effect
        # For this script, we'll just use sudo for docker commands
    fi
    
    if ! docker info &> /dev/null; then
        echo "Starting Docker daemon..."
        sudo systemctl start docker
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        echo "Installing docker-compose..."
        sudo curl -L "https://github.com/docker/compose/releases/download/v2.17.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
    fi
    
    echo "Docker is ready."
}

# Function to setup Python virtual environment
setup_python_env() {
    echo "Setting up Python environment..."
    
    # Make sure Python 3 and pip are installed
    if ! command -v python3 &> /dev/null; then
        echo "Installing Python 3..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
    fi
    
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

# Function to update Docker Compose for EC2
update_docker_compose() {
    echo "Updating Docker Compose configuration for EC2..."
    
    if [ -d "docker" ]; then
        cd docker
    fi
    
    # If docker-compose.yml exists, update it
    if [ -f "docker-compose.yml" ]; then
        echo "Updating docker-compose.yml..."
        
        # Update the KAFKA_ADVERTISED_LISTENERS to use EC2 public IP
        # This ensures Kafka is accessible from outside Docker
        sed -i "s/PLAINTEXT_HOST:\/\/localhost:9092/PLAINTEXT_HOST:\/\/${EC2_PUBLIC_IP}:9092/g" docker-compose.yml
        
        echo "Docker Compose configuration updated."
    else
        echo "Warning: docker-compose.yml not found. Creating a minimal configuration..."
        cat > docker-compose.yml << EOF
version: '3'

services:
  zookeeper:
    image: confluentinc/cp-zookeeper:latest
    container_name: zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    ports:
      - "2181:2181"
    volumes:
      - zookeeper-data:/var/lib/zookeeper/data
    restart: unless-stopped

  kafka:
    image: confluentinc/cp-kafka:latest
    container_name: kafka
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://${EC2_PUBLIC_IP}:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    volumes:
      - kafka-data:/var/lib/kafka/data
    restart: unless-stopped

volumes:
  zookeeper-data:
  kafka-data:
EOF
    fi
    
    # Return to original directory if needed
    if [ -d "../docker" ]; then
        cd ..
    fi
}

# Function to start Kafka and Zookeeper with Docker
start_kafka() {
    echo "Starting Kafka and Zookeeper..."
    
    # First make sure Docker Compose is updated
    update_docker_compose
    
    # Navigate to docker directory if it exists
    if [ -d "docker" ]; then
        cd docker
    fi
    
    # Start Kafka and Zookeeper
    sudo docker-compose up -d zookeeper kafka
    
    # Check if Kafka is running
    echo "Waiting for Kafka to start..."
    for i in {1..60}; do
        if sudo docker-compose logs kafka | grep -q "started"; then
            echo "Kafka is ready!"
            break
        fi
        echo -n "."
        sleep 2
        if [ $i -eq 60 ]; then
            echo "Warning: Kafka might not have started properly. Continuing anyway..."
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
    if [ -f "src/main.py" ]; then
        nohup python src/main.py > logs/generator.log 2>&1 &
    else
        nohup python main.py > logs/generator.log 2>&1 &
    fi
    
    GENERATOR_PID=$!
    echo "Generator started with PID: $GENERATOR_PID"
    
    # Give the generator a moment to start
    sleep 3
    
    # Check if the generator is still running
    if ! ps -p $GENERATOR_PID > /dev/null; then
        echo "Warning: Generator may have failed to start. Check logs/generator.log for details."
        echo "Continuing with setup..."
    else
        echo $GENERATOR_PID > logs/generator.pid
        echo "Generator is running. Logs in logs/generator.log"
    fi
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
    
    # Run the processor in the background using nohup to ensure it keeps running after SSH session ends
    nohup python direct_kafka_spark.py --from-beginning > logs/spark_processor.log 2>&1 &
    PROCESSOR_PID=$!
    echo "Spark processor started with PID: $PROCESSOR_PID"
    
    # Give the processor a moment to start
    sleep 5
    
    # Check if the processor is still running
    if ! ps -p $PROCESSOR_PID > /dev/null; then
        echo "Warning: Spark processor may have failed to start. Check logs/spark_processor.log for details."
        echo "Continuing with setup..."
    else
        echo $PROCESSOR_PID > logs/processor.pid
        echo "Spark processor is running. Logs in logs/spark_processor.log"
    fi
}

# Function to start the Streamlit dashboard
start_dashboard() {
    echo "Starting Streamlit dashboard..."
    
    # Find the dashboard file
    DASHBOARD_FILE=""
    if [ -f "streamlit_dashboard.py" ]; then
        DASHBOARD_FILE="streamlit_dashboard.py"
    elif [ -f "src/spark/streamlit_dashboard.py" ]; then
        DASHBOARD_FILE="src/spark/streamlit_dashboard.py"
    elif [ -f "src/spark/dashboard.py" ]; then
        DASHBOARD_FILE="src/spark/dashboard.py"
    else
        echo "Warning: Dashboard file not found. Skipping dashboard startup."
        return
    fi
    
    # Run the dashboard in the background using nohup to ensure it keeps running after SSH session ends
    nohup streamlit run $DASHBOARD_FILE --server.address=0.0.0.0 --server.port=8501 > logs/dashboard.log 2>&1 &
    DASHBOARD_PID=$!
    echo "Dashboard started with PID: $DASHBOARD_PID"
    
    # Give the dashboard a moment to start
    sleep 5
    
    # Check if the dashboard is still running
    if ! ps -p $DASHBOARD_PID > /dev/null; then
        echo "Warning: Dashboard may have failed to start. Check logs/dashboard.log for details."
        echo "Continuing with setup..."
    else
        echo $DASHBOARD_PID > logs/dashboard.pid
        echo "Dashboard is running at http://${EC2_PUBLIC_IP}:8501"
        echo "Dashboard logs in logs/dashboard.log"
    fi
}

# Function to create a service monitor script
create_service_monitor() {
    echo "Creating service monitor script..."
    
    cat > monitor_services.sh << EOF
#!/bin/bash
# Service monitor script - runs as a cron job to ensure services stay running

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Check and restart generator if needed
if [ -f logs/generator.pid ]; then
    GENERATOR_PID=\$(cat logs/generator.pid)
    if ! ps -p \$GENERATOR_PID > /dev/null; then
        echo "\$(date): Generator not running. Restarting..." >> logs/monitor.log
        if [ -f src/main.py ]; then
            nohup python src/main.py > logs/generator.log 2>&1 &
        else
            nohup python main.py > logs/generator.log 2>&1 &
        fi
        echo \$! > logs/generator.pid
    fi
fi

# Check and restart Spark processor if needed
if [ -f logs/processor.pid ]; then
    PROCESSOR_PID=\$(cat logs/processor.pid)
    if ! ps -p \$PROCESSOR_PID > /dev/null; then
        echo "\$(date): Spark processor not running. Restarting..." >> logs/monitor.log
        export PYSPARK_SUBMIT_ARGS="--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1 pyspark-shell"
        export JAVA_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
        export PYSPARK_DRIVER_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
        export PYSPARK_EXECUTOR_OPTS="-Dio.netty.tryReflectionSetAccessible=true"
        nohup python direct_kafka_spark.py --from-beginning > logs/spark_processor.log 2>&1 &
        echo \$! > logs/processor.pid
    fi
fi

# Check and restart dashboard if needed
if [ -f logs/dashboard.pid ]; then
    DASHBOARD_PID=\$(cat logs/dashboard.pid)
    if ! ps -p \$DASHBOARD_PID > /dev/null; then
        echo "\$(date): Dashboard not running. Restarting..." >> logs/monitor.log
        DASHBOARD_FILE=""
        if [ -f "streamlit_dashboard.py" ]; then
            DASHBOARD_FILE="streamlit_dashboard.py"
        elif [ -f "src/spark/streamlit_dashboard.py" ]; then
            DASHBOARD_FILE="src/spark/streamlit_dashboard.py"
        elif [ -f "src/spark/dashboard.py" ]; then
            DASHBOARD_FILE="src/spark/dashboard.py"
        fi
        
        if [ -n "\$DASHBOARD_FILE" ]; then
            nohup streamlit run \$DASHBOARD_FILE --server.address=0.0.0.0 --server.port=8501 > logs/dashboard.log 2>&1 &
            echo \$! > logs/dashboard.pid
        fi
    fi
fi

# Check if Kafka is running
if [ -d docker ]; then
    cd docker
fi

if ! sudo docker ps | grep -q kafka; then
    echo "\$(date): Kafka not running. Restarting..." >> logs/monitor.log
    sudo docker-compose up -d zookeeper kafka
fi

if [ -d ../docker ]; then
    cd ..
fi
EOF

    chmod +x monitor_services.sh
    
    # Set up cron job to run the monitor every 5 minutes
    echo "Setting up cron job for service monitoring..."
    (crontab -l 2>/dev/null; echo "*/5 * * * * cd $(pwd) && ./monitor_services.sh") | crontab -
    
    echo "Service monitor created and scheduled."
}

# Main script execution
echo "Starting all services on EC2..."

# Setup environment
check_docker
setup_python_env

# Start all components
start_kafka
sleep 5  # Give Kafka time to fully initialize
start_generator
start_spark_processor
start_dashboard

# Create service monitor
create_service_monitor

# Print access information
echo ""
echo "======================================================"
echo "  All services are now running on EC2!"
echo "======================================================"
echo ""
echo "Dashboard URL: http://${EC2_PUBLIC_IP}:8501"
echo "Kafka Topic: $KAFKA_TOPIC"
echo "Event Generation Rate: every ${EVENT_GENERATION_INTERVAL} seconds"
echo ""
echo "Use the following commands to view logs:"
echo "- Generator: tail -f logs/generator.log"
echo "- Spark Processor: tail -f logs/spark_processor.log"
echo "- Dashboard: tail -f logs/dashboard.log"
echo ""
echo "A monitoring service has been set up to restart any failed components."
echo "It runs every 5 minutes via cron job."
echo ""
echo "To manually stop all services:"
echo "1. Kill the processes: ./stop_services.sh (create this if needed)"
echo "2. Stop the Docker containers: cd docker && sudo docker-compose down"
echo ""
echo "Setup on EC2 complete!" 