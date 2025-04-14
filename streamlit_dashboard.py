#!/usr/bin/env python3
"""
Simplified Security Events Dashboard
Uses file-based event storage to avoid Streamlit threading issues
"""
import os
import sys
import json
import time
import logging
import threading
from datetime import datetime
from collections import defaultdict
import uuid
import pickle
import tempfile
import shutil

import streamlit as st
import pandas as pd
from confluent_kafka import Consumer
import plotly.express as px

# Set page config - MUST be the first Streamlit command
st.set_page_config(
    page_title="Security Events Dashboard",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/streamlit_dashboard.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("streamlit_dashboard")

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "dev_security_logs")
KAFKA_GROUP_ID = f'dashboard-consumer-{datetime.now().strftime("%Y%m%d%H%M%S")}'

# Define severity colors
SEVERITY_COLORS = {
    "INFO": "green",
    "LOW": "blue",
    "MEDIUM": "orange",
    "HIGH": "red",
    "CRITICAL": "purple"
}

# File to store events (avoid threading issues)
EVENTS_FILE = "dashboard_events.json"
STATS_FILE = "dashboard_stats.json"
STATUS_FILE = "dashboard_status.json"  # New file to track status between refreshes

# Global flags for consumer thread
should_stop = threading.Event()
thread_running = threading.Event()

# Rate limiting configuration
MAX_EVENTS_PER_MINUTE = 30  # Limit to approximately 1 event every 2 seconds
EVENT_RATE_WINDOW = 60  # Window in seconds for rate limiting

def save_events(events):
    """Save events to file safely using atomic write pattern"""
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            # Write to the temp file
            json.dump(events, tmp, default=str)
            tmp_name = tmp.name
        
        # Atomically replace the target file
        shutil.move(tmp_name, EVENTS_FILE)
        logger.debug(f"Successfully saved {len(events)} events to file")
        
        # Also save status immediately after saving events to preserve sort settings
        save_status()
    except Exception as e:
        logger.error(f"Error saving events: {e}")

def load_events():
    """Load events from file"""
    if not os.path.exists(EVENTS_FILE):
        return []
    
    try:
        with open(EVENTS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading events: {e}")
        # If file is corrupted, return empty list and create backup of corrupted file
        if os.path.exists(EVENTS_FILE):
            backup_file = f"{EVENTS_FILE}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            try:
                shutil.copy(EVENTS_FILE, backup_file)
                logger.info(f"Created backup of corrupted events file: {backup_file}")
            except Exception:
                pass
        return []

def save_stats(stats):
    """Save statistics to file safely"""
    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            # Convert defaultdicts to regular dicts for serialization
            serializable_stats = {}
            for key, value in stats.items():
                if isinstance(value, defaultdict):
                    serializable_stats[key] = dict(value)
                elif isinstance(value, datetime):
                    serializable_stats[key] = value.isoformat()
                else:
                    serializable_stats[key] = value
            
            # Write to the temp file
            json.dump(serializable_stats, tmp)
            tmp_name = tmp.name
        
        # Atomically replace the target file
        shutil.move(tmp_name, STATS_FILE)
    except Exception as e:
        logger.error(f"Error saving stats: {e}")

def load_stats():
    """Load statistics from file"""
    if not os.path.exists(STATS_FILE):
        return {
            "event_counts": defaultdict(int),
            "severity_counts": defaultdict(int),
            "country_counts": defaultdict(int),
            "messages_received": 0,
            "last_update": datetime.now().isoformat()
        }
    
    try:
        with open(STATS_FILE, 'r') as f:
            stats = json.load(f)
            
            # Convert regular dicts back to defaultdicts
            stats["event_counts"] = defaultdict(int, stats.get("event_counts", {}))
            stats["severity_counts"] = defaultdict(int, stats.get("severity_counts", {}))
            stats["country_counts"] = defaultdict(int, stats.get("country_counts", {}))
            
            # Convert ISO timestamp string back to datetime if needed
            if isinstance(stats.get("last_update"), str):
                try:
                    stats["last_update"] = datetime.fromisoformat(stats["last_update"].replace('Z', '+00:00'))
                except:
                    stats["last_update"] = datetime.now()
            
            return stats
    except Exception as e:
        logger.error(f"Error loading stats: {e}")
        # If file is corrupted, return default and create backup
        if os.path.exists(STATS_FILE):
            backup_file = f"{STATS_FILE}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            try:
                shutil.copy(STATS_FILE, backup_file)
                logger.info(f"Created backup of corrupted stats file: {backup_file}")
            except Exception:
                pass
                
        return {
            "event_counts": defaultdict(int),
            "severity_counts": defaultdict(int),
            "country_counts": defaultdict(int),
            "messages_received": 0,
            "last_update": datetime.now()
        }

def save_status():
    """Save consumer status to file"""
    try:
        # Always preserve the current sort state to ensure visual consistency
        current_sort_prefs = {}
        
        # First load the existing status to preserve settings
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, 'r') as f:
                    status_data = json.load(f)
                    if "sort_preferences" in status_data:
                        current_sort_prefs = status_data["sort_preferences"]
            except Exception as e:
                logger.error(f"Error reading status file: {e}")
        
        # Now gather the latest session state values
        for key, value in st.session_state.items():
            # Only save sort related preferences
            if key.startswith('sort_'):
                current_sort_prefs[key] = value
        
        # Prepare the complete status data
        status = {
            "running": thread_running.is_set(),
            "consumer_status": st.session_state.get("consumer_status", "Not Started"),
            "last_status_update": st.session_state.get("last_status_update", datetime.now()).isoformat(),
            "sort_preferences": current_sort_prefs
        }
        
        # Use atomic write pattern for reliability
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
            json.dump(status, tmp)
            tmp_name = tmp.name
        
        shutil.move(tmp_name, STATUS_FILE)
    except Exception as e:
        logger.error(f"Error saving status: {e}")

def load_status():
    """Load consumer status from file"""
    if not os.path.exists(STATUS_FILE):
        return {
            "running": False,
            "consumer_status": "Not Started",
            "last_status_update": datetime.now().isoformat(),
            "sort_preferences": {}
        }
    
    try:
        with open(STATUS_FILE, 'r') as f:
            status = json.load(f)
            
            # Convert ISO timestamp string back to datetime
            if isinstance(status.get("last_status_update"), str):
                try:
                    status["last_status_update"] = datetime.fromisoformat(
                        status["last_status_update"].replace('Z', '+00:00'))
                except:
                    status["last_status_update"] = datetime.now()
            
            # Ensure sort preferences exist
            if "sort_preferences" not in status:
                status["sort_preferences"] = {}
                
            return status
    except Exception as e:
        logger.error(f"Error loading status: {e}")
        return {
            "running": False,
            "consumer_status": "Not Started", 
            "last_status_update": datetime.now(),
            "sort_preferences": {}
        }

