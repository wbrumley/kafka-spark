"""
Simplified Spark security events analyzer that doesn't require Kafka.
This generates sample data and analyzes it using Spark.
"""
import os
import logging
import sys
import json
import random
from datetime import datetime, timedelta
import pandas as pd
from termcolor import colored
from tabulate import tabulate
from pyspark.sql import SparkSession

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "simple_spark.log"))
    ]
)
logger = logging.getLogger(__name__)

def create_spark_session():
    """Create a Spark session"""
    try:
        logger.info("Creating Spark session...")
        spark = (SparkSession.builder
                .appName("SecurityEventsSimple")
                .master("local[*]")
                .getOrCreate())
        
        logger.info(f"Spark version: {spark.version}")
        return spark
    except Exception as e:
        logger.error(f"Failed to create Spark session: {e}")
        raise

def generate_sample_events(count=100):
    """Generate sample security events"""
    logger.info(f"Generating {count} sample security events")
    
    events = []
    event_types = ["LOGIN_SUCCESS", "LOGIN_FAILURE", "LOGOUT", "DATA_ACCESS", 
                   "UNAUTHORIZED_ACCESS", "PRIVILEGE_ESCALATION"]
    severities = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
    countries = ["United States", "Brazil", "Germany", "Japan", "India"]
    
    for i in range(count):
        # Weighted random severity (more low severity events)
        severity = random.choices(
            severities, 
            weights=[0.4, 0.3, 0.2, 0.07, 0.03],
            k=1
        )[0]
        
        # Event type with different distributions based on severity
        if severity in ["HIGH", "CRITICAL"]:
            event_type = random.choices(
                event_types,
                weights=[0.1, 0.3, 0.05, 0.15, 0.25, 0.15],
                k=1
            )[0]
        else:
            event_type = random.choices(
                event_types,
                weights=[0.35, 0.15, 0.2, 0.2, 0.05, 0.05],
                k=1
            )[0]
        
        # Generate timestamp within the last hour
        minutes_ago = random.randint(0, 59)
        timestamp = datetime.now() - timedelta(minutes=minutes_ago)
        
        # Create an event
        event = {
            "event_id": f"EVT-{i:06d}",
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "user_id": f"user{random.randint(1, 50):03d}",
            "severity": severity,
            "ip_address": f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}",
            "message": f"Sample {event_type} event",
            "country": random.choice(countries),
            "status_code": random.choice([200, 200, 200, 400, 401, 403, 500])
        }
        
        events.append(event)
    
    return events

def analyze_events(spark, events):
    """Run analysis on the events"""
    logger.info("Analyzing security events...")
    
    # Create a DataFrame from the events
    df = spark.createDataFrame(events)
    
    # Register a temp view for SQL queries
    df.createOrReplaceTempView("security_events")
    
    # Run various analyses
    analyses = {}
    
    # 1. Event type counts
    analyses["event_type_counts"] = spark.sql("""
        SELECT event_type, COUNT(*) as count 
        FROM security_events 
        GROUP BY event_type 
        ORDER BY count DESC
    """)
    
    # 2. High severity events
    analyses["high_severity_events"] = spark.sql("""
        SELECT * FROM security_events 
        WHERE severity IN ('HIGH', 'CRITICAL')
        ORDER BY timestamp DESC
    """)
    
    # 3. Login failures
    analyses["login_failures"] = spark.sql("""
        SELECT user_id, ip_address, COUNT(*) as failure_count
        FROM security_events 
        WHERE event_type = 'LOGIN_FAILURE'
        GROUP BY user_id, ip_address
        HAVING COUNT(*) >= 2
        ORDER BY failure_count DESC
    """)
    
    # 4. Geographic distribution
    analyses["geo_distribution"] = spark.sql("""
        SELECT country, COUNT(*) as count
        FROM security_events
        GROUP BY country
        ORDER BY count DESC
    """)
    
    # 5. Anomalies
    analyses["anomalies"] = spark.sql("""
        SELECT * FROM security_events
        WHERE 
            (event_type IN ('UNAUTHORIZED_ACCESS', 'PRIVILEGE_ESCALATION')) OR
            (severity IN ('HIGH', 'CRITICAL')) OR
            (status_code >= 400)
        ORDER BY timestamp DESC
    """)
    
    return analyses

def display_results(analyses):
    """Display the results in a nice format"""
    # Clear the screen
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("\n" + "="*80)
    print(colored("SECURITY EVENTS ANALYSIS", "cyan", attrs=["bold"]))
    print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # 1. Summary statistics
    total_events = analyses["event_type_counts"].toPandas()["count"].sum()
    high_severity = analyses["high_severity_events"].count()
    login_failures_df = analyses["login_failures"].toPandas()
    login_failures = login_failures_df["failure_count"].sum() if not login_failures_df.empty else 0
    anomalies = analyses["anomalies"].count()
    countries = analyses["geo_distribution"].count()
    
    summary = [
        ["Total Events", total_events],
        ["High Severity Events", colored(str(high_severity), "red", attrs=["bold"]) if high_severity > 0 else 0],
        ["Login Failures", colored(str(login_failures), "yellow", attrs=["bold"]) if login_failures > 0 else 0],
        ["Security Anomalies", colored(str(anomalies), "red", attrs=["bold"]) if anomalies > 0 else 0],
        ["Countries", countries]
    ]
    
    print(tabulate(summary, headers=["Metric", "Value"], tablefmt="simple"))
    
    # 2. Event type breakdown
    print("\n" + "-"*80)
    print(colored("EVENT TYPE BREAKDOWN", "cyan", attrs=["bold"]))
    print("-"*80)
    
    event_types_df = analyses["event_type_counts"].toPandas()
    print(tabulate(event_types_df, headers="keys", tablefmt="psql", showindex=False))
    
    # 3. High severity events
    if high_severity > 0:
        print("\n" + "-"*80)
        print(colored("HIGH SEVERITY EVENTS", "red", attrs=["bold"]))
        print("-"*80)
        
        high_sev_df = analyses["high_severity_events"].toPandas()
        high_sev_df = high_sev_df[["timestamp", "event_type", "severity", "user_id", "message", "ip_address"]]
        high_sev_df = high_sev_df.head(10)  # Limit to 10
        
        print(tabulate(high_sev_df, headers="keys", tablefmt="simple", showindex=False))
    
    # 4. Login failures
    if not login_failures_df.empty:
        print("\n" + "-"*80)
        print(colored("POTENTIAL BRUTE FORCE ATTACKS", "yellow", attrs=["bold"]))
        print("-"*80)
        
        print(tabulate(login_failures_df, headers="keys", tablefmt="simple", showindex=False))
    
    # 5. Geographic distribution
    print("\n" + "-"*80)
    print(colored("GEOGRAPHIC DISTRIBUTION", "cyan", attrs=["bold"]))
    print("-"*80)
    
    geo_df = analyses["geo_distribution"].toPandas()
    print(tabulate(geo_df, headers="keys", tablefmt="simple", showindex=False))

def main():
    """Main function"""
    try:
        # Create Spark session
        spark = create_spark_session()
        
        # Generate sample events
        events = generate_sample_events(count=100)
        
        # Analyze events
        analyses = analyze_events(spark, events)
        
        # Display results
        display_results(analyses)
        
        # Stop Spark session
        logger.info("Stopping Spark session...")
        spark.stop()
        
        logger.info("Analysis completed successfully")
    except Exception as e:
        logger.error(f"Error in analysis: {e}", exc_info=True)
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 
 