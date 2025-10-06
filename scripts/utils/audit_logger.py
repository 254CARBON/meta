#!/usr/bin/env python3
"""
Audit Logger for Compliance and State Change Tracking

Provides structured audit logging for compliance, security, and operational tracking.
Captures detailed context including user, workflow, parameters, and state changes.

Features:
- Structured JSON logging with consistent format
- User action tracking with context
- State change monitoring
- Compliance-ready logging
- Log rotation and retention policies
- Searchable and filterable logs
- Integration with existing logging framework

Usage:
    from scripts.utils.audit_logger import audit_logger

    # Log user actions
    audit_logger.log_action(
        user="system",
        action="catalog_update",
        resource="gateway",
        details={"version": "1.2.0", "changes": 5}
    )

    # Log state changes
    audit_logger.log_state_change(
        resource="quality_scores",
        old_state={"gateway": 0.85},
        new_state={"gateway": 0.92},
        reason="quality_computation_completed"
    )
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class AuditLevel(Enum):
    """Audit log levels for different types of events."""
    INFO = "info"           # General information
    WARNING = "warning"     # Potential issues
    ERROR = "error"         # Errors and failures
    CRITICAL = "critical"   # Security or compliance violations
    SUCCESS = "success"     # Successful operations


class AuditCategory(Enum):
    """Categories for organizing audit events."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    CONFIGURATION = "configuration"
    SYSTEM_OPERATION = "system_operation"
    COMPLIANCE = "compliance"
    SECURITY = "security"
    WORKFLOW = "workflow"
    QUALITY = "quality"
    DRIFT = "drift"
    RELEASE = "release"


@dataclass
class AuditEvent:
    """Structured audit event data."""
    timestamp: str
    level: str
    category: str
    user: str
    action: str
    resource: Optional[str]
    resource_type: Optional[str]
    details: Dict[str, Any]
    context: Dict[str, Any]
    session_id: Optional[str]
    request_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    outcome: str
    error_message: Optional[str]
    duration_ms: Optional[float]
    metadata: Dict[str, Any]


