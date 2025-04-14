#!/bin/bash
# Setup script for Kafka-Spark security log analysis system
# Usage: ./setup_vm.sh [kafka|generator]

set -e  # Exit on error

if [ "$1" != "kafka" ] && [ "$1" != "generator" ]; then
    echo "Error: Please specify either 'kafka' or 'generator' as an argument"
    echo "Usage: ./setup_vm.sh [kafka|generator]"
    exit 1
fi

VM_TYPE=$1
PROJECT_DIR="kafka-spark"

echo "Setting up VM for: $VM_TYPE"
echo "------------------------"

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install common dependencies
echo "Installing common dependencies..."
sudo apt install -y python3 python3-pip python3-venv git

# Create project directory
mkdir -p ~/$PROJECT_DIR
cd ~/$PROJECT_DIR

# Clone repository if not already done
if [ ! -d ".git" ]; then
    echo "Please enter the git repository URL (or leave blank to skip):"
    read REPO_URL
    if [ ! -z "$REPO_URL" ]; then
        git clone $REPO_URL .
    fi
fi

# Create Python virtual environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install Python dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing Python requirements..."
    pip install -r requirements.txt
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "Creating .env file from example..."
    cp .env.example .env
    echo "Please update the .env file with your configuration."
fi

# Setup specific to VM type
if [ "$VM_TYPE" = "kafka" ]; then
    echo "Setting up Kafka VM..."
    
    # Install Docker and Docker Compose
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
        rm get-docker.sh
        
        echo "Docker installed. You may need to log out and log back in for group changes to take effect."
    else
        echo "Docker already installed."
    fi
    
    # Configure firewall for Kafka
    echo "Configuring firewall for Kafka (port 9092)..."
    sudo apt install -y ufw
    sudo ufw allow 22/tcp  # Ensure SSH is allowed
    sudo ufw allow 9092/tcp
    
    echo -e "\nKafka VM setup complete!"
    echo "To start Kafka, run: docker-compose up -d"
    echo "Remember to update the IP address in the generator VM's .env file."
    
elif [ "$VM_TYPE" = "generator" ]; then
    echo "Setting up Generator VM..."
    
    # Ask for Kafka host
    echo "Please enter the Kafka host IP address (default: localhost):"
    read KAFKA_HOST
    KAFKA_HOST=${KAFKA_HOST:-localhost}
    
    # Update .env file with Kafka host
    if [ -f ".env" ]; then
        echo "Updating KAFKA_BOOTSTRAP_SERVERS in .env..."
        sed -i "s/KAFKA_BOOTSTRAP_SERVERS=.*/KAFKA_BOOTSTRAP_SERVERS=$KAFKA_HOST:9092/" .env
    fi
    
    echo -e "\nGenerator VM setup complete!"
    echo "To start the event generator, run: python3 -m src.main"
fi

echo -e "\nSetup complete for $VM_TYPE!"
echo "============================="

if [ "$VM_TYPE" = "kafka" ]; then
    echo "Please log out and log back in for Docker permissions to take effect."
    echo "Then run: docker-compose up -d"
else
    echo "To run the generator: source venv/bin/activate && python3 -m src.main"
fi

echo "=============================" 