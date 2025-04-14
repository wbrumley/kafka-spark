#!/bin/bash
# Update paths in scripts to work with new directory structure

set -e  # Exit on any error

echo "===== Updating Script Paths ====="

# Ensure scripts directory exists
mkdir -p scripts

# Function to update a script file
update_script() {
    local script_file="$1"
    local new_location="$2"
    
    if [ -f "$script_file" ]; then
        echo "Updating paths in $script_file..."
        
        # Make sure parent directory exists
        mkdir -p "$(dirname "$new_location")"
        
        # Copy to new location
        cp "$script_file" "$new_location"
        
        # Update Docker paths
        sed -i.bak 's|dockerfile: Dockerfile\.|dockerfile: docker/Dockerfile\.|g' "$new_location" 2>/dev/null || true
        
        # Update relative paths for scripts in the scripts directory
        if [[ "$new_location" == scripts/* ]]; then
            # Go up one directory for scripts in scripts/
            sed -i.bak 's|SCRIPT_DIR=$(dirname "$0")|SCRIPT_DIR=$(dirname "$0")/..|g' "$new_location" 2>/dev/null || true
        fi
        
        # Remove backup file
        rm -f "$new_location.bak" 2>/dev/null || true
    fi
}

# Update docker-compose files
update_script "docker-compose.yml" "docker/docker-compose.yml"
update_script "docker-compose-spark.yml" "docker/docker-compose-spark.yml"

# Update run scripts
update_script "run_combined.sh" "scripts/run_combined.sh"
update_script "run_dashboard.sh" "scripts/run_dashboard.sh"
update_script "run_with_fresh_setup.sh" "scripts/run_with_fresh_setup.sh"
update_script "setup_vm.sh" "scripts/setup_vm.sh"

echo "===== Creating New Scripts ====="

# Create a Docker script to make it easier to run Docker commands
cat > scripts/docker-run.sh << 'EOL'
#!/bin/bash
# Script to run the Docker deployment

cd "$(dirname "$0")/../docker" || exit 1

if [ "$1" == "spark" ]; then
    echo "Starting Kafka-Spark Docker environment..."
    docker-compose -f docker-compose-spark.yml up "$@"
else
    echo "Starting basic Kafka Docker environment..."
    docker-compose up "$@"
fi
EOL
chmod +x scripts/docker-run.sh

# Create symlink in root directory
ln -sf scripts/docker-run.sh docker-run.sh

echo "===== Done Updating Scripts ====="
echo "The scripts have been updated to work with the new directory structure." 