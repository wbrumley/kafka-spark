import json
import logging
import socket
import os
from datetime import datetime
from typing import Any, Dict, Optional
from confluent_kafka import Producer
from termcolor import colored
from tabulate import tabulate

# Fix imports to work regardless of directory
try:
    # Try absolute import first (when running from project root)
    from src.config.settings import KAFKA_BOOTSTRAP_SERVERS
except ModuleNotFoundError:
    # If that fails, try relative imports (when running from src directory)
    import sys
    import os
    # Add parent directory to path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from src.config.settings import KAFKA_BOOTSTRAP_SERVERS

from src.generator.models import SecurityEvent, EventType, Severity

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "producer.log"))
    ]
)
logger = logging.getLogger(__name__)

class KafkaProducer:
    """
    Kafka producer for security events
    """
    def __init__(self):
        """
        Initialize the Kafka producer with configuration
        """
        self.producer = Producer({
            'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
            'client.id': 'security-events-producer',
            'acks': 'all',
            'retries': 5,
            'retry.backoff.ms': 500
        })
        
        # Log the bootstrap servers for debugging
        logger.info(f"Kafka producer initialized with bootstrap servers: {KAFKA_BOOTSTRAP_SERVERS}")
        
        # Track delivered messages
        self.delivered_records = 0
        self.failed_records = 0
        
        # Initialize statistics
        self.stats = {
            "messages_sent": 0,
            "delivery_success": 0,
            "delivery_failed": 0,
            "by_event_type": {},
            "by_severity": {},
            "by_user_type": {},
            "start_time": datetime.utcnow(),
        }
    
    def get_color_for_event_type(self, event_type: str) -> str:
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
    
    def get_color_for_severity(self, severity: str) -> str:
        """Return color based on severity level"""
        severity_colors = {
            "INFO": "green",
            "LOW": "blue", 
            "MEDIUM": "yellow",
            "HIGH": "red",
            "CRITICAL": "magenta"
        }
        return severity_colors.get(severity, "white")
    
    def format_event_display(self, event: SecurityEvent) -> None:
        """Format and print event details in a readable way for console output"""
        # Extract key fields
        event_type = str(event.event_type).replace('EventType.', '')
        severity = str(event.severity).replace('Severity.', '')
        timestamp = event.timestamp.isoformat() + "Z"
        
        # Get location information
        location = "Unknown"
        if event.geo_location:
            location = f"{event.geo_location.city}, {event.geo_location.country}" if event.geo_location.city else event.geo_location.country
        
        # Print header with colors
        event_type_color = self.get_color_for_event_type(event_type)
        severity_color = self.get_color_for_severity(severity)
        
        print("\n" + "-"*80)
        print(colored(f"PRODUCING: {event_type}", event_type_color, attrs=['bold']) + 
              " | " + colored(f"SEVERITY: {severity}", severity_color, attrs=['bold']) +
              f" | {timestamp}")
        
        # Basic event information in a table format
        basic_info = [
            ["Event ID", event.event_id],
            ["User", f"{event.user_id} ({event.user_type})"],
            ["Message", event.message],
            ["Location", location],
            ["IP Address", event.ip_address]
        ]
        
        print(tabulate(basic_info, tablefmt="simple"))
        print("-"*80)
    
    def delivery_report(self, err: Any, msg: Any) -> None:
        """
        Callback for delivery reports with enhanced statistics tracking
        """
        if err is not None:
            self.stats["delivery_failed"] += 1
            logger.error(f"Message delivery failed: {err}")
        else:
            self.stats["delivery_success"] += 1
            
            # Extract event type from headers for statistics
            event_type = None
            if msg.headers():
                for key, value in msg.headers():
                    if key == "event-type" and value:
                        event_type = value.decode('utf-8')
            
            logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}")
            
            # Log periodic statistics
            if self.stats["messages_sent"] > 0 and self.stats["messages_sent"] % 50 == 0:
                self.log_statistics()
    
    def log_statistics(self) -> None:
        """Log current producer statistics"""
        runtime = (datetime.utcnow() - self.stats["start_time"]).total_seconds()
        messages_per_second = self.stats["messages_sent"] / runtime if runtime > 0 else 0
        success_rate = (self.stats["delivery_success"] / self.stats["messages_sent"]) * 100 if self.stats["messages_sent"] > 0 else 0
        
        logger.info(f"Producer Statistics:")
        logger.info(f"Total messages sent: {self.stats['messages_sent']} ({messages_per_second:.2f} msgs/sec)")
        logger.info(f"Delivery success rate: {success_rate:.2f}% ({self.stats['delivery_success']}/{self.stats['messages_sent']})")
        logger.info(f"Runtime: {runtime:.2f} seconds")
        
        # Log top event types
        if self.stats["by_event_type"]:
            event_counts = sorted(self.stats["by_event_type"].items(), key=lambda x: x[1], reverse=True)[:3]
            logger.info("Top event types: " + ", ".join([f"{e[0].replace('EventType.', '')}: {e[1]}" for e in event_counts]))
        
        # Log severity distribution
        if self.stats["by_severity"]:
            severity_counts = self.stats["by_severity"]
            logger.info("Severity distribution: " + ", ".join(
                [f"{s}: {severity_counts.get(s, 0)}" for s in ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]]
            ))
    
    def produce(self, topic: str, event: SecurityEvent) -> None:
        """
        Produce a security event to a Kafka topic with enhanced tracking and formatting
        """
        try:
            # Update statistics
            self.stats["messages_sent"] += 1
            event_type_str = str(event.event_type)
            severity_str = str(event.severity)
            user_type_str = str(event.user_type)
            
            self.stats["by_event_type"][event_type_str] = self.stats["by_event_type"].get(event_type_str, 0) + 1
            self.stats["by_severity"][severity_str] = self.stats["by_severity"].get(severity_str, 0) + 1
            self.stats["by_user_type"][user_type_str] = self.stats["by_user_type"].get(user_type_str, 0) + 1
            
            # Print formatted event
            self.format_event_display(event)
            
            # Convert Pydantic model to dictionary
            event_dict = event.model_dump()
            
            # Convert datetime to string
            event_dict["timestamp"] = event_dict["timestamp"].isoformat() + "Z"
            
            # Convert to JSON string
            event_json = json.dumps(event_dict)
            
            # Enhanced headers
            headers = [
                ("schema-version", b"1.0.0"),
                ("event-type", str(event.event_type).encode()),
                ("severity", str(event.severity).encode()),
                ("source", event.source_system.encode() if event.source_system else b"unknown"),
                ("timestamp", str(event.timestamp.timestamp()).encode()),
                ("correlation-id", event.correlation_id.encode() if event.correlation_id else b"")
            ]
            
            # Produce message
            self.producer.produce(
                topic=topic,
                key=event.user_id.encode(),  # Using user_id as the key
                value=event_json.encode(),
                headers=headers,
                callback=self.delivery_report
            )
            
            # Serve delivery callbacks from previous produce calls
            self.producer.poll(0)
            
        except Exception as e:
            logger.error(f"Error producing message: {e}")
    
    def flush(self, timeout: Optional[float] = None) -> None:
        """
        Flush the producer to ensure all messages are sent
        """
        logger.info("Flushing producer...")
        # Fix: provide a default timeout if None is passed
        actual_timeout = 5.0 if timeout is None else timeout
        remaining = self.producer.flush(actual_timeout)
        if remaining > 0:
            logger.warning(f"Failed to flush {remaining} messages after timeout")
        else:
            logger.info("All messages flushed successfully")
            
        # Final statistics log
        self.log_statistics()