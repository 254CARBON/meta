#!/usr/bin/env python3
"""
254Carbon Meta Repository - Release Train Rollback Script

Provides emergency rollback capabilities for release trains when issues are detected.
Supports both automated and manual rollback with comprehensive safety checks.

Usage:
    python scripts/rollback_release_train.py [--train-name NAME] [--reason REASON] [--dry-run]

Features:
- Emergency rollback for failed release trains
- Safety checks and validation
- Rollback plan generation
- Service version restoration
- Health verification after rollback
- Audit logging and compliance
- Integration with monitoring systems
- Rollback status tracking
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from scripts.utils import audit_logger, monitor_execution, redis_client, error_recovery

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/rollback.log')
    ]
)
logger = logging.getLogger(__name__)


class RollbackStatus(Enum):
    """Rollback status values."""
    PLANNING = "planning"
    VALIDATING = "validating"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ServiceRollbackStatus(Enum):
    """Individual service rollback status values."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ROLLED_BACK = "rolled_back"
    VERIFIED = "verified"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ServiceRollbackInfo:
    """Information about a service's rollback."""
    service_name: str
    current_version: str
    target_version: str
    previous_version: str
    status: ServiceRollbackStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    health_status: str = "unknown"
    rollback_method: str = "version_rollback"
    backup_available: bool = True
    dependencies_affected: List[str] = field(default_factory=list)


@dataclass
class RollbackPlan:
    """Rollback plan for a release train."""
    train_name: str
    reason: str
    initiated_by: str
    initiated_at: datetime
    status: RollbackStatus
    services: List[ServiceRollbackInfo] = field(default_factory=list)
    rollback_order: List[str] = field(default_factory=list)
    safety_checks: List[str] = field(default_factory=list)
    estimated_duration: Optional[timedelta] = None
    rollback_window: Optional[timedelta] = None
    health_checks: Dict[str, Any] = field(default_factory=dict)
    rollback_artifacts: Dict[str, Any] = field(default_factory=dict)