class AuditLogger:
    """
    Audit logger for compliance and operational tracking.
    
    Provides structured logging with detailed context capture,
    log rotation, and search capabilities for compliance reporting.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, log_file: str = "audit.log", max_file_size: int = 100 * 1024 * 1024):
        """
        Initialize audit logger.
        
        Args:
            log_file: Path to audit log file
            max_file_size: Maximum file size before rotation (bytes)
        """
        self.log_file = Path(log_file)
        self.max_file_size = max_file_size
        self._lock = threading.Lock()
        self._session_counter = 0
        
        # Ensure log directory exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup file handler
        self._setup_file_handler()
        
        logger.info(f"Audit logger initialized: {self.log_file}")
    
    @classmethod
    def get_instance(cls, log_file: str = "audit.log") -> 'AuditLogger':
        """Get singleton instance of audit logger."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(log_file)
        return cls._instance
    
    def _setup_file_handler(self):
        """Setup file handler for audit logging."""
        self.file_handler = logging.FileHandler(self.log_file)
        self.file_handler.setLevel(logging.INFO)
        
        # Custom formatter for structured JSON logging
        formatter = logging.Formatter('%(message)s')
        self.file_handler.setFormatter(formatter)
        
        # Add handler to audit logger
        audit_logger = logging.getLogger('audit')
        audit_logger.addHandler(self.file_handler)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        self._session_counter += 1
        return f"session_{int(time.time())}_{self._session_counter}"
    
    def _create_audit_event(
        self,
        level: AuditLevel,
        category: AuditCategory,
        user: str,
        action: str,
        resource: Optional[str] = None,
        resource_type: Optional[str] = None,
        details: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        outcome: str = "success",
        error_message: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Dict[str, Any] = None
    ) -> AuditEvent:
        """Create structured audit event."""
        return AuditEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            level=level.value,
            category=category.value,
            user=user,
            action=action,
            resource=resource,
            resource_type=resource_type,
            details=details or {},
            context=context or {},
            session_id=session_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            outcome=outcome,
            error_message=error_message,
            duration_ms=duration_ms,
            metadata=metadata or {}
        )
    
    def _write_event(self, event: AuditEvent):
        """Write audit event to log file."""
        try:
            with self._lock:
                # Check file size and rotate if needed
                if self.log_file.exists() and self.log_file.stat().st_size > self.max_file_size:
                    self._rotate_log_file()
                
                # Write JSON event
                audit_logger = logging.getLogger('audit')
                audit_logger.info(json.dumps(asdict(event), default=str))
                
        except Exception as e:
            logger.error(f"Failed to write audit event: {e}")
    
    def _rotate_log_file(self):
        """Rotate log file when it gets too large."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_file = self.log_file.with_suffix(f".{timestamp}.log")
            
            # Move current file
            self.log_file.rename(rotated_file)
            
            # Remove old rotated files (keep last 10)
            self._cleanup_old_logs()
            
            logger.info(f"Audit log rotated: {rotated_file}")
            
        except Exception as e:
            logger.error(f"Failed to rotate audit log: {e}")
    
    def _cleanup_old_logs(self, keep_count: int = 10):
        """Clean up old rotated log files."""
        try:
            log_dir = self.log_file.parent
            pattern = f"{self.log_file.stem}.*.log"
            
            rotated_files = sorted(
                log_dir.glob(pattern),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )
            
            # Remove files beyond keep_count
            for old_file in rotated_files[keep_count:]:
                old_file.unlink()
                logger.debug(f"Removed old audit log: {old_file}")
                
        except Exception as e:
            logger.warning(f"Failed to cleanup old logs: {e}")
    
    def log_action(
        self,
        user: str,
        action: str,
        resource: Optional[str] = None,
        resource_type: Optional[str] = None,
        details: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        level: AuditLevel = AuditLevel.INFO,
        category: AuditCategory = AuditCategory.SYSTEM_OPERATION,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        outcome: str = "success",
        error_message: Optional[str] = None,
        duration_ms: Optional[float] = None,
        metadata: Dict[str, Any] = None
    ):
        """Log a user action."""
        event = self._create_audit_event(
            level=level,
            category=category,
            user=user,
            action=action,
            resource=resource,
            resource_type=resource_type,
            details=details,
            context=context,
            session_id=session_id,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            outcome=outcome,
            error_message=error_message,
            duration_ms=duration_ms,
            metadata=metadata
        )
        
        self._write_event(event)
    
    def log_state_change(
        self,
        resource: str,
        resource_type: str,
        old_state: Dict[str, Any],
        new_state: Dict[str, Any],
        user: str = "system",
        reason: str = "state_change",
        details: Dict[str, Any] = None,
        context: Dict[str, Any] = None
    ):
        """Log a state change event."""
        change_details = {
            "old_state": old_state,
            "new_state": new_state,
            "reason": reason,
            "changed_fields": self._get_changed_fields(old_state, new_state)
        }
        
        if details:
            change_details.update(details)
        
        self.log_action(
            user=user,
            action="state_change",
            resource=resource,
            resource_type=resource_type,
            details=change_details,
            context=context,
            level=AuditLevel.INFO,
            category=AuditCategory.DATA_MODIFICATION
        )
    
    def log_data_access(
        self,
        user: str,
        resource: str,
        resource_type: str,
        access_type: str = "read",
        details: Dict[str, Any] = None,
        context: Dict[str, Any] = None
    ):
        """Log data access event."""
        self.log_action(
            user=user,
            action=f"data_{access_type}",
            resource=resource,
            resource_type=resource_type,
            details=details,
            context=context,
            level=AuditLevel.INFO,
            category=AuditCategory.DATA_ACCESS
        )
    
    def log_configuration_change(
        self,
        user: str,
        config_item: str,
        old_value: Any,
        new_value: Any,
        details: Dict[str, Any] = None,
        context: Dict[str, Any] = None
    ):
        """Log configuration change."""
        config_details = {
            "config_item": config_item,
            "old_value": old_value,
            "new_value": new_value
        }
        
        if details:
            config_details.update(details)
        
        self.log_action(
            user=user,
            action="config_change",
            resource=config_item,
            resource_type="configuration",
            details=config_details,
            context=context,
            level=AuditLevel.WARNING,
            category=AuditCategory.CONFIGURATION
        )
    
    def log_workflow_execution(
        self,
        workflow_name: str,
        user: str = "system",
        status: str = "started",
        details: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        duration_ms: Optional[float] = None,
        error_message: Optional[str] = None
    ):
        """Log workflow execution event."""
        workflow_details = {
            "workflow_name": workflow_name,
            "status": status
        }
        
        if details:
            workflow_details.update(details)
        
        level = AuditLevel.SUCCESS if status == "completed" else AuditLevel.INFO
        if status == "failed":
            level = AuditLevel.ERROR
        
        self.log_action(
            user=user,
            action="workflow_execution",
            resource=workflow_name,
            resource_type="workflow",
            details=workflow_details,
            context=context,
            level=level,
            category=AuditCategory.WORKFLOW,
            outcome=status,
            duration_ms=duration_ms,
            error_message=error_message
        )
    
    def log_security_event(
        self,
        event_type: str,
        user: str,
        details: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        level: AuditLevel = AuditLevel.WARNING
    ):
        """Log security-related event."""
        self.log_action(
            user=user,
            action=event_type,
            details=details,
            context=context,
            level=level,
            category=AuditCategory.SECURITY
        )
    
    def log_compliance_event(
        self,
        compliance_type: str,
        user: str,
        details: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        status: str = "compliant"
    ):
        """Log compliance-related event."""
        compliance_details = {
            "compliance_type": compliance_type,
            "status": status
        }
        
        if details:
            compliance_details.update(details)
        
        level = AuditLevel.SUCCESS if status == "compliant" else AuditLevel.ERROR
        
        self.log_action(
            user=user,
            action="compliance_check",
            details=compliance_details,
            context=context,
            level=level,
            category=AuditCategory.COMPLIANCE,
            outcome=status
        )
    
    def _get_changed_fields(self, old_state: Dict[str, Any], new_state: Dict[str, Any]) -> List[str]:
        """Get list of changed fields between two states."""
        changed_fields = []
        
        # Check for new or changed fields
        for key, new_value in new_state.items():
            old_value = old_state.get(key)
            if old_value != new_value:
                changed_fields.append(key)
        
        # Check for removed fields
        for key in old_state.keys():
            if key not in new_state:
                changed_fields.append(f"{key} (removed)")
        
        return changed_fields
    
    def search_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        level: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Search audit logs with filters."""
        results = []
        
        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        
                        # Apply filters
                        if start_time and datetime.fromisoformat(event['timestamp'].replace('Z', '')) < start_time:
                            continue
                        if end_time and datetime.fromisoformat(event['timestamp'].replace('Z', '')) > end_time:
                            continue
                        if user and event.get('user') != user:
                            continue
                        if action and event.get('action') != action:
                            continue
                        if resource and event.get('resource') != resource:
                            continue
                        if level and event.get('level') != level:
                            continue
                        if category and event.get('category') != category:
                            continue
                        
                        results.append(event)
                        
                        if len(results) >= limit:
                            break
                            
                    except json.JSONDecodeError:
                        continue
                        
        except FileNotFoundError:
            logger.warning("Audit log file not found")
        except Exception as e:
            logger.error(f"Error searching audit logs: {e}")
        
        return results
    
    def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get audit log statistics for the last N days."""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        
        events = self.search_logs(start_time=start_time, end_time=end_time, limit=10000)
        
        stats = {
            "total_events": len(events),
            "events_by_level": {},
            "events_by_category": {},
            "events_by_user": {},
            "events_by_action": {},
            "daily_counts": {},
            "error_rate": 0.0,
            "top_resources": {}
        }
        
        error_count = 0
        
        for event in events:
            # Count by level
            level = event.get('level', 'unknown')
            stats["events_by_level"][level] = stats["events_by_level"].get(level, 0) + 1
            
            # Count by category
            category = event.get('category', 'unknown')
            stats["events_by_category"][category] = stats["events_by_category"].get(category, 0) + 1
            
            # Count by user
            user = event.get('user', 'unknown')
            stats["events_by_user"][user] = stats["events_by_user"].get(user, 0) + 1
            
            # Count by action
            action = event.get('action', 'unknown')
            stats["events_by_action"][action] = stats["events_by_action"].get(action, 0) + 1
            
            # Count by resource
            resource = event.get('resource')
            if resource:
                stats["top_resources"][resource] = stats["top_resources"].get(resource, 0) + 1
            
            # Daily counts
            event_date = event['timestamp'][:10]  # YYYY-MM-DD
            stats["daily_counts"][event_date] = stats["daily_counts"].get(event_date, 0) + 1
            
            # Error count
            if event.get('level') in ['error', 'critical']:
                error_count += 1
        
        # Calculate error rate
        if len(events) > 0:
            stats["error_rate"] = error_count / len(events)
        
        return stats


# Global audit logger instance
audit_logger = AuditLogger.get_instance()


# Convenience functions for common audit operations
def log_catalog_update(service_name: str, changes: Dict[str, Any], user: str = "system"):
    """Log catalog update event."""
    audit_logger.log_action(
        user=user,
        action="catalog_update",
        resource=service_name,
        resource_type="service",
        details=changes,
        category=AuditCategory.DATA_MODIFICATION
    )


def log_quality_change(service_name: str, old_score: float, new_score: float, user: str = "system"):
    """Log quality score change."""
    audit_logger.log_state_change(
        resource=service_name,
        resource_type="quality_score",
        old_state={"score": old_score},
        new_state={"score": new_score},
        user=user,
        reason="quality_computation"
    )


def log_drift_detection(service_name: str, drift_type: str, severity: str, user: str = "system"):
    """Log drift detection event."""
    audit_logger.log_action(
        user=user,
        action="drift_detected",
        resource=service_name,
        resource_type="service",
        details={"drift_type": drift_type, "severity": severity},
        category=AuditCategory.DRIFT,
        level=AuditLevel.WARNING if severity == "high" else AuditLevel.INFO
    )


def log_release_train_execution(train_name: str, status: str, services: List[str], user: str = "system"):
    """Log release train execution."""
    audit_logger.log_workflow_execution(
        workflow_name=train_name,
        user=user,
        status=status,
        details={"services": services, "service_count": len(services)},
        category=AuditCategory.RELEASE
    )


# Example usage and testing
if __name__ == "__main__":
    import logging
    import time
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n=== Audit Logger Demo ===\n")
    
    # Example 1: Basic action logging
    print("1. Basic action logging:")
    audit_logger.log_action(
        user="admin",
        action="login",
        resource="system",
        details={"method": "oauth", "provider": "github"}
    )
    
    # Example 2: State change logging
    print("2. State change logging:")
    audit_logger.log_state_change(
        resource="gateway",
        resource_type="service",
        old_state={"version": "1.0.0", "status": "stable"},
        new_state={"version": "1.1.0", "status": "stable"},
        user="system",
        reason="version_upgrade"
    )
    
    # Example 3: Workflow execution logging
    print("3. Workflow execution logging:")
    audit_logger.log_workflow_execution(
        workflow_name="catalog_build",
        user="system",
        status="started",
        details={"services_count": 25, "parallel": True}
    )
    
    time.sleep(0.1)  # Simulate work
    
    audit_logger.log_workflow_execution(
        workflow_name="catalog_build",
        user="system",
        status="completed",
        details={"services_count": 25, "duration": 2.5},
        duration_ms=2500.0
    )
    
    # Example 4: Convenience functions
    print("4. Convenience functions:")
    log_catalog_update("gateway", {"version": "1.2.0", "dependencies": 3})
    log_quality_change("gateway", 0.85, 0.92)
    log_drift_detection("gateway", "dependency", "medium")
    log_release_train_execution("train-2024-01", "completed", ["gateway", "auth"])
    
    # Example 5: Search logs
    print("\n5. Search logs:")
    recent_events = audit_logger.search_logs(limit=5)
    print(f"   Found {len(recent_events)} recent events")
    
    for event in recent_events:
        print(f"   - {event['timestamp']}: {event['action']} by {event['user']}")
    
    # Example 6: Statistics
    print("\n6. Statistics:")
    stats = audit_logger.get_statistics(days=1)
    print(f"   Total events: {stats['total_events']}")
    print(f"   Events by level: {stats['events_by_level']}")
    print(f"   Events by category: {stats['events_by_category']}")
    
    print("\n=== Demo complete ===\n")
    print("Audit logger is ready for production use!")
    print("Use audit_logger.log_action() for detailed compliance tracking.")
