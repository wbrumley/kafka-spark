# AWS Deployment Guide for Kafka-Spark Security Analytics

This guide walks you through deploying your Kafka-Spark security analytics application to a single AWS EC2 instance.

## Step 1: Set Up AWS EC2 Instance

1. **Log in to AWS Console**
   - Go to https://aws.amazon.com/console/
   - Sign in with your AWS account

2. **Launch EC2 Instance**
   - Navigate to EC2 service
   - Click "Launch Instance"
   - Name your instance (e.g., "Kafka-Spark-Security")

3. **Select Instance Configuration**
   - Choose Amazon Machine Image (AMI): **Ubuntu Server 22.04 LTS**
   - Instance Type: **t2.large** (2 vCPU, 8GB RAM)
   - Key Pair: Create new key pair
     - Name it (e.g., "kafka-spark-key")
     - Download .pem file and keep it secure
   - Network Settings:
     - Allow SSH (port 22)
     - **Add Custom TCP ports**:
       - 8501 (Streamlit)
       - 9092 (Kafka)
       - 8080 (Kafdrop)
       - 4040 (Spark UI)
   - Storage: 30GB gp3 SSD
   - Click "Launch Instance"

4. **Note Important Information**
   - Public IP address
   - Instance ID

## Step 2: Use Deployment Script

1. **Edit the Deployment Script**
   - Open `aws-deploy.sh` in a text editor
   - Update the configuration variables:
     ```bash
     EC2_IP="your-ec2-public-ip"       # Replace with your EC2 public IP
     KEY_FILE="~/path/to/your-key.pem" # Replace with path to your key file
     GIT_REPO=""                       # Leave empty to use local files
     ```

2. **Make the Script Executable**
   ```bash
   chmod +x aws-deploy.sh
   ```

3. **Run the Deployment Script**
   ```bash
   ./aws-deploy.sh
   ```

4. **Monitor Deployment**
   - The script will show progress for each step
   - This might take 5-10 minutes to complete

## Step 3: Verify Deployment

1. **Check Services via Web UIs**
   - Streamlit Dashboard: `http://your-ec2-public-ip:8501`
   - Kafdrop UI: `http://your-ec2-public-ip:8080`
   - Spark UI: `http://your-ec2-public-ip:4040`

2. **SSH into Instance if Needed**
   ```bash
   ssh -i /path/to/your-key.pem ubuntu@your-ec2-public-ip
   ```

3. **Check Docker Containers**
   ```bash
   cd kafka-spark-app/docker
   docker-compose ps
   ```

## Step 4: Demo the Application

1. **Stop Event Generator**
   ```bash
   cd kafka-spark-app/docker
   docker-compose stop generator
   ```

2. **Start Event Generator**
   ```bash
   docker-compose start generator
   ```

3. **View Logs in Real-time**
   ```bash
   docker-compose logs -f
   ```

## Step 5: Manage Your Deployment

1. **Stop All Services**
   ```bash
   cd kafka-spark-app/docker
   docker-compose down
   ```

2. **Start All Services**
   ```bash
   cd kafka-spark-app/docker
   docker-compose up -d
   ```

3. **Stop EC2 Instance When Not in Use (To Save Money)**
   - Go to AWS Console > EC2
   - Select your instance
   - Click "Instance State" > "Stop instance"
   - Start it again when needed

## Troubleshooting

1. **If a service isn't running:**
   ```bash
   docker-compose restart service-name
   ```

2. **To check logs:**
   ```bash
   docker-compose logs -f service-name
   ```

3. **If Kafka isn't accessible:**
   Make sure you updated the `KAFKA_ADVERTISED_LISTENERS` with the correct EC2 public IP.

4. **For other issues:**
   Check the Docker container status and logs for specific error messages.

## Cost Management

- **Always stop your EC2 instance** when not actively using it
- Set up billing alerts in AWS to avoid unexpected charges
- Check AWS Cost Explorer to monitor your spending

## Cleanup

When you're completely done with the project:
1. Terminate your EC2 instance
2. Delete any associated Elastic IPs
3. Delete the security group if not used by other resources 