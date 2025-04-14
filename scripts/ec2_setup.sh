#!/bin/bash
# EC2 Setup Script for Kafka-Spark Security Analytics System
# This script prepares an EC2 instance to run the security analytics system

set -e  # Exit on any error

echo "======================================================"
echo "  Kafka-Spark Security Analytics - EC2 Setup"
echo "======================================================"
echo ""

# Install required packages
echo "Installing required system packages..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    openjdk-11-jdk \
    docker.io \
    docker-compose \
    curl \
    git

# Configure Docker to start on boot and add current user to docker group
echo "Configuring Docker..."
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
echo "Docker has been configured. You may need to log out and back in for group changes to take effect."

# Set up Python environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install confluent-kafka python-dotenv pydantic pyspark==3.4.1 pandas termcolor tabulate streamlit

# Create logs and jars directories
mkdir -p logs jars

# Download Spark Kafka connector
SPARK_KAFKA_JAR="spark-sql-kafka-0-10_2.12-3.4.1.jar"
if [ ! -f "jars/${SPARK_KAFKA_JAR}" ]; then
    echo "Downloading Spark Kafka connector..."
    curl -s -o "jars/${SPARK_KAFKA_JAR}" "https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.4.1/${SPARK_KAFKA_JAR}"
fi

# Increase file descriptor limits for Kafka
echo "Increasing file descriptor limits for system..."
echo "
* soft nofile 65536
* hard nofile 65536
" | sudo tee -a /etc/security/limits.conf > /dev/null

# Set swappiness to a lower value to improve performance
echo "Optimizing system settings for Kafka..."
echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf > /dev/null
sudo sysctl -p

# Make run scripts executable
echo "Making run scripts executable..."
chmod +x scripts/*.sh
[ -f run_unified_system.sh ] && chmod +x run_unified_system.sh
[ -f run_without_docker.sh ] && chmod +x run_without_docker.sh

# Create a default .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating default .env file..."
    cat > .env << EOF
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=dev_security_logs

# Event Generator Configuration
EVENT_GENERATION_INTERVAL=1.0

# EC2 Specific Settings
# Set to 'public' if you want to access services from outside the EC2 instance
ACCESS_MODE=local
# Your EC2 public DNS or IP (update this with your actual public DNS/IP)
EC2_PUBLIC_DNS=your-ec2-instance-public-dns.amazonaws.com
EOF
    echo "Created default .env file. Please update EC2_PUBLIC_DNS with your actual EC2 public DNS or IP."
fi

# Print final instructions
echo ""
echo "======================================================"
echo "  EC2 Setup Complete!"
echo "======================================================"
echo ""
echo "To run the system, use one of the following commands:"
echo ""
echo "1. Run with Docker (recommended):"
echo "   ./run_unified_system.sh"
echo ""
echo "2. Run without Docker:"
echo "   ./run_without_docker.sh"
echo ""
echo "3. Run individual components:"
echo "   ./scripts/run_dashboard.sh"
echo "   ./scripts/run_kafka_producer.sh"
echo "   ./scripts/run_spark_processor.sh"
echo ""
echo "Important: If you want to access the dashboard from outside EC2,"
echo "edit the .env file and set ACCESS_MODE=public and update EC2_PUBLIC_DNS"
echo "with your instance's public DNS or IP address."
echo ""
echo "For more information, refer to the documentation in docs/deployment.md"
echo "======================================================" 