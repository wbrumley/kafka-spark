import time
import logging
import signal
import sys
import json
import argparse
from typing import Optional
from datetime import datetime

# Fix imports to work regardless of directory
try:
    # Try absolute import first (when running from project root)
    from src.config.settings import KAFKA_TOPIC, EVENT_GENERATION_INTERVAL
    from src.generator.event_generator import SecurityEventGenerator
    from src.kafka.producer import KafkaProducer
    from src.generator.models import EventType, Severity
except ModuleNotFoundError:
    # If that fails, try relative imports (when running from src directory)
    from config.settings import KAFKA_TOPIC, EVENT_GENERATION_INTERVAL
    from generator.event_generator import SecurityEventGenerator
    from kafka.producer import KafkaProducer
    from generator.models import EventType, Severity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("security_events.log")
    ]
)
logger = logging.getLogger(__name__)

# Configure a separate logger for high severity events
high_severity_logger = logging.getLogger("high_severity")
high_severity_handler = logging.FileHandler("high_severity_events.log")
high_severity_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
high_severity_logger.addHandler(high_severity_handler)
high_severity_logger.setLevel(logging.WARNING)

# Global flag to control the main loop
running = True

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    global running
    logger.info("Shutdown signal received, stopping generator...")
    running = False

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def get_log_level_from_severity(severity: Severity) -> int:
    """Map severity to log level"""
    severity_map = {
        Severity.INFO: logging.INFO,
        Severity.LOW: logging.INFO,
        Severity.MEDIUM: logging.WARNING,
        Severity.HIGH: logging.ERROR,
        Severity.CRITICAL: logging.CRITICAL
    }
    return severity_map.get(severity, logging.INFO)

def format_event_for_logging(event) -> str:
    """Format event for logging output"""
    event_type = str(event.event_type).replace('EventType.', '')
    tags = ", ".join(event.tags) if event.tags else ""
    
    if hasattr(event, 'geo_location') and event.geo_location:
        location = f"{event.geo_location.city}, {event.geo_location.country}" if event.geo_location.city else event.geo_location.country
    else:
        location = "Unknown"
    
    return (f"{event_type}: User {event.user_id} ({event.user_type}) from {location} | "
            f"IP: {event.ip_address} | Session: {event.session_id or 'N/A'} | "
            f"Status: {event.status_code} | Severity: {event.severity} | Tags: {tags}")

def main():
    """Main function to run the security event generator"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Security Event Generator')
    parser.add_argument('--generator-only', action='store_true', help='Run only the generator without Kafka')
    args = parser.parse_args()
    
    logger.info("Starting security event generator")
    
    # Initialize components
    event_generator = SecurityEventGenerator()
    
    # Only initialize Kafka if not in generator-only mode
    kafka_producer = None if args.generator_only else KafkaProducer()
    
    # Collect some statistics
    stats = {
        "events_generated": 0,
        "by_event_type": {},
        "by_severity": {},
        "by_user_type": {},
        "start_time": datetime.utcnow()
    }
    
    try:
        # Keep track of events generated and last correlation ID
        events_count = 0
        last_correlation_id: Optional[str] = None
        
        if args.generator_only:
            logger.info("Running in generator-only mode (no Kafka)")
        else:
            logger.info(f"Sending events to topic: {KAFKA_TOPIC}")
            
        logger.info(f"Event generation interval: {EVENT_GENERATION_INTERVAL} seconds")
        
        # Main event generation loop
        while running:
            # Generate a new event
            # Every 3-5 events, reuse the last correlation ID to simulate related events
            if last_correlation_id and events_count % 4 == 0:
                event = event_generator.generate_event(correlation_id=last_correlation_id)
                logger.debug(f"Generated related event with correlation ID: {last_correlation_id}")
            else:
                event = event_generator.generate_event()
                last_correlation_id = event.correlation_id
            
            # Update statistics
            stats["events_generated"] += 1
            stats["by_event_type"][str(event.event_type)] = stats["by_event_type"].get(str(event.event_type), 0) + 1
            stats["by_severity"][str(event.severity)] = stats["by_severity"].get(str(event.severity), 0) + 1
            stats["by_user_type"][str(event.user_type)] = stats["by_user_type"].get(str(event.user_type), 0) + 1
            
            # Send to Kafka if not in generator-only mode
            if not args.generator_only and kafka_producer:
                kafka_producer.produce(KAFKA_TOPIC, event)
            
            # Log event details
            log_message = format_event_for_logging(event)
            log_level = get_log_level_from_severity(event.severity)
            logger.log(log_level, log_message)
            
            # Log high severity events separately
            if event.severity in [Severity.HIGH, Severity.CRITICAL]:
                high_severity_logger.log(log_level, log_message)
                
                # Add additional context for high severity events
                detail_message = (f"DETAILS: {event.message} | "
                                 f"Source: {event.source_system} | Target: {event.target_system} | "
                                 f"Additional Info: {json.dumps(event.additional_info)}")
                high_severity_logger.log(log_level, detail_message)
            
            # Print statistics periodically
            if stats["events_generated"] % 100 == 0:
                runtime = (datetime.utcnow() - stats["start_time"]).total_seconds()
                events_per_second = stats["events_generated"] / runtime if runtime > 0 else 0
                logger.info(f"Generated {stats['events_generated']} events ({events_per_second:.2f}/sec)")
                logger.info(f"Event type distribution: {json.dumps({k.replace('EventType.', ''): v for k, v in stats['by_event_type'].items()})}")
                logger.info(f"Severity distribution: {json.dumps(stats['by_severity'])}")
            
            # Increment counter
            events_count += 1
            
            # Wait for the next interval
            time.sleep(EVENT_GENERATION_INTERVAL)
            
    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        # Ensure all messages are sent before exiting
        if not args.generator_only and kafka_producer:
            logger.info("Flushing producer...")
            kafka_producer.flush()
        
        # Print final statistics
        runtime = (datetime.utcnow() - stats["start_time"]).total_seconds()
        events_per_second = stats["events_generated"] / runtime if runtime > 0 else 0
        logger.info(f"Generator stopped after sending {stats['events_generated']} events ({events_per_second:.2f}/sec)")
        logger.info(f"Runtime: {runtime:.2f} seconds")
        logger.info(f"Event type distribution: {json.dumps({k.replace('EventType.', ''): v for k, v in stats['by_event_type'].items()})}")
        logger.info(f"Severity distribution: {json.dumps(stats['by_severity'])}")
        logger.info(f"User type distribution: {json.dumps(stats['by_user_type'])}")

if __name__ == "__main__":
    main()