def kafka_consumer_thread():
    """Background thread to consume Kafka messages"""
    reconnect_delay = 1  # Start with 1 second delay
    max_reconnect_delay = 30  # Maximum delay in seconds
    reconnect_attempts = 0
    
    # Rate limiting variables
    events_processed_in_window = 0
    rate_window_start = time.time()
    
    # Get current sort preferences to preserve them
    status_data = load_status()
    
    while not should_stop.is_set():
        consumer = None
        try:
            logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}, topic: {KAFKA_TOPIC}")
            
            # Configure consumer 
            consumer = Consumer({
                'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
                'group.id': KAFKA_GROUP_ID,
                'auto.offset.reset': 'earliest',
                'enable.auto.commit': True,
                'session.timeout.ms': 30000,  # Longer session timeout (30 seconds)
                'max.poll.interval.ms': 300000  # Allow longer time between polls (5 minutes)
            })
            
            # Subscribe to topic
            consumer.subscribe([KAFKA_TOPIC])
            logger.info(f"Subscribed to topic {KAFKA_TOPIC}")
            reconnect_attempts = 0  # Reset reconnect attempts on successful connection
            
            # Update status file to show we're connected
            st.session_state.consumer_status = "Connected"
            st.session_state.last_status_update = datetime.now()
            save_status()
            
            # Load existing events and stats
            events = load_events()
            stats = load_stats()
            processed_ids = set(e.get('event_id') for e in events)
            
            # Initialize counters for batch processing and saving
            event_count_since_save = 0
            last_heartbeat = time.time()
            last_save_time = time.time()
            heartbeat_interval = 5  # Heartbeat every 5 seconds
            save_interval = 2  # Save data every 2 seconds at most
            batch_size = 10  # Process in batches for efficiency
            
            # Initialize sampling counter for rate limiting
            sample_counter = 0
            
            # Main consumption loop
            while not should_stop.is_set():
                # Process in batches for efficiency
                messages = []
                
                # Poll for multiple messages (batch processing)
                for _ in range(batch_size):
                    message = consumer.poll(timeout=0.1)  # Short timeout for responsiveness
                    if message is None or message.error():
                        if message and message.error():
                            logger.warning(f"Consumer error: {message.error()}")
                        break
                    messages.append(message)
                
                current_time = time.time()
                
                # Send a heartbeat to the log periodically
                if current_time - last_heartbeat >= heartbeat_interval:
                    logger.debug(f"Consumer heartbeat - {len(messages)} messages received - {len(events)} total events")
                    last_heartbeat = current_time
                    
                    # Save data during idle periods (if anything has changed)
                    if event_count_since_save > 0 and (current_time - last_save_time) >= save_interval:
                        save_events(events)
                        save_stats(stats)
                        event_count_since_save = 0
                        last_save_time = current_time
                
                # Check if there are new messages to process
                if not messages:
                    # Apply rate limiting - check if we need to reset the window
                    time_in_window = current_time - rate_window_start
                    
                    # Reset window if needed
                    if time_in_window >= EVENT_RATE_WINDOW:
                        # Reset rate limiting window
                        events_processed_in_window = 0
                        rate_window_start = current_time
                        logger.debug(f"Rate limit window reset. Processed {stats['messages_received']} total events so far.")
                    
                    # Brief sleep to avoid busy-waiting
                    time.sleep(0.01)
                    continue
                
                # Process batch of messages
                for message in messages:
                    # Check if we've hit rate limit for this window
                    current_time = time.time()
                    time_in_window = current_time - rate_window_start
                    
                    # Reset window if needed
                    if time_in_window >= EVENT_RATE_WINDOW:
                        events_processed_in_window = 0
                        rate_window_start = current_time
                        logger.debug(f"Rate limit window reset within batch. Processed {stats['messages_received']} total events.")
                    
                    # If we've hit rate limit, skip processing remaining messages this cycle
                    if events_processed_in_window >= MAX_EVENTS_PER_MINUTE:
                        logger.debug(f"Rate limit reached ({MAX_EVENTS_PER_MINUTE} events per minute). Skipping remaining batch.")
                        break
                    
                    # Process message
                    try:
                        # Decode the message value and convert to JSON
                        value_str = message.value().decode('utf-8')
                        event = json.loads(value_str)
                        event_id = event.get('event_id', str(uuid.uuid4()))
                        
                        # Skip if already processed
                        if event_id in processed_ids:
                            continue
                        
                        # Rate limit by sampling - only process some events
                        sample_counter += 1
                        event_type = event.get('event_type', 'UNKNOWN')
                        severity = event.get('severity', 'INFO')
                        
                        # Always process HIGH and CRITICAL events, sample others based on rate
                        if severity not in ['HIGH', 'CRITICAL']:
                            # Skip some events to manage rate (simple sampling)
                            if sample_counter % 3 != 0 and events_processed_in_window > MAX_EVENTS_PER_MINUTE / 2:
                                continue
                        
                        # If we got here, we're processing this event
                        events_processed_in_window += 1
                        
                        # Add to processed IDs
                        processed_ids.add(event_id)
                        
                        # Add event to list and limit size
                        events.append(event)
                        if len(events) > 1000:
                            events = events[-1000:]
                        
                        # Update statistics
                        stats["event_counts"][event_type] = stats["event_counts"].get(event_type, 0) + 1
                        stats["severity_counts"][severity] = stats["severity_counts"].get(severity, 0) + 1
                        
                        # Update geo data if available
                        if 'geo_location' in event:
                            country = event['geo_location'].get('country', 'Unknown')
                            stats["country_counts"][country] = stats["country_counts"].get(country, 0) + 1
                        
                        stats["messages_received"] += 1
                        stats["last_update"] = datetime.now()
                        
                        # Increment counter for periodic saving
                        event_count_since_save += 1
                        
                        logger.info(f"Processed event: {event_id} of type {event_type} (rate: {events_processed_in_window}/{MAX_EVENTS_PER_MINUTE} per minute)")
                        
                    except Exception as e:
                        logger.error(f"Error processing message: {e}", exc_info=True)
                
                # Check if it's time to save the data (limit frequency of disk operations)
                current_time = time.time()
                if event_count_since_save > 0 and (
                    event_count_since_save >= 10 or  # Save after processing enough events
                    (current_time - last_save_time) >= save_interval  # Or if enough time has passed
                ):
                    save_events(events)
                    save_stats(stats)
                    event_count_since_save = 0
                    last_save_time = current_time
                    
        except Exception as e:
            logger.error(f"Error in consumer thread: {e}", exc_info=True)
            reconnect_attempts += 1
            # Calculate backoff delay with exponential increase but cap at max_reconnect_delay
            reconnect_delay = min(max_reconnect_delay, reconnect_delay * 2)
            logger.info(f"Will attempt to reconnect in {reconnect_delay} seconds (attempt {reconnect_attempts})")
            
            # Update status to show reconnecting
            st.session_state.consumer_status = "Reconnecting"
            st.session_state.last_status_update = datetime.now()
            save_status()
        
        finally:
            if consumer is not None:
                try:
                    # Save any remaining events before closing
                    if 'events' in locals() and 'stats' in locals() and event_count_since_save > 0:
                        save_events(events)
                        save_stats(stats)
                    
                    consumer.close()
                    logger.info("Kafka consumer closed")
                except Exception as e:
                    logger.error(f"Error closing consumer: {e}")
            
            # Only set thread_running to False if we're completely stopping
            if should_stop.is_set():
                thread_running.clear()
                # Remove PID file when stopping
                if os.path.exists("kafka_consumer.pid"):
                    os.remove("kafka_consumer.pid")
                st.session_state.consumer_status = "Stopped"
                save_status()
                logger.info("Consumer thread terminated")
            else:
                # Otherwise we're just reconnecting
                st.session_state.consumer_status = "Reconnecting"
                save_status()
                logger.info(f"Consumer disconnected, will reconnect in {reconnect_delay} seconds")
                time.sleep(reconnect_delay)

