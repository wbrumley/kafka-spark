from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, IPvAnyAddress

class EventType(str, Enum):
    # Authentication events
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    MFA_CHALLENGE = "MFA_CHALLENGE"
    ACCOUNT_LOCKOUT = "ACCOUNT_LOCKOUT"
    
    # Authorization events
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    PERMISSION_CHANGE = "PERMISSION_CHANGE"
    
    # Data events
    DATA_ACCESS = "DATA_ACCESS"
    DATA_MODIFICATION = "DATA_MODIFICATION"
    DATA_EXFILTRATION = "DATA_EXFILTRATION"
    
    # System events
    SYSTEM_STARTUP = "SYSTEM_STARTUP"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"
    CONFIG_CHANGE = "CONFIG_CHANGE"

class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class UserType(str, Enum):
    EMPLOYEE = "EMPLOYEE"
    CONTRACTOR = "CONTRACTOR"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"
    CUSTOMER = "CUSTOMER"
    ANONYMOUS = "ANONYMOUS"

class GeoLocation(BaseModel):
    country: str
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class SecurityEvent(BaseModel):
    event_id: str = Field(..., description="Unique identifier for the event")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: EventType
    user_id: str
    user_type: Optional[UserType] = None
    ip_address: str
    geo_location: Optional[GeoLocation] = None
    user_agent: str
    status_code: int = Field(..., description="HTTP status code or similar")
    message: str
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    severity: Optional[Severity] = None
    source_system: Optional[str] = None
    target_system: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    additional_info: dict = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "123e4567-e89b-12d3-a456-426614174000",
                "timestamp": "2024-01-19T10:00:00Z",
                "event_type": "LOGIN_SUCCESS",
                "user_id": "user123",
                "user_type": "EMPLOYEE",
                "ip_address": "192.168.1.1",
                "geo_location": {
                    "country": "United States",
                    "city": "San Francisco",
                    "latitude": 37.7749,
                    "longitude": -122.4194
                },
                "user_agent": "Mozilla/5.0",
                "status_code": 200,
                "message": "Successful login attempt",
                "correlation_id": "corr123",
                "session_id": "sess456",
                "severity": "INFO",
                "source_system": "web-portal",
                "target_system": "auth-service",
                "tags": ["authentication", "web"],
                "additional_info": {"auth_method": "password", "device_type": "desktop"}
            }
        } 