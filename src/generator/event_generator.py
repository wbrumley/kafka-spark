import uuid
import random
import ipaddress
from datetime import datetime, timedelta
from faker import Faker
from typing import Optional, Dict, List, Any

from .models import SecurityEvent, EventType, Severity, UserType, GeoLocation

class SecurityEventGenerator:
    def __init__(self):
        self.fake = Faker()
        # Add more locations to get better geographic data
        Faker.seed(0)  # For reproducibility
        
        # Configure weighted event types for more realistic distribution
        self.event_weights: Dict[EventType, int] = {
            # Authentication events (highest frequency)
            EventType.LOGIN_SUCCESS: 40,
            EventType.LOGIN_FAILURE: 20,
            EventType.LOGOUT: 20,
            EventType.PASSWORD_CHANGE: 5,
            EventType.MFA_CHALLENGE: 10,
            EventType.ACCOUNT_LOCKOUT: 5,
            
            # Authorization events (medium frequency)
            EventType.UNAUTHORIZED_ACCESS: 10,
            EventType.PRIVILEGE_ESCALATION: 2,
            EventType.PERMISSION_CHANGE: 5,
            
            # Data events (medium frequency)
            EventType.DATA_ACCESS: 15,
            EventType.DATA_MODIFICATION: 5,
            EventType.DATA_EXFILTRATION: 1,
            
            # System events (low frequency)
            EventType.SYSTEM_STARTUP: 1,
            EventType.SYSTEM_SHUTDOWN: 1,
            EventType.CONFIG_CHANGE: 2,
        }
        
        # Build weighted list for random selection
        self.event_types: List[EventType] = []
        for event_type, weight in self.event_weights.items():
            self.event_types.extend([event_type] * weight)
            
        # User types with weights
        self.user_type_weights: Dict[UserType, int] = {
            UserType.EMPLOYEE: 60,
            UserType.CONTRACTOR: 15,
            UserType.ADMIN: 10,
            UserType.SYSTEM: 10,
            UserType.CUSTOMER: 30,
            UserType.ANONYMOUS: 5,
        }
        
        # Build weighted list for user types
        self.user_types: List[UserType] = []
        for user_type, weight in self.user_type_weights.items():
            self.user_types.extend([user_type] * weight)
            
        # Common resources for unauthorized access
        self.resources = [
            "/api/admin",
            "/api/users",
            "/api/settings",
            "/api/billing",
            "/api/reports",
            "/api/logs",
            "/dashboard",
            "/admin/users",
            "/admin/settings",
            "/admin/permissions",
            "/sensitive-data",
            "/internal/config",
            "/api/v1/payment-methods",
            "/api/v2/user-management"
        ]
        
        # IP address pools (internal and external)
        self.internal_ip_ranges = [
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16"
        ]
            
        # Keep track of users for consistent events
        self.users: Dict[str, Dict[str, Any]] = {}
        
        # Prepare some realistic users with consistent attributes
        self.prepare_users(100)
        
        # Track active sessions
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        # System sources and targets
        self.systems = [
            "web-portal",
            "mobile-app",
            "api-gateway",
            "auth-service",
            "user-service",
            "billing-service",
            "data-service",
            "admin-panel",
            "reporting-service",
            "notification-service"
        ]
        
        # Typical session duration range (5 minutes to 8 hours)
        self.session_min_duration = 5 * 60  # 5 minutes in seconds
        self.session_max_duration = 8 * 60 * 60  # 8 hours in seconds
    
    def prepare_users(self, num_users: int) -> None:
        """Prepare a set of users with consistent attributes"""
        user_types = list(UserType)
        domains = ["company.com", "vendor.org", "client.net", "partner.co", "example.com"]
        
        for i in range(1, num_users + 1):
            user_id = f"user_{i}"
            user_type = random.choice(self.user_types)
            
            # Determine email domain based on user type
            if user_type == UserType.EMPLOYEE:
                domain = domains[0]
            elif user_type == UserType.CONTRACTOR:
                domain = domains[1]
            elif user_type == UserType.ADMIN:
                domain = domains[0]
            elif user_type == UserType.CUSTOMER:
                domain = random.choice(domains[2:])
            else:
                domain = random.choice(domains)
                
            email = f"{self.fake.user_name()}@{domain}"
            
            # Create consistent location data for this user
            country = self.fake.country()
            city = self.fake.city()
            
            # Generate latitude and longitude (not perfectly matched to country/city but sufficient for demo)
            lat = self.fake.latitude()
            lng = self.fake.longitude()
            
            # Store user data
            self.users[user_id] = {
                "user_id": user_id,
                "user_type": user_type,
                "email": email,
                "country": country,
                "city": city,
                "latitude": lat,
                "longitude": lng,
                "preferred_device": random.choice(["desktop", "mobile", "tablet"]),
                "frequent_ip": self.generate_ip_address(internal=user_type in [UserType.EMPLOYEE, UserType.ADMIN, UserType.SYSTEM])
            }
    
    def generate_ip_address(self, internal: bool = False) -> str:
        """Generate IP address (either internal or external)"""
        if internal:
            # Generate IP from internal ranges
            range_cidr = random.choice(self.internal_ip_ranges)
            network = ipaddress.ip_network(range_cidr)
            # Get a random IP from the range
            random_ip = random.randint(int(network.network_address), int(network.broadcast_address))
            return str(ipaddress.ip_address(random_ip))
        else:
            # Generate public IP
            return self.fake.ipv4_public()
    
    def get_severity_for_event(self, event_type: EventType) -> Severity:
        """Determine appropriate severity based on event type"""
        high_severity_events = [
            EventType.PRIVILEGE_ESCALATION,
            EventType.DATA_EXFILTRATION,
            EventType.ACCOUNT_LOCKOUT
        ]
        
        medium_severity_events = [
            EventType.UNAUTHORIZED_ACCESS,
            EventType.DATA_MODIFICATION,
            EventType.PERMISSION_CHANGE,
            EventType.LOGIN_FAILURE
        ]
        
        low_severity_events = [
            EventType.CONFIG_CHANGE,
            EventType.MFA_CHALLENGE,
            EventType.PASSWORD_CHANGE
        ]
        
        if event_type in high_severity_events:
            return random.choice([Severity.HIGH, Severity.CRITICAL])
        elif event_type in medium_severity_events:
            return random.choice([Severity.MEDIUM, Severity.HIGH])
        elif event_type in low_severity_events:
            return random.choice([Severity.LOW, Severity.MEDIUM])
        else:
            return Severity.INFO
    
    def get_tags_for_event(self, event_type: EventType, user_type: UserType) -> List[str]:
        """Generate appropriate tags for the event"""
        tags = []
        
        # Add category tag
        if event_type in [EventType.LOGIN_SUCCESS, EventType.LOGIN_FAILURE, EventType.LOGOUT, 
                         EventType.PASSWORD_CHANGE, EventType.MFA_CHALLENGE, EventType.ACCOUNT_LOCKOUT]:
            tags.append("authentication")
        elif event_type in [EventType.UNAUTHORIZED_ACCESS, EventType.PRIVILEGE_ESCALATION, EventType.PERMISSION_CHANGE]:
            tags.append("authorization")
        elif event_type in [EventType.DATA_ACCESS, EventType.DATA_MODIFICATION, EventType.DATA_EXFILTRATION]:
            tags.append("data")
        elif event_type in [EventType.SYSTEM_STARTUP, EventType.SYSTEM_SHUTDOWN, EventType.CONFIG_CHANGE]:
            tags.append("system")
        
        # Add user type tag
        tags.append(user_type.lower())
        
        # Add severity-related tags
        if event_type in [EventType.PRIVILEGE_ESCALATION, EventType.DATA_EXFILTRATION]:
            tags.append("security-threat")
        if event_type in [EventType.ACCOUNT_LOCKOUT, EventType.LOGIN_FAILURE]:
            tags.append("security-alert")
            
        # Add some randomness
        if random.random() < 0.3:
            tags.append(random.choice(["monitored", "audited", "logged"]))
            
        # Add source tag
        if random.random() < 0.5:
            tags.append(random.choice(["web", "api", "mobile", "desktop"]))
            
        return tags
    
    def create_session(self, user_id: str) -> str:
        """Create a new session for a user"""
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        
        # Set session expiry (random duration within bounds)
        session_duration = random.randint(self.session_min_duration, self.session_max_duration)
        expiry_time = datetime.utcnow() + timedelta(seconds=session_duration)
        
        self.active_sessions[session_id] = {
            "user_id": user_id,
            "created_at": datetime.utcnow(),
            "expires_at": expiry_time,
            "ip_address": self.users[user_id]["frequent_ip"] if random.random() < 0.7 else self.generate_ip_address(),
            "user_agent": self.fake.user_agent()
        }
        
        return session_id
    
    def end_session(self, session_id: str) -> None:
        """End a user session"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
    
    def get_random_session(self) -> Optional[Dict[str, Any]]:
        """Get a random active session if any exists"""
        if not self.active_sessions:
            return None
        
        session_id = random.choice(list(self.active_sessions.keys()))
        session_data = self.active_sessions[session_id]
        
        # Check if session is expired
        if session_data["expires_at"] < datetime.utcnow():
            # Session expired, remove it
            self.end_session(session_id)
            return None
            
        return {"session_id": session_id, **session_data}
    
    def generate_event(self, correlation_id: Optional[str] = None) -> SecurityEvent:
        """Generate a security event with realistic properties"""
        # Select event type based on weighted distribution
        event_type = random.choice(self.event_types)
        
        # Select a user - prefer existing users
        user_id = random.choice(list(self.users.keys()))
        user_data = self.users[user_id]
        user_type = user_data["user_type"]
        
        # Base event data
        event_data = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow(),
            "event_type": event_type,
            "user_id": user_id,
            "user_type": user_type,
            "correlation_id": correlation_id or str(uuid.uuid4()),
            "severity": self.get_severity_for_event(event_type),
            "tags": self.get_tags_for_event(event_type, user_type),
            "source_system": random.choice(self.systems),
            "target_system": random.choice(self.systems),
            "additional_info": {}
        }
        
        # Get or create session information
        session = None
        if event_type == EventType.LOGIN_SUCCESS:
            # Create a new session
            session_id = self.create_session(user_id)
            session = self.active_sessions[session_id]
            event_data["session_id"] = session_id
        elif event_type == EventType.LOGOUT:
            # Get an existing session to end
            session = self.get_random_session()
            if session:
                event_data["session_id"] = session["session_id"]
                self.end_session(session["session_id"])
            else:
                # No active session, switch to a different event type
                event_type = EventType.LOGIN_SUCCESS
                event_data["event_type"] = event_type
                session_id = self.create_session(user_id)
                session = self.active_sessions[session_id]
                event_data["session_id"] = session_id
        else:
            # For other events, try to use an existing session
            session = self.get_random_session()
            if session:
                event_data["session_id"] = session["session_id"]
                # Use the session's user data
                user_id = session["user_id"]
                event_data["user_id"] = user_id
                user_data = self.users[user_id]
                event_data["user_type"] = user_data["user_type"]
        
        # Set IP address and user agent (from session if available, otherwise generate)
        if session:
            event_data["ip_address"] = session["ip_address"]
            event_data["user_agent"] = session["user_agent"]
        else:
            # 70% chance to use the user's frequent IP, 30% chance for a random one
            event_data["ip_address"] = user_data["frequent_ip"] if random.random() < 0.7 else self.generate_ip_address()
            event_data["user_agent"] = self.fake.user_agent()
        
        # Add geolocation data
        event_data["geo_location"] = GeoLocation(
            country=user_data["country"],
            city=user_data["city"],
            latitude=user_data["latitude"],
            longitude=user_data["longitude"]
        )
        
        # Customize based on event type
        if event_type == EventType.LOGIN_SUCCESS:
            event_data.update({
                "status_code": 200,
                "message": "Successful login attempt",
                "additional_info": {
                    "login_type": random.choice(["password", "sso", "2fa", "oauth"]),
                    "device_type": user_data["preferred_device"],
                    "auth_provider": random.choice(["local", "google", "github", "okta", "azure-ad"])
                }
            })
        elif event_type == EventType.LOGIN_FAILURE:
            failure_reason = random.choice([
                "invalid_password",
                "account_locked",
                "invalid_2fa",
                "expired_password",
                "invalid_username",
                "account_disabled"
            ])
            
            event_data.update({
                "status_code": 401,
                "message": f"Failed login attempt: {failure_reason}",
                "additional_info": {
                    "failure_reason": failure_reason,
                    "attempt_number": random.randint(1, 5),
                    "device_type": random.choice(["desktop", "mobile", "tablet"])
                }
            })
        elif event_type == EventType.LOGOUT:
            event_data.update({
                "status_code": 200,
                "message": "User logged out successfully",
                "additional_info": {
                    "logout_type": random.choice(["user_initiated", "session_timeout", "admin_action"]),
                    "session_duration": random.randint(60, 3600)  # 1 minute to 1 hour in seconds
                }
            })
        elif event_type == EventType.UNAUTHORIZED_ACCESS:
            resource = random.choice(self.resources)
            required_role = random.choice(["admin", "superuser", "manager", "security-officer", "data-admin"])
            
            event_data.update({
                "status_code": 403,
                "message": f"Unauthorized access attempt to {resource}",
                "additional_info": {
                    "resource": resource,
                    "required_role": required_role,
                    "user_role": random.choice(["user", "viewer", "editor", "guest"])
                }
            })
        elif event_type == EventType.PRIVILEGE_ESCALATION:
            event_data.update({
                "status_code": 400,
                "message": "Attempted privilege escalation detected",
                "additional_info": {
                    "target_role": random.choice(["admin", "superuser", "root"]),
                    "method": random.choice(["injection", "token_manipulation", "vulnerability_exploit"]),
                    "detection_source": random.choice(["waf", "ids", "audit_log", "behavior_analysis"])
                }
            })
        elif event_type == EventType.PASSWORD_CHANGE:
            event_data.update({
                "status_code": 200,
                "message": "Password successfully changed",
                "additional_info": {
                    "initiated_by": random.choice(["user", "admin", "password_policy", "security_alert"]),
                    "password_strength": random.choice(["weak", "medium", "strong"]),
                    "forced_change": random.choice([True, False])
                }
            })
        elif event_type == EventType.MFA_CHALLENGE:
            success = random.choice([True, False])
            status_code = 200 if success else 401
            
            event_data.update({
                "status_code": status_code,
                "message": f"MFA challenge {'completed' if success else 'failed'}",
                "additional_info": {
                    "mfa_type": random.choice(["sms", "app", "email", "hardware_token"]),
                    "success": success,
                    "attempt_number": random.randint(1, 3)
                }
            })
        elif event_type == EventType.ACCOUNT_LOCKOUT:
            event_data.update({
                "status_code": 403,
                "message": "Account locked due to excessive failed login attempts",
                "additional_info": {
                    "failed_attempts": random.randint(3, 10),
                    "lockout_duration_minutes": random.choice([15, 30, 60, 1440]),  # 15 min to 24 hours
                    "unlock_method": random.choice(["time_based", "admin_action", "self_service"])
                }
            })
        elif event_type == EventType.DATA_ACCESS:
            data_type = random.choice(["customer", "financial", "employee", "product", "operational"])
            
            event_data.update({
                "status_code": 200,
                "message": f"Data access: {data_type} records",
                "additional_info": {
                    "data_type": data_type,
                    "records_accessed": random.randint(1, 1000),
                    "access_purpose": random.choice(["reporting", "analysis", "customer_service", "maintenance"]),
                    "data_classification": random.choice(["public", "internal", "confidential", "restricted"])
                }
            })
        elif event_type == EventType.DATA_MODIFICATION:
            data_type = random.choice(["user", "configuration", "content", "financial", "system"])
            
            event_data.update({
                "status_code": 200,
                "message": f"Data modification: {data_type} records updated",
                "additional_info": {
                    "data_type": data_type,
                    "records_modified": random.randint(1, 100),
                    "modification_type": random.choice(["update", "delete", "create", "bulk_update"]),
                    "approved_change": random.choice([True, False, True])  # More likely to be approved
                }
            })
        elif event_type == EventType.DATA_EXFILTRATION:
            data_type = random.choice(["customer", "financial", "employee", "intellectual_property"])
            
            event_data.update({
                "status_code": 400,
                "message": f"Potential data exfiltration detected: {data_type} data",
                "additional_info": {
                    "data_type": data_type,
                    "volume_mb": random.randint(1, 1000),
                    "detection_method": random.choice(["dlp", "network_monitor", "behavior_analysis", "honeypot"]),
                    "destination_ip": self.fake.ipv4_public(),
                    "confidence_score": random.randint(60, 100)
                }
            })
        elif event_type in [EventType.SYSTEM_STARTUP, EventType.SYSTEM_SHUTDOWN]:
            action = "started" if event_type == EventType.SYSTEM_STARTUP else "shut down"
            
            event_data.update({
                "status_code": 200,
                "message": f"System {action}",
                "additional_info": {
                    "server_id": f"srv-{self.fake.hexify(text='??????')}",
                    "environment": random.choice(["production", "staging", "development", "testing"]),
                    "initiated_by": random.choice(["scheduled_maintenance", "manual", "automated_process", "system_failure"])
                }
            })
        elif event_type == EventType.CONFIG_CHANGE:
            component = random.choice(["firewall", "authentication", "authorization", "logging", "network", "storage"])
            
            event_data.update({
                "status_code": 200,
                "message": f"Configuration changed: {component} settings",
                "additional_info": {
                    "component": component,
                    "change_type": random.choice(["update", "create", "delete"]),
                    "approved_change": random.choice([True, False, True]),  # More likely to be approved
                    "change_ticket": f"CHG-{self.fake.numerify(text='######')}"
                }
            })
        elif event_type == EventType.PERMISSION_CHANGE:
            event_data.update({
                "status_code": 200,
                "message": "User permissions modified",
                "additional_info": {
                    "target_user": f"user_{random.randint(1, 1000)}",
                    "permission_type": random.choice(["role_assignment", "group_membership", "direct_permission"]),
                    "permission_change": random.choice(["granted", "revoked", "modified"]),
                    "permissions": random.sample(["read", "write", "delete", "admin", "execute", "create"], random.randint(1, 3))
                }
            })

        return SecurityEvent(**event_data) 