#!/bin/bash
# Run the security event generator

set -e  # Exit on any error

echo "===== Starting Security Event Generator ====="

# Create logs directory if it doesn't exist
mkdir -p logs

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    set -a
    source .env
    set +a
fi

# Check for virtual environment and activate or create it
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

# Set or override environment variables
export KAFKA_TOPIC=${KAFKA_TOPIC:-"dev_security_logs"}
export KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-"localhost:9092"}
export EVENT_GENERATION_INTERVAL=${EVENT_GENERATION_INTERVAL:-"1.0"}

# Display configuration for debugging
echo "Configuration:"
echo "KAFKA_BOOTSTRAP_SERVERS: $KAFKA_BOOTSTRAP_SERVERS"
echo "KAFKA_TOPIC: $KAFKA_TOPIC"
echo "EVENT_GENERATION_INTERVAL: $EVENT_GENERATION_INTERVAL"

# Install required dependencies
echo "Installing dependencies..."
pip install -q confluent-kafka python-dotenv pydantic

# Run the security event generator
echo "Starting security event generator..."
echo "Press Ctrl+C to stop"

# Run the generator directly
python src/main.py --generator-only

# If the --generator-only flag doesn't work, try this fallback
# if [ $? -ne 0 ]; then
#     echo "Trying alternative approach..."
#     PYTHONPATH=. python src/generator/event_generator.py
# fi 