def start_kafka_consumer():
    """Start the Kafka consumer if not already running"""
    # Check if consumer is already running by looking at the pid file
    if os.path.exists("kafka_consumer.pid"):
        try:
            with open("kafka_consumer.pid", "r") as f:
                pid = int(f.read().strip())
            # Try to check if the process is running using os.kill with signal 0
            # This doesn't actually kill the process, just checks if it exists
            try:
                os.kill(pid, 0)
                # Process exists, consumer is already running
                logger.info(f"Consumer already running with PID {pid}")
                thread_running.set()
                st.session_state.consumer_status = "Running"
                st.session_state.last_status_update = datetime.now()
                save_status()
                st.success("Kafka consumer is already running!")
                return True
            except OSError:
                # Process is not running, remove stale PID file
                os.remove("kafka_consumer.pid")
        except:
            # Invalid PID file, remove it
            os.remove("kafka_consumer.pid")
    
    if not thread_running.is_set():
        # Clear the events file to start fresh
        if st.session_state.get('clear_events_on_start', False):
            if os.path.exists(EVENTS_FILE):
                os.remove(EVENTS_FILE)
            if os.path.exists(STATS_FILE):
                os.remove(STATS_FILE)
        
        logger.info("Starting Kafka consumer thread")
        should_stop.clear()
        thread_running.set()
        
        consumer_thread = threading.Thread(target=kafka_consumer_thread)
        consumer_thread.daemon = True
        consumer_thread.start()
        
        # Save current PID to file for status tracking
        with open("kafka_consumer.pid", "w") as f:
            f.write(str(os.getpid()))
        
        # Add a message to the dashboard status
        st.session_state.consumer_status = "Running"
        st.session_state.last_status_update = datetime.now()
        save_status()
        
        # Show a success message
        st.success("Kafka consumer started!")
        return True
    
    return False

def stop_kafka_consumer():
    """Stop the Kafka consumer"""
    if thread_running.is_set():
        logger.info("Stopping Kafka consumer")
        should_stop.set()
        thread_running.clear()
        
        # Remove PID file
        if os.path.exists("kafka_consumer.pid"):
            os.remove("kafka_consumer.pid")
        
        # Update session state
        st.session_state.consumer_status = "Stopped"
        st.session_state.last_status_update = datetime.now()
        save_status()
        
        # Terminate any running consumer process
        try:
            # Get the current process id
            current_pid = os.getpid()
            
            # Find any running Kafka consumer threads
            import psutil
            process = psutil.Process(current_pid)
            
            # Send SIGTERM signal to child processes that might be our consumer thread
            for child in process.children(recursive=True):
                try:
                    logger.info(f"Sending termination signal to child process {child.pid}")
                    child.terminate()
                except:
                    pass
            
            # For extra safety, terminate any Python processes with kafka in the command line
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # Check if this is a child process or a process with kafka in the cmdline
                    if proc.info['cmdline'] and 'kafka' in ' '.join(proc.info['cmdline']).lower() and proc.pid != current_pid:
                        logger.info(f"Sending termination signal to Kafka-related process {proc.pid}")
                        proc.terminate()
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error terminating consumer process: {e}")
            
        # Show a info message
        st.info("Kafka consumer stopped")
        return True
    
    return False

