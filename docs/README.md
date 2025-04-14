# Kafka-Spark Security Events Processor

This application processes security events using Kafka and Spark for real-time analytics and monitoring.

## Project Structure

- `src/`: Core source code (event generator, Kafka producer, config)
- `spark-apps/`: Spark application code
- `direct_kafka_spark.py`: Direct Spark processor for Kafka events
- `streamlit_dashboard.py`: Streamlit dashboard
- `docker/`: Docker Compose files and Dockerfiles
- `scripts/`: Run scripts for local development and testing
- `docs/`: Documentation

## Quick Start

1. Use scripts from the scripts/ directory:
   ```
   ./scripts/run_with_fresh_setup.sh
   ```

2. For Docker deployment:
   ```
   cd docker
   docker-compose up
   ```

## Documentation

See the `docs/` directory for complete documentation.
