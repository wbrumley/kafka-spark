#!/bin/bash
# AWS Deployment Script for Kafka-Spark Security Analytics
# This script deploys the application to a single EC2 instance

set -e  # Exit on any error

echo "======================================================"
echo "  Kafka-Spark Security Analytics - AWS Deployment"
echo "======================================================"
echo ""

# Configuration - Update these values
EC2_IP="your-ec2-public-ip"      # Replace with your EC2 public IP
KEY_FILE="~/path/to/your-key.pem" # Replace with path to your .pem file
GIT_REPO="your-git-repo-url"     # Replace with your Git repo URL or leave empty to use local files

# Check if key file exists
if [ ! -f "$KEY_FILE" ]; then
    echo "Error: Key file not found at $KEY_FILE"
    echo "Please update the KEY_FILE variable with the correct path to your .pem file"
    exit 1
fi

echo "Step 1: Testing connection to EC2 instance..."
ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no ubuntu@"$EC2_IP" "echo Connection successful!" || {
    echo "Error: Could not connect to EC2 instance"
    echo "Please check your EC2_IP and KEY_FILE variables"
    exit 1
}

echo "Step 2: Setting up EC2 environment..."
ssh -i "$KEY_FILE" ubuntu@"$EC2_IP" << 'EOF'
    # Update system and install dependencies
    echo "Updating system packages..."
    sudo apt-get update
    sudo apt-get upgrade -y
    
    # Install Docker and Docker Compose
    echo "Installing Docker and Docker Compose..."
    sudo apt-get install -y docker.io git
    sudo usermod -aG docker ubuntu
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.17.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    # Verify installations
    docker --version
    docker-compose --version
    
    echo "Environment setup complete!"
EOF

# Step 3: Clone or copy the repository
if [ -n "$GIT_REPO" ]; then
    echo "Step 3: Cloning repository to EC2 instance..."
    ssh -i "$KEY_FILE" ubuntu@"$EC2_IP" << EOF
        git clone "$GIT_REPO" kafka-spark-app
        cd kafka-spark-app
EOF
else
    echo "Step 3: Copying local files to EC2 instance..."
    # Create directory structure
    ssh -i "$KEY_FILE" ubuntu@"$EC2_IP" "mkdir -p kafka-spark-app"
    
    # Copy all files to EC2
    echo "Copying project files to EC2 instance..."
    rsync -avz --exclude 'venv' --exclude '.git' --exclude 'kafka-spark-backup-*' -e "ssh -i $KEY_FILE" ./ ubuntu@"$EC2_IP":kafka-spark-app/
fi

echo "Step 4: Configuring the application..."
ssh -i "$KEY_FILE" ubuntu@"$EC2_IP" << EOF
    cd kafka-spark-app
    
    # Update Kafka configuration to use EC2 public IP
    echo "Updating Kafka configuration..."
    sed -i "s/PLAINTEXT_HOST:\/\/localhost:9092/PLAINTEXT_HOST:\/\/$EC2_IP:9092/g" docker/docker-compose.yml
    
    # Make scripts executable
    chmod +x scripts/*.sh
    
    echo "Configuration complete!"
EOF

echo "Step 5: Starting the application..."
ssh -i "$KEY_FILE" ubuntu@"$EC2_IP" << EOF
    cd kafka-spark-app
    
    # Start the application using Docker Compose
    echo "Starting Docker services..."
    cd docker
    docker-compose up -d
    
    # Check if all services are running
    echo "Checking service status..."
    docker-compose ps
    
    echo "Application started successfully!"
EOF

echo "======================================================"
echo "  Deployment Complete!"
echo "======================================================"
echo ""
echo "Your application is now deployed and running on AWS"
echo ""
echo "Access your services at:"
echo "- Streamlit Dashboard: http://$EC2_IP:8501"
echo "- Kafdrop UI: http://$EC2_IP:8080"
echo "- Spark UI: http://$EC2_IP:4040"
echo ""
echo "To manage your deployment:"
echo "- SSH into your instance: ssh -i $KEY_FILE ubuntu@$EC2_IP"
echo "- Start services: cd kafka-spark-app/docker && docker-compose up -d"
echo "- Stop services: cd kafka-spark-app/docker && docker-compose down"
echo "- View logs: cd kafka-spark-app/docker && docker-compose logs -f"
echo ""
echo "For a demo, you can control the event generator:"
echo "- Start generator: docker-compose -f docker/docker-compose.yml start generator"
echo "- Stop generator: docker-compose -f docker/docker-compose.yml stop generator"
echo "======================================================" 