def display_events_table(events, max_rows=10, allow_pagination=False, table_id_prefix=""):
    """Display events in a table format with improved styling and pagination"""
    if not events:
        st.info("No events to display")
        return
    
    total_events = len(events)
    
    # Create a unique key for this table based on view_mode and table_id_prefix
    view_mode = st.session_state.get("view_mode", "Dashboard")
    
    # Use a truly fixed ID for each table type regardless of content
    table_id = f"{view_mode}_{table_id_prefix}"
    
    # Get persisted sort preferences from status file
    status_data = load_status()
    sort_prefs = status_data.get("sort_preferences", {})
    
    # Initialize session state keys
    sort_by_key = f'sort_by_{table_id}'
    sort_asc_key = f'sort_ascending_{table_id}'
    
    # Initialize from persisted preferences
    if sort_by_key not in st.session_state:
        if sort_by_key in sort_prefs:
            st.session_state[sort_by_key] = sort_prefs[sort_by_key]
        else:
            st.session_state[sort_by_key] = "Time"  # Default
    
    if sort_asc_key not in st.session_state:
        if sort_asc_key in sort_prefs:
            st.session_state[sort_asc_key] = sort_prefs[sort_asc_key]
        else:
            st.session_state[sort_asc_key] = False  # Default - descending
    
    # Setup pagination if requested
    if allow_pagination and total_events > max_rows:
        # Calculate number of pages
        num_pages = (total_events + max_rows - 1) // max_rows
        
        # Initialize page number in session state if not already set
        if f'page_{table_id}' not in st.session_state:
            st.session_state[f'page_{table_id}'] = 1
        
        # Get current page from session state
        current_page = st.session_state.get(f'page_{table_id}', 1)
        
        # Page navigation controls - more compact layout
        page_col1, page_col2 = st.columns([1, 3])
        
        with page_col1:
            # Apply custom styling for the pagination controls
            st.markdown("""
            <style>
            /* Pagination container */
            .pagination-container {{
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            /* Page text style */
            .page-text {{
                font-size: 14px;
                margin-right: 8px;
                white-space: nowrap;
            }}
            </style>
            
            <div class="pagination-container">
                <span class="page-text">Page: {current_page} of {num_pages}</span>
            </div>
            """.format(
                current_page=current_page,
                num_pages=num_pages
            ), unsafe_allow_html=True)
            
            # Use smaller buttons arranged horizontally with custom styling
            st.markdown("""
            <style>
            /* Navigation button container */
            .nav-buttons {{
                display: flex;
                gap: 4px;
            }}
            /* Make buttons more compact */
            .stButton button {{
                padding: 2px 12px !important;
                height: 30px !important;
                min-height: 30px !important;
                line-height: 1 !important;
            }}
            </style>
            """, unsafe_allow_html=True)
            
            # Simple previous/next buttons side by side
            nav_col1, nav_col2 = st.columns([1, 1])
            with nav_col1:
                prev_clicked = st.button("◀", key=f"prev_btn_{table_id}", use_container_width=False)
            with nav_col2:
                next_clicked = st.button("▶", key=f"next_btn_{table_id}", use_container_width=False)
            
            # Update page number based on button clicks
            if prev_clicked and current_page > 1:
                st.session_state[f'page_{table_id}'] = current_page - 1
                st.rerun()
            elif next_clicked and current_page < num_pages:
                st.session_state[f'page_{table_id}'] = current_page + 1
                st.rerun()
        
        # Use a simple 3-column layout for better alignment
        sort_col1, sort_col2, sort_col3 = st.columns([1.2, 2, 1])
        
        # First column - Current sort field display
        sort_col1.markdown(f"<div style='margin-top: 10px; font-weight: bold;'>Sorted by: {st.session_state[sort_by_key]} ({'↑ Asc.' if st.session_state[sort_asc_key] else '↓ Desc.'})</div>", unsafe_allow_html=True)
        
        # Second column - Sort field selector
        with sort_col2:
            st.markdown("""
            <style>
            /* Force sort dropdown width and alignment */
            div[data-testid="stSelectbox"] {{width: 200px !important; min-width: 200px !important; margin-top: 0 !important;}}
            div[data-testid="stSelectbox"] > div {{width: 200px !important;}}
            div[data-testid="stSelectbox"] > div > div {{width: 200px !important;}}
            </style>
            """, unsafe_allow_html=True)
            
            sort_field = st.selectbox(
                "Sort by:",
                ["Time", "Type", "Severity", "User", "Source IP", "Location"],
                index=["Time", "Type", "Severity", "User", "Source IP", "Location"].index(st.session_state[sort_by_key]),
                key=f'select_{table_id}',
                label_visibility="collapsed"
            )
        
        # Third column - Sort direction button
        button_text = f"{'↑ Asc.' if st.session_state[sort_asc_key] else '↓ Desc.'}"
        with sort_col3:
            st.markdown("""
            <style>
            /* Button vertical alignment and styling */
            div.stButton > button {{
                margin-top: 0px !important;
                height: 38px !important;
                padding: 2px 12px !important;
                min-width: 80px !important;
                font-size: 0.9rem !important;
            }}
            </style>
            """, unsafe_allow_html=True)
            
            if st.button(button_text, key=f"dir_btn_{table_id}", use_container_width=False):
                st.session_state[sort_asc_key] = not st.session_state[sort_asc_key]
                save_status()
                st.rerun()
            
        # Calculate indices for pagination
        current_page = st.session_state[f'page_{table_id}']
        start_idx = (current_page - 1) * max_rows
        end_idx = min(start_idx + max_rows, total_events)
        
    else:
        # No pagination - add sorting controls with different layout
        # Use a simple 3-column layout for better alignment
        sort_col1, sort_col2, sort_col3 = st.columns([1.2, 2, 1])
        
        # First column - Current sort field display
        sort_col1.markdown(f"<div style='margin-top: 10px; font-weight: bold;'>Sorted by: {st.session_state[sort_by_key]} ({'↑ Asc.' if st.session_state[sort_asc_key] else '↓ Desc.'})</div>", unsafe_allow_html=True)
        
        # Second column - Sort field selector
        with sort_col2:
            st.markdown("""
            <style>
            /* Force sort dropdown width and alignment */
            div[data-testid="stSelectbox"] {{width: 200px !important; min-width: 200px !important; margin-top: 0 !important;}}
            div[data-testid="stSelectbox"] > div {{width: 200px !important;}}
            div[data-testid="stSelectbox"] > div > div {{width: 200px !important;}}
            </style>
            """, unsafe_allow_html=True)
            
            sort_field = st.selectbox(
                "Sort by:",
                ["Time", "Type", "Severity", "User", "Source IP", "Location"],
                index=["Time", "Type", "Severity", "User", "Source IP", "Location"].index(st.session_state[sort_by_key]),
                key=f'select_{table_id}',
                label_visibility="collapsed"
            )
        
        # Third column - Sort direction button
        button_text = f"{'↑ Asc.' if st.session_state[sort_asc_key] else '↓ Desc.'}"
        with sort_col3:
            st.markdown("""
            <style>
            /* Button vertical alignment and styling */
            div.stButton > button {{
                margin-top: 0px !important;
                height: 38px !important;
                padding: 2px 12px !important;
                min-width: 80px !important;
                font-size: 0.9rem !important;
            }}
            </style>
            """, unsafe_allow_html=True)
            
            if st.button(button_text, key=f"dir_btn_{table_id}", use_container_width=False):
                st.session_state[sort_asc_key] = not st.session_state[sort_asc_key]
                save_status()
                st.rerun()
    
    # Update sort field if changed
    if sort_field != st.session_state[sort_by_key]:
        st.session_state[sort_by_key] = sort_field
        save_status()  # Save changes immediately
        
    # Convert and sort all events based on current settings
    sort_field_name = st.session_state[sort_by_key]
    is_ascending = st.session_state[sort_asc_key]
    
    # First, convert all events to a format ready for display and sorting
    formatted_events = []
    
    # Define severity ranking for proper sorting (higher number = more severe)
    severity_rank = {
        "CRITICAL": 5,
        "HIGH": 4,
        "MEDIUM": 3,
        "LOW": 2,
        "INFO": 1
    }
    
    for event in events:
        # Format timestamp for display
        timestamp_str = event.get("timestamp", "")
        timestamp_dt = None
        if timestamp_str:
            try:
                if isinstance(timestamp_str, str):
                    timestamp_dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    timestamp_display = timestamp_dt.strftime("%H:%M:%S")
                else:
                    timestamp_dt = timestamp_str
                    timestamp_display = timestamp_dt.strftime("%H:%M:%S")
            except:
                timestamp_display = timestamp_str
        else:
            timestamp_display = ""
        
        # Get severity for sorting and styling
        severity = event.get("severity", "INFO")
        
        # Get location for sorting
        country = event.get('geo_location', {}).get('country', '')
        city = event.get('geo_location', {}).get('city', '')
        location = f"{country}, {city}" if country or city else ""
        
        # Create a dict with formatted values for display and raw values for sorting
        formatted_event = {
            "original": event,  # Keep the original for reference
            "display": {
                "Time": timestamp_display,
                "Type": event.get("event_type", ""),
                "Severity": severity,
                "User": event.get("user_id", ""),
                "Source IP": event.get("ip_address", ""),
                "Location": location,
                "Message": event.get("message", "")
            },
            "sort": {
                "Time": timestamp_dt or datetime.min,
                "Type": event.get("event_type", ""),
                "Severity": severity_rank.get(severity, 0),  # Use numeric rank instead of string
                "User": event.get("user_id", ""),
                "Source IP": event.get("ip_address", ""),
                "Location": location,
                "Message": event.get("message", "")
            }
        }
        formatted_events.append(formatted_event)
    
    # Sort all events based on the selected field
    if sort_field_name == "Time":
        # Special case for time to handle None values
        formatted_events.sort(
            key=lambda x: x["sort"][sort_field_name] or datetime.min, 
            reverse=not is_ascending
        )
    else:
        # For other fields, use standard sorting
        formatted_events.sort(
            key=lambda x: x["sort"][sort_field_name] or "", 
            reverse=not is_ascending
        )
    
    # Determine which events to display (with or without pagination)
    if allow_pagination and total_events > max_rows:
        # Get events for current page (already sorted)
        page_events = formatted_events[start_idx:end_idx]
        
        # Display page range info
        st.caption(f"Showing events {start_idx + 1} to {end_idx} of {total_events}")
    else:
        # No pagination, use all events up to max_rows (already sorted)
        page_events = formatted_events[:max_rows]
    
    # Create table data from the formatted and sorted events
    table_data = [event["display"] for event in page_events]
    
    # Convert to dataframe
    df = pd.DataFrame(table_data)
    
    # Apply conditional formatting based on severity
    def highlight_severity(val):
        if val == 'CRITICAL':
            return 'background-color: #ffcccc; color: darkred; font-weight: bold'
        elif val == 'HIGH':
            return 'background-color: #ffd6a5; color: #994d00; font-weight: bold'
        elif val == 'MEDIUM':
            return 'background-color: #ffffcc; color: #806600'
        elif val == 'LOW':
            return 'background-color: #e6f3ff; color: #004080'
        else:
            return ''
    
    # Apply the styling to the Severity column only
    styled_df = df.style.apply(lambda row: [highlight_severity(row['Severity']) if col == 'Severity' else '' for col in row.index], axis=1)
    
    # Display the styled dataframe
    st.dataframe(styled_df, use_container_width=True, height=350)
    
    # Add a note about sorting behavior
    st.caption("ℹ️ **Note:** Clicking column headers only sorts the current page. Use the Sort controls above to sort across all pages.")
    
    # Return total count for convenience
    return total_events

