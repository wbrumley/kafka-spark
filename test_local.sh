#!/bin/bash
# Local Testing Script for Kafka-Spark Security Analytics Project

set -e  # Exit on errors

echo "=================================================="
echo "  Kafka-Spark Security Analytics - Local Testing"
echo "=================================================="
echo ""

# Create a function to check for required dependencies
check_dependencies() {
  echo "Checking for required dependencies..."
  
  # Check for Python
  if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
  fi
  
  # Check for Java
  if ! command -v java &> /dev/null; then
    echo "Error: Java is required but not installed."
    exit 1
  fi
  
  echo "All required dependencies are installed."
}

# Function to present options menu
show_menu() {
  echo ""
  echo "Choose an option to test locally:"
  echo "1) Run complete setup (generator + processor + dashboard)"
  echo "2) Run just the security event generator"
  echo "3) Run just the Kafka-Spark processor"
  echo "4) Run just the dashboard"
  echo "5) Exit"
  echo ""
  read -p "Enter your choice (1-5): " choice
  
  case $choice in
    1)
      run_complete_setup
      ;;
    2)
      run_generator
      ;;
    3)
      run_processor
      ;;
    4)
      run_dashboard
      ;;
    5)
      echo "Exiting..."
      exit 0
      ;;
    *)
      echo "Invalid choice. Please try again."
      show_menu
      ;;
  esac
}

# Function to run the complete setup
run_complete_setup() {
  echo "Starting complete setup (generator + processor + dashboard)..."
  if [ -f "./run_with_fresh_setup.sh" ]; then
    ./run_with_fresh_setup.sh
  else
    ./scripts/run_with_fresh_setup.sh
  fi
}

# Function to run just the generator
run_generator() {
  echo "Starting just the security event generator..."
  
  # Create Python virtual environment if it doesn't exist
  if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
  fi
  
  # Activate virtual environment
  source venv/bin/activate
  
  # Install required dependencies
  echo "Installing dependencies..."
  pip install -q confluent-kafka python-dotenv pydantic
  
  # Run the generator
  echo "Running security event generator..."
  echo "Press Ctrl+C to stop"
  python src/main.py --generator-only
}

# Function to run just the processor
run_processor() {
  echo "Starting just the Kafka-Spark processor..."
  if [ -f "./run_combined.sh" ]; then
    ./run_combined.sh
  else
    ./scripts/run_combined.sh
  fi
}

# Function to run just the dashboard
run_dashboard() {
  echo "Starting just the dashboard..."
  if [ -f "./run_dashboard.sh" ]; then
    ./run_dashboard.sh
  else
    ./scripts/run_dashboard.sh
  fi
}

# Main execution
check_dependencies
show_menu 