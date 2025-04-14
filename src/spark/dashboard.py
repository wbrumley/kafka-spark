import os
import logging
import time
import sys
from datetime import datetime
import subprocess
from typing import Dict, Any, List, Optional

# Configure logging first
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join("logs", "spark_dashboard.log"))
    ]
)
logger = logging.getLogger(__name__)

# Check for proper numpy/pandas compatibility
try:
    import numpy as np
    logger.info(f"NumPy version: {np.__version__}")
    
    import pandas as pd
    logger.info(f"Pandas version: {pd.__version__}")
    
    # Check for successful import
    test_df = pd.DataFrame({'a': [1, 2, 3]})
    logger.info("Pandas test successful")
    
except ImportError as e:
    logger.error(f"Error importing dependencies: {e}")
    logger.error("Try: pip install numpy==1.24.3 pandas==2.0.3")
    sys.exit(1)
except ValueError as e:
    logger.error(f"Compatibility error: {e}")
    logger.error("NumPy and Pandas versions are incompatible.")
    logger.error("Fix with: pip uninstall -y numpy pandas && pip install numpy==1.24.3 pandas==2.0.3")
    sys.exit(1)
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    sys.exit(1)

# Now try to import Spark components
try:
    from tabulate import tabulate
    from termcolor import colored
    from src.spark.session import create_spark_session, stop_spark_session
except ImportError as e:
    logger.error(f"Error importing Spark modules: {e}")
    logger.error("Please make sure all dependencies are installed: pip install pyspark tabulate termcolor")
    sys.exit(1)

# Check for Java installation
def check_java():
    """Check if Java is installed and properly configured"""
    try:
        result = subprocess.run(
            ['java', '-version'], 
            capture_output=True, 
            text=True,
            check=False
        )
        if result.returncode != 0:
            logger.error("Java is not installed or not in PATH. Spark requires Java.")
            logger.error(f"Error: {result.stderr}")
            return False
        
        # Extract Java version
        version_line = result.stderr.split('\n')[0]
        logger.info(f"Found Java: {version_line}")
        return True
    except Exception as e:
        logger.error(f"Error checking Java: {e}")
        return False

# Check for Java
if not check_java():
    logger.error("Java check failed. Spark requires Java 8 or later.")
    logger.error("Please install Java and make sure it's in your PATH.")
    sys.exit(1)