def display_event_type_chart(event_counts):
    """Display a bar chart of event types with improved styling"""
    if not event_counts:
        st.info("No event data available")
        return
    
    # Create dataframe for chart
    chart_data = pd.DataFrame({
        "Event Type": list(event_counts.keys()),
        "Count": list(event_counts.values())
    }).sort_values("Count", ascending=False)
    
    # Create a colorful bar chart
    fig = px.bar(
        chart_data, 
        x="Event Type", 
        y="Count",
        color="Event Type",
        title="Event Distribution by Type",
        color_discrete_sequence=px.colors.qualitative.Bold
    )
    
    # Customize layout
    fig.update_layout(
        xaxis_title="Event Type",
        yaxis_title="Number of Events",
        height=350,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    
    # Display the figure
    st.plotly_chart(fig, use_container_width=True)

def display_severity_chart(severity_counts):
    """Display a pie chart of severity levels with improved styling"""
    if not severity_counts:
        st.info("No severity data available")
        return
    
    # Create dataframe
    chart_data = pd.DataFrame({
        "Severity": list(severity_counts.keys()),
        "Count": list(severity_counts.values())
    })
    
    # Create a pie chart with custom colors
    colors = {
        'CRITICAL': '#ff4d4d',
        'HIGH': '#ff9933',
        'MEDIUM': '#ffcc00',
        'LOW': '#66b3ff',
        'INFO': '#99cc99'
    }
    
    # Get colors for the values that exist in our data
    color_values = [colors.get(sev, '#cccccc') for sev in chart_data['Severity']]
    
    fig = px.pie(
        chart_data, 
        values='Count', 
        names='Severity',
        title="Distribution by Severity Level",
        color='Severity',
        color_discrete_map={k: v for k, v in zip(chart_data['Severity'], color_values)}
    )
    
    # Customize layout
    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    
    # Display the figure
    st.plotly_chart(fig, use_container_width=True)

def display_geo_chart(country_counts):
    """Display a choropleth map of event locations"""
    if not country_counts or sum(country_counts.values()) == 0:
        st.info("No geographic data available")
        return
    
    # Create dataframe for chart
    chart_data = pd.DataFrame({
        "Country": list(country_counts.keys()),
        "Count": list(country_counts.values())
    })
    
    # Create a choropleth map
    fig = px.choropleth(
        chart_data,
        locations="Country",
        locationmode="country names",
        color="Count",
        hover_name="Country",
        color_continuous_scale=px.colors.sequential.Plasma,
        title="Geographic Distribution of Events"
    )
    
    # Customize layout
    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=50, b=10),
        geo=dict(
            showframe=False,
            showcoastlines=True,
            projection_type='natural earth'
        )
    )
    
    # Display the figure
    st.plotly_chart(fig, use_container_width=True)

