#!/bin/bash
# Script to run the Docker deployment

cd "$(dirname "$0")/../docker" || exit 1

if [ "$1" == "spark" ]; then
    echo "Starting Kafka-Spark Docker environment..."
    docker-compose -f docker-compose-spark.yml up
else
    echo "Starting basic Kafka Docker environment..."
    docker-compose up
fi 