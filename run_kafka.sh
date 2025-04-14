#!/bin/bash

# Run the Kafka producer and consumer
# This script can start either the producer, consumer, or both

SCRIPT_DIR=$(dirname "$0")
cd "$SCRIPT_DIR" || exit 1

# Create logs directory if it doesn't exist
mkdir -p logs

# Check if Python virtual environment exists
if [ -d "venv" ]; then
    echo "Activating Python virtual environment..."
    source venv/bin/activate
fi

# Default mode
MODE="producer"

function show_help {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -p, --producer        Run the Kafka producer (default)"
    echo "  -c, --consumer        Run the Kafka consumer"
    echo "  -b, --both            Run both producer and consumer"
    echo "  -h, --help            Show this help message"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--producer)
            MODE="producer"
            shift
            ;;
        -c|--consumer)
            MODE="consumer"
            shift
            ;;
        -b|--both)
            MODE="both"
            shift
            ;;
        -h|--help)
            show_help
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            ;;
    esac
done

# Install required dependencies if needed
echo "Checking dependencies..."
pip install -q confluent-kafka python-dotenv pydantic termcolor tabulate

# Function to run the Kafka producer
run_producer() {
    echo "Starting Kafka producer..."
    echo "Press Ctrl+C to stop"
    echo ""
    python run_kafka_app.py
}

# Function to run the Kafka consumer
run_consumer() {
    echo "Starting Kafka consumer..."
    echo "Press Ctrl+C to stop"
    echo ""
    python run_kafka_consumer.py
}

# Run based on the selected mode
case "$MODE" in
    producer)
        run_producer
        ;;
    consumer)
        run_consumer
        ;;
    both)
        # Run in separate terminals
        if command -v osascript &> /dev/null && [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS: Use AppleScript to open new terminal windows
            osascript -e "tell application \"Terminal\" to do script \"cd $(pwd) && $(which python) run_kafka_app.py\""
            osascript -e "tell application \"Terminal\" to do script \"cd $(pwd) && $(which python) run_kafka_consumer.py\""
            echo "Started producer and consumer in separate terminal windows"
        elif command -v gnome-terminal &> /dev/null; then
            # Linux with GNOME: Use gnome-terminal
            gnome-terminal -- bash -c "cd $(pwd) && python run_kafka_app.py; exec bash"
            gnome-terminal -- bash -c "cd $(pwd) && python run_kafka_consumer.py; exec bash"
            echo "Started producer and consumer in separate terminal windows"
        else
            # Fallback: Run producer in foreground and warn about consumer
            echo "Cannot open multiple terminal windows automatically."
            echo "Running producer in this window. Please run consumer in another window:"
            echo "  ./run_kafka.sh --consumer"
            echo ""
            run_producer
        fi
        ;;
esac 
 