def display_time_series(events, window_minutes=30):
    """Display a time series of events over time"""
    if not events or len(events) < 5:
        st.info("Not enough event data for time series")
        return
    
    # Extract timestamps and convert to datetime
    timestamps = []
    event_types = []
    severities = []
    
    for event in events:
        ts = event.get("timestamp")
        if ts:
            try:
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    timestamps.append(dt)
                    event_types.append(event.get("event_type", "UNKNOWN"))
                    severities.append(event.get("severity", "INFO"))
            except:
                pass
    
    if not timestamps:
        st.info("No valid timestamp data for time series")
        return
    
    # Create a dataframe
    df = pd.DataFrame({
        "timestamp": timestamps,
        "event_type": event_types,
        "severity": severities
    })
    
    # Ensure timestamps are in chronological order
    df = df.sort_values("timestamp")
    
    # Set the minimum time to include (last N minutes)
    min_time = datetime.now(timestamps[0].tzinfo) - pd.Timedelta(minutes=window_minutes)
    df = df[df["timestamp"] > min_time]
    
    # Group by minute and event type
    df["minute"] = df["timestamp"].dt.floor("min")
    event_counts = df.groupby(["minute", "event_type"]).size().reset_index(name="count")
    
    # Create a time series chart
    fig = px.line(
        event_counts,
        x="minute",
        y="count",
        color="event_type",
        title=f"Event Activity (Last {window_minutes} Minutes)",
        markers=True
    )
    
    # Customize layout
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Number of Events",
        height=350,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    
    # Display the figure
    st.plotly_chart(fig, use_container_width=True)

def display_high_severity_events(events, prefix_suffix=""):
    """Display only high and critical severity events with improved styling
    
    Args:
        events: List of events to filter for high severity
        prefix_suffix: Optional suffix to add to table_id_prefix to ensure unique keys across views
    """
    high_severity = [
        e for e in events 
        if e.get('severity') in ['HIGH', 'CRITICAL']
    ]
    
    if not high_severity:
        st.info("No high severity events detected")
        return
    
    # Create metrics for high severity event counts
    high_count = len([e for e in high_severity if e.get('severity') == 'HIGH'])
    critical_count = len([e for e in high_severity if e.get('severity') == 'CRITICAL'])
    
    # Create columns for metrics
    cols = st.columns(2)
    cols[0].metric("HIGH Severity Events", high_count, delta=None, delta_color="off")
    cols[1].metric("CRITICAL Severity Events", critical_count, delta=None, delta_color="off")
    
    # Display the events - use a stable table ID with 'high_severity' prefix
    # to ensure sort settings for high severity events persist separately
    # Adding the prefix_suffix parameter to ensure unique keys across different views
    display_events_table(high_severity, table_id_prefix=f"high_severity_{prefix_suffix}")

def display_status_indicators(status_data):
    """Display system status indicators"""
    # Create columns for status indicators
    cols = st.columns(3)
    
    # Kafka connection status
    if status_data.get("running", False):
        cols[0].success("Kafka Connected")
    else:
        cols[0].error("Kafka Disconnected")
    
    # Event processing status - simplified to avoid timezone issues
    if thread_running.is_set():
        # If Kafka is running, assume events are being processed
        cols[1].success("Events Processing")
    else:
        # If Kafka is not running, show disconnected
        cols[1].warning("Event Processing Stopped")
    
    # Rate limiting status
    rate_limit = MAX_EVENTS_PER_MINUTE
    if rate_limit <= 30:
        cols[2].info(f"Slow Mode: {rate_limit}/min")
    elif rate_limit <= 100:
        cols[2].success(f"Normal Rate: {rate_limit}/min")
    else:
        cols[2].warning(f"High Rate: {rate_limit}/min")

