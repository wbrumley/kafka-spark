import json
import logging
import signal
import sys
import os
from datetime import datetime
from confluent_kafka import Consumer, KafkaError
from termcolor import colored
from tabulate import tabulate

from src.config.settings import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC
from src.generator.models import EventType, Severity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "consumer.log"))
    ]
)
logger = logging.getLogger(__name__)

# Global flag to control the consumer loop
running = True

# Statistics tracking
stats = {
    "messages_received": 0,
    "by_event_type": {},
    "by_severity": {},
    "by_user_type": {},
    "start_time": datetime.utcnow(),
    "errors": 0
}

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    global running
    logger.info("Shutdown signal received, stopping consumer...")
    running = False

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_color_for_event_type(event_type: str) -> str:
    """Return color based on event type category"""
    if any(auth_type in event_type for auth_type in ["LOGIN_SUCCESS", "LOGOUT"]):
        return "green"
    elif any(alert_type in event_type for alert_type in ["LOGIN_FAILURE", "ACCOUNT_LOCKOUT", "MFA_CHALLENGE"]):
        return "yellow"
    elif any(threat_type in event_type for threat_type in ["UNAUTHORIZED", "PRIVILEGE", "DATA_EXFILTRATION"]):
        return "red"
    elif any(data_type in event_type for data_type in ["DATA_"]):
        return "blue"
    elif any(system_type in event_type for system_type in ["SYSTEM_", "CONFIG_"]):
        return "cyan"
    else:
        return "white"

def get_color_for_severity(severity: str) -> str:
    """Return color based on severity level"""
    severity_colors = {
        "INFO": "green",
        "LOW": "blue",
        "MEDIUM": "yellow",
        "HIGH": "red",
        "CRITICAL": "magenta"
    }
    return severity_colors.get(severity, "white")

def format_event(event: dict) -> None:
    """Format and print event details in a readable way"""
    # Extract key fields
    event_type = event.get('event_type', '').replace('EventType.', '')
    severity = event.get('severity', '')
    user_id = event.get('user_id', '')
    user_type = event.get('user_type', '')
    timestamp = event.get('timestamp', '')
    message = event.get('message', '')
    ip_address = event.get('ip_address', '')
    status_code = event.get('status_code', '')
    
    # Get location information if available
    geo = event.get('geo_location', {})
    location = f"{geo.get('city', '')}, {geo.get('country', '')}" if geo and geo.get('city') else geo.get('country', 'Unknown')
    
    # Get tags information
    tags = ", ".join(event.get('tags', []))
    
    # Print header
    event_type_color = get_color_for_event_type(event_type)
    severity_color = get_color_for_severity(severity)
    
    print("\n" + "="*80)
    print(colored(f"EVENT: {event_type}", event_type_color, attrs=['bold']) + 
          " | " + colored(f"SEVERITY: {severity}", severity_color, attrs=['bold']) +
          f" | {timestamp}")
    print("-"*80)
    
    # Basic event information in a table format
    basic_info = [
        ["User", f"{user_id} ({user_type})"],
        ["Message", message],
        ["Status", status_code],
        ["Location", location],
        ["IP Address", ip_address],
        ["Tags", tags]
    ]
    
    print(tabulate(basic_info, tablefmt="plain"))
    
    # Additional details section if available
    additional_info = event.get('additional_info', {})
    if additional_info:
        print("\nAdditional Details:")
        details_rows = []
        for key, value in additional_info.items():
            details_rows.append([key.replace('_', ' ').title(), value])
        print(tabulate(details_rows, tablefmt="plain"))
    
    # Print system info if relevant
    if event.get('source_system') or event.get('target_system'):
        print(f"\nSystems: {event.get('source_system', 'Unknown')} → {event.get('target_system', 'Unknown')}")
    
    print("="*80)

def main():
    """Simple Kafka consumer to verify messages"""
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    logger.info(f"Starting Kafka consumer for topic: {KAFKA_TOPIC}")
    
    # Configure consumer
    consumer_config = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': 'security-logs-consumer',
        'auto.offset.reset': 'latest',  # Start from latest messages
        'enable.auto.commit': True,
    }
    
    # Create consumer
    consumer = Consumer(consumer_config)
    
    try:
        # Subscribe to topic
        consumer.subscribe([KAFKA_TOPIC])
        logger.info(f"Subscribed to topic: {KAFKA_TOPIC}")
        
        # Main consumer loop
        while running:
            # Poll for messages
            msg = consumer.poll(timeout=1.0)
            
            if msg is None:
                continue
                
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.debug(f"Reached end of partition: {msg.topic()} [{msg.partition()}]")
                else:
                    logger.error(f"Error: {msg.error()}")
                    stats["errors"] += 1
            else:
                # Parse message value as JSON
                try:
                    value = json.loads(msg.value().decode('utf-8'))
                    
                    # Extract headers if available
                    headers = {}
                    if msg.headers():
                        headers = {k: v.decode('utf-8') if v else None for k, v in msg.headers()}
                    
                    # Update statistics
                    stats["messages_received"] += 1
                    event_type = value.get('event_type', '')
                    severity = value.get('severity', '')
                    user_type = value.get('user_type', '')
                    
                    stats["by_event_type"][event_type] = stats["by_event_type"].get(event_type, 0) + 1
                    stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
                    stats["by_user_type"][user_type] = stats["by_user_type"].get(user_type, 0) + 1
                    
                    # Format and display the event
                    format_event(value)
                    
                    # Print periodic statistics
                    if stats["messages_received"] % 20 == 0:
                        runtime = (datetime.utcnow() - stats["start_time"]).total_seconds()
                        messages_per_second = stats["messages_received"] / runtime if runtime > 0 else 0
                        
                        print("\nConsumer Statistics:")
                        print(f"Total messages: {stats['messages_received']} ({messages_per_second:.2f} msgs/sec)")
                        print(f"Runtime: {runtime:.2f} seconds")
                        print(f"Error count: {stats['errors']}")
                        
                        # Print top 3 event types
                        event_counts = sorted(stats["by_event_type"].items(), key=lambda x: x[1], reverse=True)[:3]
                        print("Top event types:", ", ".join([f"{e[0].replace('EventType.', '')}: {e[1]}" for e in event_counts]))
                        
                        # Print severity distribution
                        severity_counts = stats["by_severity"]
                        print("Severity distribution:", ", ".join([f"{s}: {severity_counts.get(s, 0)}" for s in ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]]))
                        
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    stats["errors"] += 1
                    
    except Exception as e:
        logger.error(f"Consumer error: {e}")
    finally:
        # Display final statistics
        runtime = (datetime.utcnow() - stats["start_time"]).total_seconds()
        messages_per_second = stats["messages_received"] / runtime if runtime > 0 else 0
        
        print("\nFinal Consumer Statistics:")
        print(f"Total messages: {stats['messages_received']} ({messages_per_second:.2f} msgs/sec)")
        print(f"Runtime: {runtime:.2f} seconds")
        print(f"Error count: {stats['errors']}")
        
        # Close consumer
        consumer.close()
        logger.info("Consumer closed")

if __name__ == "__main__":
    main() 