class SparkDashboard:
    """Interactive dashboard for Spark security analytics"""
    
    def __init__(self, update_interval: int = 5):
        """
        Initialize the dashboard
        
        Args:
            update_interval: Interval in seconds between updates
        """
        self.update_interval = update_interval
        self.spark = None
        self.running = True
        self.start_time = datetime.now()
        
        # Create logs directory if it doesn't exist
        os.makedirs("logs", exist_ok=True)
        
        # Statistics
        self.stats = {
            "event_count_total": 0,
            "high_severity_count": 0,
            "login_failures": 0,
            "anomalies_detected": 0,
            "countries_seen": set(),
            "last_update": None
        }
    
    def initialize_spark(self) -> None:
        """Initialize Spark session"""
        logger.info("Initializing Spark session for dashboard")
        try:
            self.spark = create_spark_session("SecurityEventsDashboard")
            logger.info(f"Spark session created: {self.spark.version}")
        except Exception as e:
            logger.error(f"Failed to create Spark session: {e}")
            raise
    
    def get_dataframe_from_table(self, table_name: str) -> Optional[pd.DataFrame]:
        """
        Get pandas DataFrame from Spark table
        
        Args:
            table_name: Name of the in-memory table
            
        Returns:
            pandas DataFrame or None if table doesn't exist
        """
        try:
            # Check if table exists
            tables = [t.name for t in self.spark.catalog.listTables()]
            if table_name not in tables:
                return None
            
            # Get DataFrame and convert to pandas
            spark_df = self.spark.table(table_name)
            if spark_df.count() == 0:
                return pd.DataFrame()
                
            # For non-aggregated tables (append mode), sort by timestamp for latest events
            if table_name in ["high_severity_events", "security_anomalies"]:
                if "event_timestamp" in spark_df.columns:
                    spark_df = spark_df.orderBy("event_timestamp", ascending=False)
            
            return spark_df.toPandas()
        except Exception as e:
            logger.error(f"Error getting data from table {table_name}: {e}")
            return None
    
    def get_all_tables_data(self) -> Dict[str, pd.DataFrame]:
        """Get all in-memory tables data as pandas DataFrames"""
        result = {}
        try:
            tables = [t.name for t in self.spark.catalog.listTables()]
            for table in tables:
                result[table] = self.get_dataframe_from_table(table)
        except Exception as e:
            logger.error(f"Error listing tables: {e}")
        
        return result
    
    def update_statistics(self, dataframes: Dict[str, pd.DataFrame]) -> None:
        """Update dashboard statistics based on data"""
        # Check if we have data
        if not dataframes:
            return
            
        # Get event counts
        if "event_type_counts" in dataframes and dataframes["event_type_counts"] is not None:
            df = dataframes["event_type_counts"]
            if not df.empty:
                self.stats["event_count_total"] = df["count"].sum()
        
        # Get high severity events
        if "high_severity_events" in dataframes and dataframes["high_severity_events"] is not None:
            df = dataframes["high_severity_events"]
            if not df.empty:
                self.stats["high_severity_count"] = len(df)
        
        # Get login failures
        if "login_failures" in dataframes and dataframes["login_failures"] is not None:
            df = dataframes["login_failures"]
            if not df.empty:
                self.stats["login_failures"] = df["failure_count"].sum()
        
        # Get security anomalies
        if "security_anomalies" in dataframes and dataframes["security_anomalies"] is not None:
            df = dataframes["security_anomalies"]
            if not df.empty:
                self.stats["anomalies_detected"] = len(df)
        
        # Get geographic data
        if "geo_distribution" in dataframes and dataframes["geo_distribution"] is not None:
            df = dataframes["geo_distribution"]
            if not df.empty and "country" in df:
                self.stats["countries_seen"].update(df["country"].unique())
        
        # Update timestamp
        self.stats["last_update"] = datetime.now()
    
    def print_summary_statistics(self) -> None:
        """Print summary statistics"""
        runtime = (datetime.now() - self.start_time).total_seconds()
        hours, remainder = divmod(runtime, 3600)
        minutes, seconds = divmod(remainder, 60)
        runtime_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
        
        # Clear screen and print header
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n" + "="*80)
        print(colored("SECURITY EVENTS DASHBOARD", "cyan", attrs=["bold"]))
        print(f"Runtime: {runtime_str} | Last Update: {self.stats['last_update'].strftime('%H:%M:%S') if self.stats['last_update'] else 'Never'}")
        print("="*80)
        
        # Print summary
        summary = [
            ["Total Events", self.stats["event_count_total"]],
            ["High Severity Events", colored(str(self.stats["high_severity_count"]), "red", attrs=["bold"]) if self.stats["high_severity_count"] > 0 else 0],
            ["Login Failures", colored(str(self.stats["login_failures"]), "yellow", attrs=["bold"]) if self.stats["login_failures"] > 0 else 0],
            ["Security Anomalies", colored(str(self.stats["anomalies_detected"]), "red", attrs=["bold"]) if self.stats["anomalies_detected"] > 0 else 0],
            ["Countries", len(self.stats["countries_seen"])]
        ]
        print(tabulate(summary, headers=["Metric", "Value"], tablefmt="simple"))
    
    def print_event_type_breakdown(self, dataframes: Dict[str, pd.DataFrame]) -> None:
        """Print event type breakdown"""
        if "event_type_counts" not in dataframes or dataframes["event_type_counts"] is None or dataframes["event_type_counts"].empty:
            print("\nNo event type data available yet")
            return
            
        df = dataframes["event_type_counts"]
        
        # Aggregate by event type
        event_type_summary = df.groupby("event_type")["count"].sum().reset_index()
        event_type_summary = event_type_summary.sort_values("count", ascending=False)
        
        # Set limit to top 10
        if len(event_type_summary) > 10:
            event_type_summary = event_type_summary.head(10)
        
        print("\n" + "-"*80)
        print(colored("EVENT TYPE BREAKDOWN (Top 10)", "cyan", attrs=["bold"]))
        print("-"*80)
        
        # Format data for display
        data = []
        for _, row in event_type_summary.iterrows():
            event_type = row["event_type"].replace("EventType.", "")
            count = row["count"]
            data.append([event_type, count])
        
        print(tabulate(data, headers=["Event Type", "Count"], tablefmt="simple"))
    
    def print_high_severity_events(self, dataframes: Dict[str, pd.DataFrame]) -> None:
        """Print high severity events"""
        if "high_severity_events" not in dataframes or dataframes["high_severity_events"] is None or dataframes["high_severity_events"].empty:
            print("\nNo high severity events detected yet")
            return
            
        df = dataframes["high_severity_events"]
        
        # Limit to most recent 10 (already sorted in get_dataframe_from_table)
        if len(df) > 10:
            df = df.head(10)
        
        print("\n" + "-"*80)
        print(colored("RECENT HIGH SEVERITY EVENTS", "red", attrs=["bold"]))
        print("-"*80)
        
        # Format data for display
        data = []
        for _, row in df.iterrows():
            timestamp = pd.to_datetime(row["event_timestamp"]).strftime("%H:%M:%S")
            event_type = row["event_type"].replace("EventType.", "")
            severity = row["severity"].replace("Severity.", "")
            user = row["user_id"]
            message = row["message"]
            data.append([
                timestamp, 
                colored(event_type, "red"), 
                colored(severity, "red" if severity == "CRITICAL" else "yellow"),
                user,
                message
            ])
        
        print(tabulate(data, headers=["Time", "Event Type", "Severity", "User", "Message"], tablefmt="simple"))
    
    def print_potential_attacks(self, dataframes: Dict[str, pd.DataFrame]) -> None:
        """Print potential attacks (login failures)"""
        if "login_failures" not in dataframes or dataframes["login_failures"] is None or dataframes["login_failures"].empty:
            print("\nNo potential brute force attacks detected yet")
            return
            
        df = dataframes["login_failures"]
        
        # Limit to top 10 by failure count
        if len(df) > 10:
            df = df.sort_values("failure_count", ascending=False).head(10)
        
        print("\n" + "-"*80)
        print(colored("POTENTIAL BRUTE FORCE ATTACKS", "yellow", attrs=["bold"]))
        print("-"*80)
        
        # Format data for display
        data = []
        for _, row in df.iterrows():
            window_start = pd.to_datetime(row["window_start"]).strftime("%H:%M:%S")
            window_end = pd.to_datetime(row["window_end"]).strftime("%H:%M:%S")
            user = row["user_id"]
            ip = row["ip_address"]
            failures = row["failure_count"]
            
            # Color code based on failure count
            failure_color = "yellow"
            if failures >= 10:
                failure_color = "red"
            elif failures >= 5:
                failure_color = "yellow"
                
            data.append([
                f"{window_start} - {window_end}",
                user,
                ip,
                colored(str(failures), failure_color, attrs=["bold"])
            ])
        
        print(tabulate(data, headers=["Time Window", "User", "IP Address", "Failures"], tablefmt="simple"))
    
    def print_geo_distribution(self, dataframes: Dict[str, pd.DataFrame]) -> None:
        """Print geographic distribution"""
        if "geo_distribution" not in dataframes or dataframes["geo_distribution"] is None or dataframes["geo_distribution"].empty:
            print("\nNo geographic data available yet")
            return
            
        df = dataframes["geo_distribution"]
        
        # Aggregate by country and city
        geo_summary = df.groupby(["country", "city"])["count"].sum().reset_index()
        geo_summary = geo_summary.sort_values("count", ascending=False)
        
        # Limit to top 10
        if len(geo_summary) > 10:
            geo_summary = geo_summary.head(10)
        
        print("\n" + "-"*80)
        print(colored("GEOGRAPHIC DISTRIBUTION (Top 10)", "cyan", attrs=["bold"]))
        print("-"*80)
        
        # Format data for display
        data = []
        for _, row in geo_summary.iterrows():
            country = row["country"]
            city = row["city"] if pd.notna(row["city"]) else "Unknown"
            location = f"{city}, {country}" if city != "Unknown" else country
            count = row["count"]
            data.append([location, count])
        
        print(tabulate(data, headers=["Location", "Event Count"], tablefmt="simple"))
    
    def run(self) -> None:
        """Run the dashboard"""
        try:
            logger.info("Starting dashboard initialization...")
            self.initialize_spark()
            logger.info("Dashboard started, press Ctrl+C to stop")
            
            while self.running:
                try:
                    # Get data from in-memory tables
                    dataframes = self.get_all_tables_data()
                    
                    # Update statistics
                    self.update_statistics(dataframes)
                    
                    # Print dashboard
                    self.print_summary_statistics()
                    self.print_event_type_breakdown(dataframes)
                    self.print_high_severity_events(dataframes)
                    self.print_potential_attacks(dataframes)
                    self.print_geo_distribution(dataframes)
                except Exception as e:
                    logger.error(f"Error updating dashboard: {e}")
                    print(f"\nError updating dashboard: {e}")
                    print("Will retry in the next update cycle...")
                
                # Wait for next update
                time.sleep(self.update_interval)
                
        except KeyboardInterrupt:
            logger.info("Dashboard stopped by user")
        except Exception as e:
            logger.error(f"Error in dashboard: {e}", exc_info=True)
        finally:
            if self.spark:
                try:
                    stop_spark_session(self.spark)
                except Exception as e:
                    logger.error(f"Error stopping Spark session: {e}")
            logger.info("Dashboard stopped")

if __name__ == "__main__":
    dashboard = SparkDashboard(update_interval=5)
    dashboard.run() 
 