def main():
    """Main function for the dashboard UI"""
    # Declare global variables at the beginning of the function
    global MAX_EVENTS_PER_MINUTE
    
    # Load persisted status
    status_data = load_status()
    
    # Restore any previously saved sort preferences to session state
    if "sort_preferences" in status_data:
        for key, value in status_data["sort_preferences"].items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    # Check if we're switching views from a button click
    if 'switch_to_view' in st.session_state:
        st.session_state.view_mode = st.session_state.switch_to_view
        del st.session_state.switch_to_view  # Clear after setting

    # Import required libraries for visualization
    try:
        import psutil
    except ImportError:
        st.error("psutil package not installed. Process management features will be limited. Install with: pip install psutil")
        st.info("Continuing with limited visualization capabilities...")
        
        # Define a dummy px object to prevent errors
        class DummyPlotly:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None
            
            def __getitem__(self, name):
                return self
        
        px = DummyPlotly()
        px.colors = DummyPlotly()
        px.colors.qualitative = DummyPlotly()
        px.colors.sequential = DummyPlotly()
    
    # Add custom CSS for styling
    st.markdown("""
    <style>
    .block-container {{padding-top: 1rem; padding-bottom: 0rem;}}
    section[data-testid="stSidebar"] > div {{padding-top: 1rem;}}
    div[data-testid="stMetricValue"] {{font-size: 2rem !important}}
    .critical {{background-color: #ffcccc; padding: 0.5rem; border-radius: 5px; border-left: 5px solid #cc0000;}}
    .high {{background-color: #ffd6a5; padding: 0.5rem; border-radius: 5px; border-left: 5px solid #ff9900;}}
    .medium {{background-color: #ffffcc; padding:.5rem; border-radius: 5px; border-left: 5px solid #cccc00;}}
    .low {{background-color: #e6f3ff; padding: 0.5rem; border-radius: 5px; border-left: 5px solid #0077cc;}}
    .info {{background-color: #e6ffe6; padding: 0.5rem; border-radius: 5px; border-left: 5px solid #00cc00;}}
    div[data-testid="stHeader"] {{background-color: rgba(0,0,0,0);}}
    .stPagination {{text-align: center; margin-top: 10px;}}
    button[data-testid="baseButton-secondary"] {{min-width: 100px;}}
    
    /* Compact select box for pagination */
    [data-testid="stSelectbox"] {{min-width: 40px !important; width: 40px !important;}}
    [data-testid="stSelectbox"] > div {{min-width: 40px !important; width: 40px !important; }}
    [data-testid="stSelectbox"] > div > div {{min-width: 40px !important; width: 40px !important;}}
    [data-testid="stSelectbox"] > div > div > div {{padding: 0 !important; }}
    [data-baseweb="select"] {{width: 40px !important; min-width: 40px !important;}}
    [data-baseweb="select"] > div {{padding-left: 3px !important; padding-right: 3px !important; font-size:0.8em !important;}}
    
    /* Remove sort dropdown CSS that conflicts with inline CSS */
    
    /* Adjust margin for pagination text */
    [data-testid="stMarkdown"] > div > p {{margin-bottom: 0 !important; margin-top: 0 !important;}}
    
    /* Remove column padding */
    div.row-widget.stRow > div {{padding-left: 0 !important; padding-right: 0 !important;}}
    /* Reduce spacing in all elements */
    div[data-testid="stVerticalBlock"] > div {{margin-bottom: 0 !important; padding-bottom: 0 !important;}}
    /* Less margin after subheaders */
    h3 {{margin-bottom: 0.2rem !important;}}
    /* More compact caption */
    .stCaption {{margin-top: -5px !important; margin-bottom: 5px !important;}}
    /* More compact buttons */
    button[data-testid="baseButton-secondary"] {{padding-top: 0.2rem !important; padding-bottom: 0.2rem !important;}}
    
    /* Sort direction button styling */
    .stButton button {{min-width: 80px !important; font-size: 0.9rem !important;}}
    </style>
    """, unsafe_allow_html=True)
    
    # Check if psutil is installed
    try:
        import psutil
    except ImportError:
        st.sidebar.warning("psutil package not installed. Process management features will be limited. Install with: pip install psutil")
    
    # Initialize session state for UI controls and status
    if 'refresh_interval' not in st.session_state:
        st.session_state.refresh_interval = 5  # Fixed to 5 seconds
    if 'auto_refresh' not in st.session_state:
        st.session_state.auto_refresh = True
    if 'clear_events_on_start' not in st.session_state:
        st.session_state.clear_events_on_start = False
    if 'rate_limit' not in st.session_state:
        st.session_state.rate_limit = MAX_EVENTS_PER_MINUTE
    if 'view_mode' not in st.session_state:
        st.session_state.view_mode = "Dashboard"
    if 'rows_per_page' not in st.session_state:
        st.session_state.rows_per_page = 50  # Fixed to 50 rows
    
    # Check if Kafka consumer is running
    if status_data["running"]:
        # If status file indicates consumer is running, set thread_running
        thread_running.set()
        
        # Verify if the process is actually running
        if os.path.exists("kafka_consumer.pid"):
            try:
                with open("kafka_consumer.pid", "r") as f:
                    pid = int(f.read().strip())
                try:
                    # Check if process exists
                    os.kill(pid, 0)
                except OSError:
                    # Process doesn't exist, clear thread_running
                    thread_running.clear()
                    st.session_state.consumer_status = "Stopped (Abnormal)"
                    save_status()
            except:
                # Invalid PID file
                thread_running.clear()
                st.session_state.consumer_status = "Stopped (Error)"
                save_status()
    
    # Update session state with persisted values
    st.session_state.consumer_status = status_data["consumer_status"]
    st.session_state.last_status_update = status_data["last_status_update"]
    
    # Main title and description in header
    header_col1, header_col2 = st.columns([3, 1])
    with header_col1:
        st.title("Security Events Dashboard")
    with header_col2:
        # Display current time
        st.markdown(f"**Current Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load data from files
    events = load_events()
    stats = load_stats()
    
    # Add last event time to status data for display
    if events and len(events) > 0:
        latest_event = events[-1]
        ts = latest_event.get("timestamp")
        if ts:
            try:
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    status_data["last_event_time"] = dt
            except:
                pass
    
    # Sidebar controls
    st.sidebar.title("Dashboard Controls")
    
    # View mode selection
    view_modes = ["Dashboard", "Events Only", "Geographic", "System Info"]
    st.session_state.view_mode = st.sidebar.radio("View Mode", view_modes)
    
    # Display options in the sidebar
    st.sidebar.subheader("Display Options")
    st.session_state.auto_refresh = st.sidebar.checkbox(
        "Auto Refresh (5s interval)", 
        value=st.session_state.auto_refresh
    )
    
    if st.sidebar.button("Manual Refresh", use_container_width=True):
        # Save current status before refreshing
        save_status()
        st.rerun()
    
    # Kafka connection controls
    st.sidebar.subheader("Kafka Connection")
    
    # Start/Stop consumer
    if not thread_running.is_set():
        # Option to clear events on start
        st.session_state.clear_events_on_start = st.sidebar.checkbox(
            "Clear existing events on start", 
            value=st.session_state.clear_events_on_start
        )
        
        # Rate limiting control
        st.session_state.rate_limit = st.sidebar.slider(
            "Events Per Minute (Rate Limit)",
            min_value=10,
            max_value=300,
            value=st.session_state.rate_limit,
            step=10
        )
        # Update the global variable
        MAX_EVENTS_PER_MINUTE = st.session_state.rate_limit
        
        if st.sidebar.button("Start Kafka Consumer", use_container_width=True):
            start_kafka_consumer()
    else:
        if st.sidebar.button("Stop Kafka Consumer", use_container_width=True):
            stop_kafka_consumer()
    
    # Display connection info based on persisted status
    status = "Connected" if thread_running.is_set() else "Disconnected"
    status_color = "green" if thread_running.is_set() else "red"
    
    # Display consumer status with last update time
    st.sidebar.markdown(f"**Status:** :{status_color}[{status}]")
    
    # Show detailed consumer status from session state
    consumer_status = st.session_state.consumer_status
    status_emoji = "🟢" if consumer_status in ["Connected", "Running"] else "🔄" if consumer_status == "Reconnecting" else "🔴"
    st.sidebar.markdown(f"**Consumer State:** {status_emoji} {consumer_status}")
    
    st.sidebar.markdown(f"**Topic:** {KAFKA_TOPIC}")
    st.sidebar.markdown(f"**Bootstrap Servers:** {KAFKA_BOOTSTRAP_SERVERS}")
    
    # Show rate limit if connected
    if thread_running.is_set():
        st.sidebar.markdown(f"**Rate Limit:** {MAX_EVENTS_PER_MINUTE} events/minute")
    
    # Format last status update time
    last_status_update = st.session_state.last_status_update
    if isinstance(last_status_update, str):
        try:
            last_status_update = datetime.fromisoformat(last_status_update.replace('Z', '+00:00'))
        except:
            last_status_update = datetime.now()
    last_status_str = last_status_update.strftime("%Y-%m-%d %H:%M:%S")
    st.sidebar.markdown(f"**Last Status Change:** {last_status_str}")
    
    # Add button to manually repair data files if needed
    if st.sidebar.button("Repair Data Files", use_container_width=True):
        if os.path.exists(EVENTS_FILE):
            os.remove(EVENTS_FILE)
        if os.path.exists(STATS_FILE):
            os.remove(STATS_FILE)
        # Don't remove status file, just update it
        st.sidebar.success("Data files reset successfully")
    
    # Display stats
    st.sidebar.subheader("Statistics")
    st.sidebar.markdown(f"**Total Events:** {stats.get('messages_received', 0)}")
    
    # Format last update time
    last_update = stats.get('last_update', datetime.now())
    if isinstance(last_update, str):
        try:
            last_update = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
        except:
            last_update = datetime.now()
    
    last_update_str = last_update.strftime("%Y-%m-%d %H:%M:%S")
    st.sidebar.markdown(f"**Last Event Update:** {last_update_str}")
    
    # Add system information if expanded
    if st.sidebar.checkbox("Show System Information"):
        st.sidebar.subheader("System Info")
        
        # Show CPU and memory usage if psutil is available
        try:
            import psutil
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            st.sidebar.markdown(f"**CPU Usage:** {cpu_percent:.1f}%")
            st.sidebar.markdown(f"**Memory Usage:** {memory_percent:.1f}%")
            st.sidebar.markdown(f"**Python Version:** {sys.version.split()[0]}")
            st.sidebar.markdown(f"**Streamlit Version:** {st.__version__}")
        except:
            st.sidebar.markdown("System information unavailable")
    
    # Check if we have events to display
    if not events:
        st.warning("No events to display. Make sure the Kafka consumer is running and producing events.")
    else:
        # Display status indicators at the top
        display_status_indicators(status_data)
        
        # Different views based on selected mode
        if st.session_state.view_mode == "Events Only":
            # Full-width events table
            st.subheader(f"Security Events ({len(events)})")
            display_events_table(events, max_rows=st.session_state.rows_per_page, allow_pagination=True, table_id_prefix="all")
            
        elif st.session_state.view_mode == "Geographic":
            # Focus on geographic information
            st.subheader("Geographic Distribution")
            display_geo_chart(stats.get("country_counts", {}))
            
            # List of countries with most events
            if stats.get("country_counts"):
                country_df = pd.DataFrame({
                    "Country": list(stats["country_counts"].keys()),
                    "Events": list(stats["country_counts"].values())
                }).sort_values("Events", ascending=False)
                
                st.subheader("Top Countries by Event Count")
                st.dataframe(country_df.head(10), use_container_width=True)
            
            # Recent events table with location data
            st.subheader("Events with Location Data")
            geo_events = [e for e in events if 'geo_location' in e]
            if geo_events:
                display_events_table(geo_events, max_rows=st.session_state.rows_per_page, allow_pagination=True, table_id_prefix="geo")
            else:
                st.info("No events with geographic data")
            
        elif st.session_state.view_mode == "System Info":
            # System information and diagnostics
            st.subheader("System Information")
            
            # Create columns for system metrics
            col1, col2, col3 = st.columns(3)
            
            # Show memory and CPU if available
            try:
                import psutil
                col1.metric("CPU Usage", f"{psutil.cpu_percent()}%")
                col2.metric("Memory Usage", f"{psutil.virtual_memory().percent}%")
                col3.metric("Disk Usage", f"{psutil.disk_usage('/').percent}%")
            except:
                col1.info("CPU info unavailable")
                col2.info("Memory info unavailable")
                col3.info("Disk info unavailable")
            
            # Show data file sizes
            st.subheader("Data Files")
            file_sizes = {}
            for file_path in [EVENTS_FILE, STATS_FILE, STATUS_FILE]:
                if os.path.exists(file_path):
                    size_bytes = os.path.getsize(file_path)
                    size_kb = size_bytes / 1024
                    file_sizes[file_path] = f"{size_kb:.2f} KB"
                else:
                    file_sizes[file_path] = "File not found"
            
            file_df = pd.DataFrame({
                "File": list(file_sizes.keys()),
                "Size": list(file_sizes.values())
            })
            st.dataframe(file_df, use_container_width=True)
            
            # Event statistics
            st.subheader("Event Statistics")
            st.write(f"Total events processed: {stats.get('messages_received', 0)}")
            st.write(f"Events in memory: {len(events)}")
            st.write(f"Unique event types: {len(stats.get('event_counts', {}))}")
            st.write(f"Unique countries: {len(stats.get('country_counts', {}))}")
            
            # Show all events with pagination
            st.subheader("All Events")
            display_events_table(events, max_rows=st.session_state.rows_per_page, allow_pagination=True, table_id_prefix="all")
            
            # Show logs if expanded
            if st.checkbox("Show Recent Logs"):
                log_file = "logs/streamlit_dashboard.log"
                if os.path.exists(log_file):
                    with open(log_file, "r") as f:
                        logs = f.readlines()[-50:]  # Get last 50 lines
                    
                    st.code("".join(logs), language="text")
                else:
                    st.info("Log file not found")
            
        else:  # Default Dashboard view
            # Set up dashboard layout
            col1, col2 = st.columns(2)
            
            with col1:
                # Display recent events
                st.subheader(f"Recent Events ({len(events)})")
                display_events_table(events, max_rows=st.session_state.rows_per_page, table_id_prefix="recent")
                
                # Instead of a button, just show an informational message
                if len(events) > st.session_state.rows_per_page:
                    st.caption(f"Showing {st.session_state.rows_per_page} most recent events. To see all {len(events)} events with pagination, select 'Events Only' in the sidebar.")
                
                # Display severity distribution
                st.subheader("Severity Distribution")
                display_severity_chart(stats.get("severity_counts", {}))
            
            with col2:
                # Display event type chart
                st.subheader("Event Types")
                display_event_type_chart(stats.get("event_counts", {}))
                
                # Display high severity events
                st.subheader("High Severity Events")
                display_high_severity_events(events, prefix_suffix="dashboard_view")
        
        # Add a time series view at the bottom in Dashboard view
        if st.session_state.view_mode == "Dashboard" and len(events) > 5:
            st.subheader("Event Activity Timeline")
            display_time_series(events)
    
    # Show data source info in footer
    st.markdown("---")
    st.caption(f"Data Source: Kafka Topic '{KAFKA_TOPIC}' | Refresh Rate: {st.session_state.refresh_interval}s | Last Update: {datetime.now().strftime('%H:%M:%S')}")
    
    # Save current status before auto-refreshing
    save_status()
    
    # Auto refresh if enabled
    if st.session_state.auto_refresh:
        time.sleep(st.session_state.refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main() 