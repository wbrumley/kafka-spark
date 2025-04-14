# System Architecture

## Overview

This project implements a real-time security log stream analysis system using Kafka and optional Spark processing. The system generates synthetic security event data, sends it to Kafka topics, and provides options for analyzing the stream in real-time.

## Components

The system consists of the following main components:

1. **Event Generator** - Python application that creates synthetic security events
2. **Kafka Cluster** - Message broker for streaming events
3. **Consumer Applications** - Applications that process the security events (including optional Spark)

## Architecture Diagram

```
                     ┌───────────────────┐
                     │                   │
                     │  Event Generator  │
                     │                   │
                     └─────────┬─────────┘
                               │
                               │ Security Events
                               │ (JSON)
                               ▼
┌───────────────────────────────────────────────────┐
│                                                   │
│                   Kafka Cluster                   │
│                                                   │
│  ┌─────────────┐      ┌─────────────────────┐    │
│  │             │      │                     │    │
│  │  Zookeeper  │◄────►│  Kafka Broker(s)    │    │
│  │             │      │                     │    │
│  └─────────────┘      └──────────┬──────────┘    │
│                                  │               │
└──────────────────────────────────┼───────────────┘
                                   │
                                   │ Consume Events
                                   │
                                   ▼
                     ┌───────────────────────┐
                     │                       │
                     │   Kafka Consumers     │
                     │                       │
                     └──┬──────────────────┬─┘
                        │                  │
                        │                  │
                        ▼                  ▼
            ┌──────────────────┐  ┌─────────────────┐
            │                  │  │                 │
            │ Simple Consumer  │  │ Spark Streaming │
            │ (Optional)       │  │ (Optional)      │
            │                  │  │                 │
            └──────────────────┘  └─────────────────┘
```

## Data Flow

1. The Event Generator creates synthetic security events (login success/failure, unauthorized access)
2. Events are serialized to JSON format and sent to Kafka topics
3. Kafka brokers store and distribute the events to consumers
4. Consumers process the events in real-time (logging, analysis, alerting)

## Deployment Architecture (Cloud)

```
┌───────────────────────────────────────────┐
│                                           │
│  VM1: Kafka Server                        │
│                                           │
│  ┌───────────────┐    ┌───────────────┐  │
│  │               │    │               │  │
│  │   Zookeeper   │    │     Kafka     │  │
│  │   (Docker)    │    │    (Docker)   │  │
│  │               │    │               │  │
│  └───────────────┘    └───────────────┘  │
│                                           │
└─────────────────┬─────────────────────────┘
                  │
                  │ Network
                  │ Connection
                  │
┌─────────────────▼─────────────────────────┐
│                                           │
│  VM2: Generator                           │
│                                           │
│  ┌───────────────────────────────────┐   │
│  │                                   │   │
│  │      Security Event Generator     │   │
│  │      Python Application           │   │
│  │                                   │   │
│  └───────────────────────────────────┘   │
│                                           │
└───────────────────────────────────────────┘
```

## Key Technologies

- **Python**: Core programming language
- **Kafka**: Distributed event streaming platform
- **Docker**: Containerization for Kafka deployment
- **Pydantic**: Data validation and settings management
- **Faker**: Synthetic data generation
- **Optional: Apache Spark**: For advanced stream processing

## Scalability and Extension

The system is designed to be modular and scalable:

1. Kafka allows horizontal scaling by adding more brokers
2. Multiple generators can run in parallel for higher event rates
3. Multiple consumers can process events for different purposes
4. Spark integration allows complex analytics at scale 