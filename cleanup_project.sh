#!/bin/bash
# Main script to clean up and restructure the Kafka-Spark project

set -e  # Exit on any error

echo "===== Kafka-Spark Project Cleanup ====="
echo "This script will:"
echo "1. Create a backup of all current files"
echo "2. Restructure the project directories"
echo "3. Remove redundant files"
echo "4. Update scripts to work with the new structure"
echo ""
read -p "Are you sure you want to proceed? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleanup cancelled."
    exit 1
fi

# Run restructuring script
echo ""
echo "Running project restructuring..."
./restructure_project.sh

# Run script update script
echo ""
echo "Updating scripts for new structure..."
./update_scripts.sh

echo ""
echo "===== Project Cleanup Complete ====="
echo "The Kafka-Spark project has been restructured with the following organization:"
echo ""
echo "Directories:"
echo "- src/: Core source code"
echo "- spark-apps/: Spark application code"
echo "- docker/: Docker files"
echo "- scripts/: Run scripts"
echo "- docs/: Documentation"
echo ""
echo "Main Files:"
echo "- streamlit_dashboard.py: The Streamlit dashboard"
echo "- direct_kafka_spark.py: Direct Kafka-Spark processor"
echo ""
echo "To run the application:"
echo "- For local development: ./run_with_fresh_setup.sh"
echo "- For Streamlit dashboard: ./run_dashboard.sh"
echo "- For Docker deployment: ./docker-run.sh"
echo "- For Docker with Spark: ./docker-run.sh spark"
echo ""
echo "See the README.md file for more information." 