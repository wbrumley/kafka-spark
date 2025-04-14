#!/bin/bash
# Script to test Kafka connection and diagnose issues

set -e

echo "===== Kafka Connection Diagnostic Tool ====="

# Create logs directory if it doesn't exist
mkdir -p logs

# Load environment variables from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env file..."
    set -a
    source .env
    set +a
fi

# Set default values if not provided
KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-"localhost:9092"}
KAFKA_TOPIC=${KAFKA_TOPIC:-"dev_security_logs"}

echo "Testing connection to Kafka at $KAFKA_BOOTSTRAP_SERVERS"
echo "Topic to test: $KAFKA_TOPIC"

# Check if Python virtual environment exists
if [ -d "venv" ]; then
    echo "Activating Python virtual environment..."
    source venv/bin/activate
else
    echo "Creating new Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    
    # Install base dependencies
    pip install --upgrade pip setuptools wheel
fi

# Install required dependencies
echo "Installing dependencies..."
pip install -q confluent-kafka

# Create a Python script to test producer and consumer
echo "Creating test script..."
cat > kafka_test.py << 'EOF'
import sys
import time
from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
import os
import uuid
import json

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}")

def test_producer():
    bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic = os.environ.get("KAFKA_TOPIC", "dev_security_logs")
    
    print(f"\nProducer Test: Connecting to {bootstrap_servers}")
    print(f"Topic: {topic}")
    
    # Create Producer instance
    p = Producer({
        'bootstrap.servers': bootstrap_servers,
        'client.id': 'kafka-test-producer'
    })
    
    # Send 3 test messages
    for i in range(3):
        test_id = str(uuid.uuid4())
        test_message = {
            'event_id': test_id,
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.%fZ', time.gmtime()),
            'event_type': 'TEST_EVENT',
            'message': f'Test message {i+1}',
            'test_run': True
        }
        
        try:
            # Produce message
            p.produce(
                topic=topic,
                key=test_id,
                value=json.dumps(test_message),
                callback=delivery_report
            )
            print(f"Sending: {test_message['message']}")
            
            # Wait for any outstanding messages to be delivered
            p.poll(0)
            
        except BufferError:
            print(f"Local producer queue is full ({len(p)} messages awaiting delivery)")
        
        except Exception as e:
            print(f"Producer error: {e}")
            return False
        
        time.sleep(0.5)
    
    # Wait for all messages to be delivered
    print("Flushing producer...")
    remaining = p.flush(10)
    if remaining > 0:
        print(f"Failed to deliver {remaining} messages")
        return False
    
    print("Producer test completed successfully")
    return True

def test_consumer():
    bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    topic = os.environ.get("KAFKA_TOPIC", "dev_security_logs")
    
    print(f"\nConsumer Test: Connecting to {bootstrap_servers}")
    print(f"Topic: {topic}")
    
    # Create Consumer instance
    c = Consumer({
        'bootstrap.servers': bootstrap_servers,
        'group.id': 'kafka-test-consumer',
        'auto.offset.reset': 'latest',
        'enable.auto.commit': True,
    })
    
    # Subscribe to topic
    c.subscribe([topic])
    
    try:
        print(f"Waiting for messages (10 second timeout)...")
        message_count = 0
        start_time = time.time()
        
        while True:
            if time.time() - start_time > 10:
                print("Timeout: No more messages received in 10 seconds")
                break
            
            msg = c.poll(1.0)
            
            if msg is None:
                continue
            
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    print(f"Reached end of partition")
                else:
                    print(f"Consumer error: {msg.error()}")
                continue
            
            message_count += 1
            try:
                message_data = json.loads(msg.value())
                print(f"Received: {message_data}")
            except:
                print(f"Received: {msg.value()} (not valid JSON)")
            
            if message_count >= 3:
                print(f"Received {message_count} messages, test completed")
                break
                
    except KeyboardInterrupt:
        print("Interrupted")
    
    finally:
        # Close down consumer
        c.close()
    
    if message_count > 0:
        print("Consumer test completed successfully")
        return True
    else:
        print("Consumer test failed: No messages received")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "consumer":
        test_consumer()
    else:
        test_producer()
EOF

echo "Running producer test..."
python kafka_test.py

echo -e "\nWaiting 5 seconds before running consumer test..."
sleep 5

echo "Running consumer test..."
python kafka_test.py consumer

echo -e "\n===== Test Complete ====="
echo "If you're seeing errors, check the following:"
echo "1. Is Kafka running? (Check Docker containers)"
echo "2. Is the KAFKA_BOOTSTRAP_SERVERS value correct in your .env file?"
echo "3. Are there any firewall issues blocking connections?"
echo "4. Are you using the correct topic name?" 