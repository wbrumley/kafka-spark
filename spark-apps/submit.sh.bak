#!/bin/bash

# Submit script for running the security events processor

echo "Starting Spark Submit for Security Events Processor"
echo "SPARK_MASTER: $SPARK_MASTER"
echo "KAFKA_BOOTSTRAP_SERVERS: $KAFKA_BOOTSTRAP_SERVERS"
echo "KAFKA_TOPIC: $KAFKA_TOPIC"

# Ensure checkpoint directory exists
mkdir -p /opt/spark/data/checkpoints

# Submit the Spark job
/opt/bitnami/spark/bin/spark-submit \
  --master ${SPARK_MASTER} \
  --name "SecurityEventsProcessor" \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1 \
  --conf spark.sql.adaptive.enabled=true \
  --conf spark.sql.shuffle.partitions=2 \
  --conf spark.driver.memory=1g \
  --conf spark.executor.memory=1g \
  /opt/spark/apps/security_events_processor.py

# If the application exits, keep the container running to inspect logs
echo "Spark job exited, container will sleep for debugging purposes"
tail -f /dev/null 