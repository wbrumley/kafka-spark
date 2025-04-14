#!/bin/bash
# Script to restructure the Kafka-Spark project
# This will remove redundant files and organize according to the new structure

set -e  # Exit on any error

echo "===== Starting Project Restructuring ====="
echo "This script will reorganize the project and remove unnecessary files."
echo "Creating backup first..."

# Create a backup directory
BACKUP_DIR="kafka-spark-backup-$(date +%Y%m%d%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup all files
echo "Creating backup in $BACKUP_DIR..."
cp -r * "$BACKUP_DIR/" 2>/dev/null || true
cp .env* "$BACKUP_DIR/" 2>/dev/null || true
echo "Backup complete."

echo "===== Creating New Directory Structure ====="

# Create directories if they don't exist
mkdir -p src/{config,generator,kafka} 2>/dev/null || true
mkdir -p spark-apps 2>/dev/null || true
mkdir -p docker 2>/dev/null || true
mkdir -p scripts 2>/dev/null || true
mkdir -p docs 2>/dev/null || true
mkdir -p logs 2>/dev/null || true
mkdir -p jars 2>/dev/null || true

echo "===== Moving Essential Files ====="

# Move Docker files to docker directory
echo "Organizing Docker files..."
mv Dockerfile.* docker/ 2>/dev/null || true
mv docker-compose*.yml docker/ 2>/dev/null || true

# Move run scripts to scripts directory
echo "Organizing run scripts..."
cp run_combined.sh scripts/ 2>/dev/null || true
cp run_dashboard.sh scripts/ 2>/dev/null || true
cp run_with_fresh_setup.sh scripts/ 2>/dev/null || true
cp setup_vm.sh scripts/ 2>/dev/null || true

# Move documentation
echo "Organizing documentation..."
mv README.md docs/ 2>/dev/null || true
mv ARCHITECTURE.md docs/ 2>/dev/null || true

# Create a new README.md in the root directory
cat > README.md << 'EOL'
# Kafka-Spark Security Events Processor

This application processes security events using Kafka and Spark for real-time analytics and monitoring.

## Project Structure

- `src/`: Core source code (event generator, Kafka producer, config)
- `spark-apps/`: Spark application code
- `direct_kafka_spark.py`: Direct Spark processor for Kafka events
- `streamlit_dashboard.py`: Streamlit dashboard
- `docker/`: Docker Compose files and Dockerfiles
- `scripts/`: Run scripts for local development and testing
- `docs/`: Documentation

## Quick Start

1. Use scripts from the scripts/ directory:
   ```
   ./scripts/run_with_fresh_setup.sh
   ```

2. For Docker deployment:
   ```
   cd docker
   docker-compose up
   ```

## Documentation

See the `docs/` directory for complete documentation.
EOL

echo "===== Removing Redundant Files ====="

# List of files to delete
REDUNDANT_FILES=(
  "dashboard.py"
  "fixed_dashboard.py"
  "fixed_dashboard_ui.py"
  "simple_dashboard.py"
  "run_fixed_dashboard.sh"
  "run_simple_dashboard.sh"
  "run_spark_dashboard.sh"
)

# Remove redundant files (only if they exist and after backup)
for file in "${REDUNDANT_FILES[@]}"; do
  if [ -f "$file" ]; then
    echo "Removing redundant file: $file"
    rm "$file"
  fi
done

# Clean up any generated data files
echo "Cleaning up generated data files..."
rm -f dashboard_*.json 2>/dev/null || true
rm -f security_events_*.json 2>/dev/null || true
rm -f *.bak 2>/dev/null || true

echo "===== Creating symlinks for convenience ====="

# Create symlinks in root directory for important scripts
ln -sf scripts/run_with_fresh_setup.sh run_with_fresh_setup.sh
ln -sf scripts/run_combined.sh run_combined.sh
ln -sf scripts/run_dashboard.sh run_dashboard.sh

echo "===== Done! ====="
echo "Project has been restructured. A backup of the original files is in: $BACKUP_DIR"
echo "To run the project:"
echo "  - For local development: ./run_with_fresh_setup.sh"
echo "  - For Docker deployment: cd docker && docker-compose up"
