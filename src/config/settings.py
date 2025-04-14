import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'dev_security_logs')

# Generator Configuration
EVENT_GENERATION_INTERVAL = float(os.getenv('EVENT_GENERATION_INTERVAL', '1.0'))  # seconds 