class ReleaseTrainRollback:
    """Handles rollback operations for release trains."""

    def __init__(self, train_name: str, reason: str = None, dry_run: bool = False):
        """
        Initialize release train rollback.
        
        Args:
            train_name: Name of the release train to rollback
            reason: Reason for rollback
            dry_run: Whether to simulate rollback without executing
        """
        self.train_name = train_name
        self.reason = reason or "Emergency rollback"
        self.dry_run = dry_run
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize rollback data
        self.rollback_plan: Optional[RollbackPlan] = None
        self.rollback_history: List[Dict[str, Any]] = []
        
        # GitHub API configuration
        self.github_token = os.getenv('GITHUB_TOKEN')
        self.github_api_base = "https://api.github.com"
        
        logger.info(f"Release train rollback initialized: train={train_name}, reason={reason}, dry_run={dry_run}")

    def _load_config(self) -> Dict[str, Any]:
        """Load rollback configuration."""
        config_file = Path("config/rollback-policies.yaml")
        if not config_file.exists():
            return self._get_default_config()
        
        with open(config_file) as f:
            return yaml.safe_load(f)

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default rollback configuration."""
        return {
            "safety_checks": {
                "health_check_timeout": 60,
                "rollback_timeout": 300,
                "max_concurrent_rollbacks": 3,
                "require_approval": False
            },
            "rollback_methods": {
                "default": "version_rollback",
                "available_methods": ["version_rollback", "image_rollback", "config_rollback"]
            },
            "notifications": {
                "enabled": True,
                "channels": ["slack", "email"],
                "stakeholders": ["platform-team", "release-managers"]
            },
            "audit": {
                "log_all_actions": True,
                "require_reason": True,
                "retention_days": 90
            }
        }

    @monitor_execution("release-train-rollback")
    def execute_rollback(self) -> bool:
        """Execute the rollback process."""
        logger.info(f"Starting rollback for release train: {self.train_name}")
        
        try:
            # Load release train information
            if not self._load_release_train_info():
                logger.error(f"Failed to load release train information for: {self.train_name}")
                return False
            
            # Generate rollback plan
            if not self._generate_rollback_plan():
                logger.error("Failed to generate rollback plan")
                return False
            
            # Validate rollback plan
            if not self._validate_rollback_plan():
                logger.error("Rollback plan validation failed")
                return False
            
            # Execute rollback
            if self.dry_run:
                logger.info("DRY RUN: Would execute rollback plan")
                self._simulate_rollback()
                return True
            else:
                return self._execute_rollback_plan()
            
        except Exception as e:
            logger.error(f"Rollback execution failed: {e}")
            return False

    def _load_release_train_info(self) -> bool:
        """Load release train information."""
        try:
            # Load from release trains file
            release_trains_file = Path("catalog/release-trains.yaml")
            if not release_trains_file.exists():
                logger.error("Release trains file not found")
                return False
            
            with open(release_trains_file) as f:
                trains_data = yaml.safe_load(f)
            
            # Find the specific train
            train_data = None
            for train in trains_data.get('trains', []):
                if train['name'] == self.train_name:
                    train_data = train
                    break
            
            if not train_data:
                logger.error(f"Release train '{self.train_name}' not found")
                return False
            
            # Load service information
            self.train_data = train_data
            self.participants = train_data.get('participants', [])
            
            logger.info(f"Loaded release train info: {len(self.participants)} participants")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load release train info: {e}")
            return False

    def _generate_rollback_plan(self) -> bool:
        """Generate comprehensive rollback plan."""
        logger.info("Generating rollback plan...")
        
        try:
            # Create rollback plan
            self.rollback_plan = RollbackPlan(
                train_name=self.train_name,
                reason=self.reason,
                initiated_by=os.getenv('USER', 'system'),
                initiated_at=datetime.now(),
                status=RollbackStatus.PLANNING
            )
            
            # Generate service rollback info
            for participant in self.participants:
                service_info = self._get_service_rollback_info(participant)
                self.rollback_plan.services.append(service_info)
            
            # Determine rollback order (reverse dependency order)
            self.rollback_plan.rollback_order = self._determine_rollback_order()
            
            # Add safety checks
            self.rollback_plan.safety_checks = self._generate_safety_checks()
            
            # Estimate duration
            self.rollback_plan.estimated_duration = self._estimate_rollback_duration()
            
            # Set rollback window
            self.rollback_plan.rollback_window = timedelta(hours=24)  # 24 hour window
            
            logger.info(f"Rollback plan generated: {len(self.rollback_plan.services)} services")
            return True
            
        except Exception as e:
            logger.error(f"Failed to generate rollback plan: {e}")
            return False

    def _get_service_rollback_info(self, service_name: str) -> ServiceRollbackInfo:
        """Get rollback information for a specific service."""
        try:
            # Get current version
            current_version = self._get_service_current_version(service_name)
            
            # Get previous version (from backup or history)
            previous_version = self._get_service_previous_version(service_name)
            
            # Determine rollback method
            rollback_method = self._determine_rollback_method(service_name)
            
            # Check backup availability
            backup_available = self._check_backup_availability(service_name)
            
            # Get affected dependencies
            dependencies_affected = self._get_affected_dependencies(service_name)
            
            return ServiceRollbackInfo(
                service_name=service_name,
                current_version=current_version or "unknown",
                target_version=self.train_data.get('target_version', 'unknown'),
                previous_version=previous_version or "unknown",
                status=ServiceRollbackStatus.PENDING,
                rollback_method=rollback_method,
                backup_available=backup_available,
                dependencies_affected=dependencies_affected
            )
            
        except Exception as e:
            logger.error(f"Failed to get rollback info for {service_name}: {e}")
            return ServiceRollbackInfo(
                service_name=service_name,
                current_version="unknown",
                target_version="unknown",
                previous_version="unknown",
                status=ServiceRollbackStatus.FAILED,
                error_message=str(e)
            )

    def _get_service_current_version(self, service_name: str) -> Optional[str]:
        """Get current deployed version of a service."""
        try:
            # This would integrate with actual deployment system
            # For now, return mock data
            return "1.1.0"
        except Exception as e:
            logger.error(f"Failed to get current version for {service_name}: {e}")
            return None

    def _get_service_previous_version(self, service_name: str) -> Optional[str]:
        """Get previous version for rollback."""
        try:
            # This would check backup systems or version history
            # For now, return mock data
            return "1.0.0"
        except Exception as e:
            logger.error(f"Failed to get previous version for {service_name}: {e}")
            return None

    def _determine_rollback_method(self, service_name: str) -> str:
        """Determine the best rollback method for a service."""
        # This would analyze the service type and deployment method
        # For now, return default method
        return self.config["rollback_methods"]["default"]

    def _check_backup_availability(self, service_name: str) -> bool:
        """Check if backup is available for rollback."""
        try:
            # This would check backup systems
            # For now, return True
            return True
        except Exception as e:
            logger.error(f"Failed to check backup availability for {service_name}: {e}")
            return False

    def _get_affected_dependencies(self, service_name: str) -> List[str]:
        """Get list of services that depend on this service."""
        try:
            # This would analyze the dependency graph
            # For now, return empty list
            return []
        except Exception as e:
            logger.error(f"Failed to get affected dependencies for {service_name}: {e}")
            return []

    def _determine_rollback_order(self) -> List[str]:
        """Determine the order in which services should be rolled back."""
        try:
            # This would analyze the dependency graph to determine reverse order
            # For now, return the participants in reverse order
            return list(reversed(self.participants))
        except Exception as e:
            logger.error(f"Failed to determine rollback order: {e}")
            return self.participants

    def _generate_safety_checks(self) -> List[str]:
        """Generate list of safety checks to perform."""
        return [
            "Verify all services are healthy before rollback",
            "Check for active user sessions",
            "Validate backup integrity",
            "Confirm rollback window is within limits",
            "Check for critical dependencies",
            "Verify rollback permissions",
            "Validate service compatibility"
        ]

    def _estimate_rollback_duration(self) -> timedelta:
        """Estimate total rollback duration."""
        # Base time per service
        base_time_per_service = timedelta(minutes=5)
        
        # Additional time for dependencies
        dependency_time = timedelta(minutes=2) * len(self.participants)
        
        # Safety buffer
        safety_buffer = timedelta(minutes=10)
        
        return base_time_per_service * len(self.participants) + dependency_time + safety_buffer

    def _validate_rollback_plan(self) -> bool:
        """Validate the rollback plan."""
        logger.info("Validating rollback plan...")
        
        try:
            # Check if rollback window is still valid
            if self.rollback_plan.rollback_window:
                window_end = self.rollback_plan.initiated_at + self.rollback_plan.rollback_window
                if datetime.now() > window_end:
                    logger.error("Rollback window has expired")
                    return False
            
            # Check backup availability
            for service_info in self.rollback_plan.services:
                if not service_info.backup_available:
                    logger.error(f"No backup available for service: {service_info.service_name}")
                    return False
            
            # Check service health
            for service_info in self.rollback_plan.services:
                health_status = self._check_service_health(service_info.service_name)
                if health_status == 'critical':
                    logger.error(f"Service {service_info.service_name} is in critical state")
                    return False
            
            # Check for active deployments
            if self._check_active_deployments():
                logger.error("Active deployments detected, cannot proceed with rollback")
                return False
            
            logger.info("Rollback plan validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Rollback plan validation failed: {e}")
            return False

    def _check_service_health(self, service_name: str) -> str:
        """Check health status of a service."""
        try:
            # This would integrate with actual health check endpoints
            # For now, return mock data
            return "healthy"
        except Exception as e:
            logger.error(f"Health check failed for {service_name}: {e}")
            return "unknown"

    def _check_active_deployments(self) -> bool:
        """Check if there are active deployments."""
        try:
            # This would check deployment systems
            # For now, return False
            return False
        except Exception as e:
            logger.error(f"Failed to check active deployments: {e}")
            return True

    def _simulate_rollback(self):
        """Simulate rollback execution for dry run."""
        logger.info("Simulating rollback execution...")
        
        print(f"\n{'='*60}")
        print(f"ROLLBACK PLAN SIMULATION: {self.train_name}")
        print(f"{'='*60}")
        print(f"Reason: {self.rollback_plan.reason}")
        print(f"Initiated by: {self.rollback_plan.initiated_by}")
        print(f"Estimated duration: {self.rollback_plan.estimated_duration}")
        print(f"Services to rollback: {len(self.rollback_plan.services)}")
        
        print(f"\nRollback Order:")
        for i, service_name in enumerate(self.rollback_plan.rollback_order, 1):
            service_info = next(s for s in self.rollback_plan.services if s.service_name == service_name)
            print(f"  {i}. {service_name}")
            print(f"     Current: {service_info.current_version}")
            print(f"     Target:  {service_info.previous_version}")
            print(f"     Method:  {service_info.rollback_method}")
            print(f"     Backup:  {'✓' if service_info.backup_available else '✗'}")
        
        print(f"\nSafety Checks:")
        for i, check in enumerate(self.rollback_plan.safety_checks, 1):
            print(f"  {i}. {check}")
        
        print(f"\n{'='*60}")

    def _execute_rollback_plan(self) -> bool:
        """Execute the rollback plan."""
        logger.info("Executing rollback plan...")
        
        try:
            # Update status
            self.rollback_plan.status = RollbackStatus.EXECUTING
            
            # Log rollback start
            audit_logger.log_action(
                user=self.rollback_plan.initiated_by,
                action="rollback_started",
                resource=self.train_name,
                details={
                    "reason": self.reason,
                    "services_count": len(self.rollback_plan.services),
                    "estimated_duration": str(self.rollback_plan.estimated_duration)
                }
            )
            
            # Execute rollback for each service
            success_count = 0
            for service_name in self.rollback_plan.rollback_order:
                service_info = next(s for s in self.rollback_plan.services if s.service_name == service_name)
                
                if self._rollback_single_service(service_info):
                    success_count += 1
                else:
                    logger.error(f"Failed to rollback service: {service_name}")
                    # Continue with other services
            
            # Verify rollback
            if success_count == len(self.rollback_plan.services):
                self.rollback_plan.status = RollbackStatus.VERIFYING
                if self._verify_rollback():
                    self.rollback_plan.status = RollbackStatus.COMPLETED
                    logger.info("Rollback completed successfully")
                    return True
                else:
                    self.rollback_plan.status = RollbackStatus.FAILED
                    logger.error("Rollback verification failed")
                    return False
            else:
                self.rollback_plan.status = RollbackStatus.FAILED
                logger.error(f"Rollback failed: {success_count}/{len(self.rollback_plan.services)} services rolled back")
                return False
            
        except Exception as e:
            logger.error(f"Rollback execution failed: {e}")
            self.rollback_plan.status = RollbackStatus.FAILED
            return False

    def _rollback_single_service(self, service_info: ServiceRollbackInfo) -> bool:
        """Rollback a single service."""
        logger.info(f"Rolling back service: {service_info.service_name}")
        
        try:
            # Update status
            service_info.status = ServiceRollbackStatus.IN_PROGRESS
            service_info.started_at = datetime.now()
            
            # Log service rollback start
            audit_logger.log_action(
                user=self.rollback_plan.initiated_by,
                action="service_rollback_started",
                resource=service_info.service_name,
                details={
                    "current_version": service_info.current_version,
                    "target_version": service_info.previous_version,
                    "method": service_info.rollback_method
                }
            )
            
            # Execute rollback based on method
            if service_info.rollback_method == "version_rollback":
                success = self._execute_version_rollback(service_info)
            elif service_info.rollback_method == "image_rollback":
                success = self._execute_image_rollback(service_info)
            elif service_info.rollback_method == "config_rollback":
                success = self._execute_config_rollback(service_info)
            else:
                logger.error(f"Unknown rollback method: {service_info.rollback_method}")
                success = False
            
            if success:
                service_info.status = ServiceRollbackStatus.ROLLED_BACK
                service_info.completed_at = datetime.now()
                
                # Log successful rollback
                audit_logger.log_action(
                    user=self.rollback_plan.initiated_by,
                    action="service_rollback_completed",
                    resource=service_info.service_name,
                    details={
                        "previous_version": service_info.previous_version,
                        "duration": str(service_info.completed_at - service_info.started_at)
                    }
                )
                
                logger.info(f"Successfully rolled back service: {service_info.service_name}")
            else:
                service_info.status = ServiceRollbackStatus.FAILED
                service_info.error_message = "Rollback execution failed"
                
                # Log failed rollback
                audit_logger.log_action(
                    user=self.rollback_plan.initiated_by,
                    action="service_rollback_failed",
                    resource=service_info.service_name,
                    details={
                        "error": service_info.error_message,
                        "method": service_info.rollback_method
                    }
                )
                
                logger.error(f"Failed to rollback service: {service_info.service_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Service rollback failed: {service_info.service_name}: {e}")
            service_info.status = ServiceRollbackStatus.FAILED
            service_info.error_message = str(e)
            return False

    def _execute_version_rollback(self, service_info: ServiceRollbackInfo) -> bool:
        """Execute version-based rollback."""
        try:
            # This would integrate with actual deployment system
            # For now, simulate success
            logger.info(f"Executing version rollback: {service_info.service_name} {service_info.current_version} -> {service_info.previous_version}")
            return True
        except Exception as e:
            logger.error(f"Version rollback failed: {e}")
            return False

    def _execute_image_rollback(self, service_info: ServiceRollbackInfo) -> bool:
        """Execute image-based rollback."""
        try:
            # This would integrate with container registry
            # For now, simulate success
            logger.info(f"Executing image rollback: {service_info.service_name}")
            return True
        except Exception as e:
            logger.error(f"Image rollback failed: {e}")
            return False

    def _execute_config_rollback(self, service_info: ServiceRollbackInfo) -> bool:
        """Execute configuration-based rollback."""
        try:
            # This would integrate with configuration management
            # For now, simulate success
            logger.info(f"Executing config rollback: {service_info.service_name}")
            return True
        except Exception as e:
            logger.error(f"Config rollback failed: {e}")
            return False

    def _verify_rollback(self) -> bool:
        """Verify that rollback was successful."""
        logger.info("Verifying rollback...")
        
        try:
            # Check health of all services
            for service_info in self.rollback_plan.services:
                if service_info.status == ServiceRollbackStatus.ROLLED_BACK:
                    health_status = self._check_service_health(service_info.service_name)
                    if health_status != 'healthy':
                        logger.error(f"Service {service_info.service_name} is not healthy after rollback")
                        return False
            
            # Check version consistency
            for service_info in self.rollback_plan.services:
                if service_info.status == ServiceRollbackStatus.ROLLED_BACK:
                    current_version = self._get_service_current_version(service_info.service_name)
                    if current_version != service_info.previous_version:
                        logger.error(f"Version mismatch for {service_info.service_name}: expected {service_info.previous_version}, got {current_version}")
                        return False
            
            logger.info("Rollback verification passed")
            return True
            
        except Exception as e:
            logger.error(f"Rollback verification failed: {e}")
            return False

    def generate_rollback_report(self) -> Dict[str, Any]:
        """Generate comprehensive rollback report."""
        if not self.rollback_plan:
            return {"error": "No rollback plan available"}
        
        return {
            "metadata": {
                "train_name": self.rollback_plan.train_name,
                "reason": self.rollback_plan.reason,
                "initiated_by": self.rollback_plan.initiated_by,
                "initiated_at": self.rollback_plan.initiated_at.isoformat(),
                "status": self.rollback_plan.status.value,
                "estimated_duration": str(self.rollback_plan.estimated_duration) if self.rollback_plan.estimated_duration else None
            },
            "services": [
                {
                    "service_name": s.service_name,
                    "current_version": s.current_version,
                    "previous_version": s.previous_version,
                    "status": s.status.value,
                    "rollback_method": s.rollback_method,
                    "backup_available": s.backup_available,
                    "error_message": s.error_message,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None
                }
                for s in self.rollback_plan.services
            ],
            "rollback_order": self.rollback_plan.rollback_order,
            "safety_checks": self.rollback_plan.safety_checks,
            "summary": {
                "total_services": len(self.rollback_plan.services),
                "successful_rollbacks": sum(1 for s in self.rollback_plan.services if s.status == ServiceRollbackStatus.ROLLED_BACK),
                "failed_rollbacks": sum(1 for s in self.rollback_plan.services if s.status == ServiceRollbackStatus.FAILED),
                "overall_success": self.rollback_plan.status == RollbackStatus.COMPLETED
            }
        }

    def save_rollback_report(self, report: Dict[str, Any], output_file: str = None) -> str:
        """Save rollback report to file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"analysis/reports/rollback_report_{self.train_name}_{timestamp}.json"
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Rollback report saved: {output_path}")
        return str(output_path)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Rollback release train")
    parser.add_argument("--train-name", type=str, required=True, help="Name of the release train to rollback")
    parser.add_argument("--reason", type=str, help="Reason for rollback")
    parser.add_argument("--dry-run", action="store_true", help="Simulate rollback without executing")
    parser.add_argument("--report", action="store_true", help="Generate detailed rollback report")
    parser.add_argument("--output-file", type=str, help="Output file for rollback report")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        rollback = ReleaseTrainRollback(
            train_name=args.train_name,
            reason=args.reason,
            dry_run=args.dry_run
        )
        
        # Execute rollback
        success = rollback.execute_rollback()
        
        # Generate report
        report = rollback.generate_rollback_report()
        
        if args.report or args.output_file:
            output_file = rollback.save_rollback_report(report, args.output_file)
            print(f"Rollback report saved: {output_file}")
        
        # Print summary
        summary = report["summary"]
        print(f"\nRollback Summary:")
        print(f"  Train: {args.train_name}")
        print(f"  Status: {report['metadata']['status']}")
        print(f"  Services: {summary['total_services']}")
        print(f"  Successful: {summary['successful_rollbacks']}")
        print(f"  Failed: {summary['failed_rollbacks']}")
        print(f"  Overall Success: {'✓' if summary['overall_success'] else '✗'}")
        
        if success:
            print("\n✅ Rollback completed successfully")
            sys.exit(0)
        else:
            print("\n❌ Rollback failed")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
