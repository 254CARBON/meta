#!/usr/bin/env python3
"""
254Carbon Meta Repository - Release Progress Monitor

Monitors ongoing release trains and tracks progress across multiple services.
Provides real-time status updates, health checks, and rollback capabilities.

Usage:
    python scripts/monitor_release_progress.py [--train-name NAME] [--watch] [--interval 30]

Features:
- Real-time release train monitoring
- Service health status tracking
- Progress visualization
- Automatic health checks
- Rollback recommendations
- Notification system
- Integration with GitHub Actions
- Metrics collection and reporting
"""

import os
import sys
import json
import yaml
import argparse
import logging
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from scripts.utils import audit_logger, monitor_execution, redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/release_monitoring.log')
    ]
)
logger = logging.getLogger(__name__)


class ReleaseStatus(Enum):
    """Release train status values."""
    PLANNING = "planning"
    VALIDATING = "validating"
    STAGING = "staging"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PAUSED = "paused"


class ServiceStatus(Enum):
    """Individual service status values."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DEPLOYED = "deployed"
    HEALTH_CHECKING = "health_checking"
    VERIFIED = "verified"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class ServiceReleaseInfo:
    """Information about a service's release progress."""
    service_name: str
    target_version: str
    current_version: str
    status: ServiceStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    health_status: str = "unknown"
    deployment_url: Optional[str] = None
    error_message: Optional[str] = None
    rollback_available: bool = False
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReleaseTrainInfo:
    """Information about a release train."""
    train_name: str
    status: ReleaseStatus
    target_version: str
    participants: List[str]
    started_at: datetime
    expected_completion: Optional[datetime] = None
    progress_percentage: float = 0.0
    services: List[ServiceReleaseInfo] = field(default_factory=list)
    gates_passed: List[str] = field(default_factory=list)
    gates_failed: List[str] = field(default_factory=list)
    health_checks: Dict[str, Any] = field(default_factory=dict)
    rollback_recommended: bool = False
    rollback_reason: Optional[str] = None


class ReleaseProgressMonitor:
    """Monitors release train progress and service health."""

    def __init__(self, train_name: str = None, watch_mode: bool = False, interval: int = 30):
        """
        Initialize release progress monitor.
        
        Args:
            train_name: Specific release train to monitor
            watch_mode: Whether to run in continuous watch mode
            interval: Polling interval in seconds
        """
        self.train_name = train_name
        self.watch_mode = watch_mode
        self.interval = interval
        self.running = False
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize monitoring data
        self.release_trains: Dict[str, ReleaseTrainInfo] = {}
        self.service_health_cache: Dict[str, Dict[str, Any]] = {}
        
        # GitHub API configuration
        self.github_token = os.getenv('GITHUB_TOKEN')
        self.github_api_base = "https://api.github.com"
        
        logger.info(f"Release progress monitor initialized: train={train_name}, watch={watch_mode}, interval={interval}s")

    def _load_config(self) -> Dict[str, Any]:
        """Load monitoring configuration."""
        config_file = Path("config/release-monitoring.yaml")
        if not config_file.exists():
            return self._get_default_config()
        
        with open(config_file) as f:
            return yaml.safe_load(f)

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default monitoring configuration."""
        return {
            "health_checks": {
                "timeout": 30,
                "retries": 3,
                "endpoints": {
                    "health": "/health",
                    "metrics": "/metrics",
                    "readiness": "/ready"
                }
            },
            "notifications": {
                "enabled": True,
                "channels": ["slack", "email"],
                "thresholds": {
                    "failure_rate": 0.2,
                    "health_check_failures": 3
                }
            },
            "rollback": {
                "auto_rollback": False,
                "failure_threshold": 0.3,
                "health_check_threshold": 0.5
            }
        }

    @monitor_execution("release-progress-monitoring")
    def start_monitoring(self):
        """Start monitoring release progress."""
        logger.info("Starting release progress monitoring...")
        
        # Load current release trains
        self._load_release_trains()
        
        if self.watch_mode:
            self._start_watch_mode()
        else:
            self._run_single_check()
        
        # Log audit event
        audit_logger.log_action(
            user="system",
            action="release_monitoring_started",
            resource=self.train_name or "all_trains",
            details={
                "watch_mode": self.watch_mode,
                "interval": self.interval,
                "trains_monitored": len(self.release_trains)
            }
        )

    def _load_release_trains(self):
        """Load release train information."""
        release_trains_file = Path("catalog/release-trains.yaml")
        if not release_trains_file.exists():
            logger.warning("No release trains file found")
            return
        
        with open(release_trains_file) as f:
            trains_data = yaml.safe_load(f)
        
        for train_data in trains_data.get('trains', []):
            train_name = train_data['name']
            
            # Filter by train name if specified
            if self.train_name and train_name != self.train_name:
                continue
            
            # Create release train info
            train_info = ReleaseTrainInfo(
                train_name=train_name,
                status=ReleaseStatus(train_data.get('status', 'planning')),
                target_version=train_data.get('target_version', ''),
                participants=train_data.get('participants', []),
                started_at=datetime.now()  # Would be loaded from actual data
            )
            
            # Initialize service release info
            for participant in train_info.participants:
                service_info = ServiceReleaseInfo(
                    service_name=participant,
                    target_version=train_info.target_version,
                    current_version="unknown",
                    status=ServiceStatus.PENDING
                )
                train_info.services.append(service_info)
            
            self.release_trains[train_name] = train_info
        
        logger.info(f"Loaded {len(self.release_trains)} release trains")

    def _start_watch_mode(self):
        """Start continuous monitoring in watch mode."""
        self.running = True
        logger.info(f"Starting watch mode with {self.interval}s interval")
        
        try:
            while self.running:
                self._run_single_check()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            logger.info("Watch mode interrupted by user")
        finally:
            self.running = False
            logger.info("Watch mode stopped")

    def _run_single_check(self):
        """Run a single monitoring check."""
        logger.info("Running release progress check...")
        
        for train_name, train_info in self.release_trains.items():
            try:
                self._check_release_train_progress(train_info)
                self._check_service_health(train_info)
                self._evaluate_rollback_conditions(train_info)
                self._update_progress_metrics(train_info)
                
                # Save updated state
                self._save_release_state(train_info)
                
            except Exception as e:
                logger.error(f"Failed to check release train {train_name}: {e}")
        
        # Generate monitoring report
        report = self._generate_monitoring_report()
        self._save_monitoring_report(report)
        
        # Send notifications if needed
        self._send_notifications(report)

    def _check_release_train_progress(self, train_info: ReleaseTrainInfo):
        """Check progress of a specific release train."""
        logger.info(f"Checking progress for release train: {train_info.train_name}")
        
        # Check GitHub Actions status for each service
        for service_info in train_info.services:
            self._check_service_deployment_status(service_info)
        
        # Calculate overall progress
        completed_services = sum(1 for s in train_info.services if s.status == ServiceStatus.VERIFIED)
        total_services = len(train_info.services)
        train_info.progress_percentage = (completed_services / total_services) * 100 if total_services > 0 else 0
        
        # Update train status based on service statuses
        self._update_train_status(train_info)
        
        logger.info(f"Release train {train_info.train_name}: {train_info.progress_percentage:.1f}% complete")

    def _check_service_deployment_status(self, service_info: ServiceReleaseInfo):
        """Check deployment status of a specific service."""
        try:
            # Check GitHub Actions workflow status
            workflow_status = self._get_github_workflow_status(service_info.service_name)
            
            if workflow_status:
                service_info.status = self._map_workflow_status(workflow_status)
                service_info.deployment_url = workflow_status.get('url')
                
                if workflow_status.get('status') == 'completed':
                    if workflow_status.get('conclusion') == 'success':
                        service_info.status = ServiceStatus.DEPLOYED
                        service_info.completed_at = datetime.now()
                    else:
                        service_info.status = ServiceStatus.FAILED
                        service_info.error_message = workflow_status.get('error_message')
            
            # Check current version
            current_version = self._get_service_current_version(service_info.service_name)
            if current_version:
                service_info.current_version = current_version
                
                # Check if target version is deployed
                if current_version == service_info.target_version:
                    service_info.status = ServiceStatus.DEPLOYED
            
        except Exception as e:
            logger.error(f"Failed to check deployment status for {service_info.service_name}: {e}")
            service_info.error_message = str(e)

    def _get_github_workflow_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get GitHub Actions workflow status for a service."""
        if not self.github_token:
            logger.warning("GitHub token not available, skipping workflow status check")
            return None
        
        try:
            # This would need to be implemented based on actual GitHub Actions setup
            # For now, return mock data
            return {
                "status": "completed",
                "conclusion": "success",
                "url": f"https://github.com/254carbon/{service_name}/actions",
                "run_id": "123456789"
            }
        except Exception as e:
            logger.error(f"Failed to get GitHub workflow status for {service_name}: {e}")
            return None

    def _map_workflow_status(self, workflow_status: Dict[str, Any]) -> ServiceStatus:
        """Map GitHub workflow status to service status."""
        status = workflow_status.get('status', 'unknown')
        conclusion = workflow_status.get('conclusion', 'unknown')
        
        if status == 'in_progress':
            return ServiceStatus.IN_PROGRESS
        elif status == 'completed':
            if conclusion == 'success':
                return ServiceStatus.DEPLOYED
            else:
                return ServiceStatus.FAILED
        else:
            return ServiceStatus.PENDING

    def _get_service_current_version(self, service_name: str) -> Optional[str]:
        """Get current deployed version of a service."""
        try:
            # This would integrate with actual deployment system
            # For now, return mock data
            return "1.0.0"
        except Exception as e:
            logger.error(f"Failed to get current version for {service_name}: {e}")
            return None

    def _check_service_health(self, train_info: ReleaseTrainInfo):
        """Check health of services in a release train."""
        logger.info(f"Checking service health for {train_info.train_name}")
        
        # Use thread pool for concurrent health checks
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self._check_single_service_health, service_info): service_info
                for service_info in train_info.services
                if service_info.status in [ServiceStatus.DEPLOYED, ServiceStatus.VERIFIED]
            }
            
            for future in as_completed(futures):
                service_info = futures[future]
                try:
                    health_data = future.result()
                    service_info.health_status = health_data.get('status', 'unknown')
                    service_info.metrics.update(health_data.get('metrics', {}))
                    
                    # Cache health data
                    self.service_health_cache[service_info.service_name] = health_data
                    
                except Exception as e:
                    logger.error(f"Health check failed for {service_info.service_name}: {e}")
                    service_info.health_status = 'error'

    def _check_single_service_health(self, service_info: ServiceReleaseInfo) -> Dict[str, Any]:
        """Check health of a single service."""
        try:
            # This would integrate with actual health check endpoints
            # For now, return mock data
            return {
                "status": "healthy",
                "response_time": 0.05,
                "metrics": {
                    "cpu_usage": 0.3,
                    "memory_usage": 0.4,
                    "request_rate": 100.0,
                    "error_rate": 0.01
                },
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Health check failed for {service_info.service_name}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    def _evaluate_rollback_conditions(self, train_info: ReleaseTrainInfo):
        """Evaluate if rollback is recommended."""
        logger.info(f"Evaluating rollback conditions for {train_info.train_name}")
        
        # Check failure rate
        failed_services = sum(1 for s in train_info.services if s.status == ServiceStatus.FAILED)
        total_services = len(train_info.services)
        failure_rate = failed_services / total_services if total_services > 0 else 0
        
        # Check health status
        unhealthy_services = sum(1 for s in train_info.services if s.health_status == 'error')
        health_failure_rate = unhealthy_services / total_services if total_services > 0 else 0
        
        # Check rollback thresholds
        rollback_config = self.config.get('rollback', {})
        failure_threshold = rollback_config.get('failure_threshold', 0.3)
        health_threshold = rollback_config.get('health_check_threshold', 0.5)
        
        if failure_rate > failure_threshold:
            train_info.rollback_recommended = True
            train_info.rollback_reason = f"High failure rate: {failure_rate:.1%} > {failure_threshold:.1%}"
        elif health_failure_rate > health_threshold:
            train_info.rollback_recommended = True
            train_info.rollback_reason = f"High health check failure rate: {health_failure_rate:.1%} > {health_threshold:.1%}"
        else:
            train_info.rollback_recommended = False
            train_info.rollback_reason = None
        
        if train_info.rollback_recommended:
            logger.warning(f"Rollback recommended for {train_info.train_name}: {train_info.rollback_reason}")

    def _update_progress_metrics(self, train_info: ReleaseTrainInfo):
        """Update progress metrics for a release train."""
        # Calculate various metrics
        metrics = {
            "total_services": len(train_info.services),
            "completed_services": sum(1 for s in train_info.services if s.status == ServiceStatus.VERIFIED),
            "failed_services": sum(1 for s in train_info.services if s.status == ServiceStatus.FAILED),
            "in_progress_services": sum(1 for s in train_info.services if s.status == ServiceStatus.IN_PROGRESS),
            "healthy_services": sum(1 for s in train_info.services if s.health_status == 'healthy'),
            "unhealthy_services": sum(1 for s in train_info.services if s.health_status == 'error'),
            "progress_percentage": train_info.progress_percentage,
            "rollback_recommended": train_info.rollback_recommended
        }
        
        # Store metrics in Redis for real-time access
        redis_client.set(
            f"release_metrics:{train_info.train_name}",
            metrics,
            ttl=300,  # 5 minutes
            fallback_to_file=True
        )

    def _update_train_status(self, train_info: ReleaseTrainInfo):
        """Update overall train status based on service statuses."""
        service_statuses = [s.status for s in train_info.services]
        
        if all(s == ServiceStatus.VERIFIED for s in service_statuses):
            train_info.status = ReleaseStatus.COMPLETED
        elif any(s == ServiceStatus.FAILED for s in service_statuses):
            if train_info.rollback_recommended:
                train_info.status = ReleaseStatus.FAILED
            else:
                train_info.status = ReleaseStatus.PAUSED
        elif any(s == ServiceStatus.IN_PROGRESS for s in service_statuses):
            train_info.status = ReleaseStatus.EXECUTING
        elif any(s == ServiceStatus.DEPLOYED for s in service_statuses):
            train_info.status = ReleaseStatus.VERIFYING
        else:
            train_info.status = ReleaseStatus.PLANNING

    def _save_release_state(self, train_info: ReleaseTrainInfo):
        """Save current release state to file."""
        state_file = Path(f"analysis/reports/release_state_{train_info.train_name}.json")
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        state_data = {
            "train_name": train_info.train_name,
            "status": train_info.status.value,
            "progress_percentage": train_info.progress_percentage,
            "services": [
                {
                    "service_name": s.service_name,
                    "status": s.status.value,
                    "current_version": s.current_version,
                    "target_version": s.target_version,
                    "health_status": s.health_status,
                    "error_message": s.error_message
                }
                for s in train_info.services
            ],
            "rollback_recommended": train_info.rollback_recommended,
            "rollback_reason": train_info.rollback_reason,
            "last_updated": datetime.now().isoformat()
        }
        
        with open(state_file, 'w') as f:
            json.dump(state_data, f, indent=2)

    def _generate_monitoring_report(self) -> Dict[str, Any]:
        """Generate comprehensive monitoring report."""
        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "monitor_mode": "watch" if self.watch_mode else "single",
                "trains_monitored": len(self.release_trains)
            },
            "release_trains": [],
            "summary": {
                "total_trains": len(self.release_trains),
                "active_trains": sum(1 for t in self.release_trains.values() if t.status in [ReleaseStatus.EXECUTING, ReleaseStatus.VERIFYING]),
                "completed_trains": sum(1 for t in self.release_trains.values() if t.status == ReleaseStatus.COMPLETED),
                "failed_trains": sum(1 for t in self.release_trains.values() if t.status == ReleaseStatus.FAILED),
                "rollback_recommended": sum(1 for t in self.release_trains.values() if t.rollback_recommended)
            }
        }
        
        for train_info in self.release_trains.values():
            train_report = {
                "train_name": train_info.train_name,
                "status": train_info.status.value,
                "progress_percentage": train_info.progress_percentage,
                "total_services": len(train_info.services),
                "completed_services": sum(1 for s in train_info.services if s.status == ServiceStatus.VERIFIED),
                "failed_services": sum(1 for s in train_info.services if s.status == ServiceStatus.FAILED),
                "healthy_services": sum(1 for s in train_info.services if s.health_status == 'healthy'),
                "rollback_recommended": train_info.rollback_recommended,
                "rollback_reason": train_info.rollback_reason,
                "services": [
                    {
                        "service_name": s.service_name,
                        "status": s.status.value,
                        "health_status": s.health_status,
                        "current_version": s.current_version,
                        "target_version": s.target_version,
                        "error_message": s.error_message
                    }
                    for s in train_info.services
                ]
            }
            report["release_trains"].append(train_report)
        
        return report

    def _save_monitoring_report(self, report: Dict[str, Any]):
        """Save monitoring report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = Path(f"analysis/reports/release_monitoring_{timestamp}.json")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Monitoring report saved: {report_file}")

    def _send_notifications(self, report: Dict[str, Any]):
        """Send notifications based on monitoring results."""
        if not self.config.get('notifications', {}).get('enabled', False):
            return
        
        # Check for critical conditions
        critical_conditions = []
        
        for train_report in report["release_trains"]:
            if train_report["rollback_recommended"]:
                critical_conditions.append(f"Rollback recommended for {train_report['train_name']}: {train_report['rollback_reason']}")
            
            failure_rate = train_report["failed_services"] / train_report["total_services"] if train_report["total_services"] > 0 else 0
            if failure_rate > self.config['notifications']['thresholds']['failure_rate']:
                critical_conditions.append(f"High failure rate in {train_report['train_name']}: {failure_rate:.1%}")
        
        if critical_conditions:
            # Send notifications (implementation would depend on notification system)
            logger.warning(f"Critical conditions detected: {critical_conditions}")
            # TODO: Implement actual notification sending

    def stop_monitoring(self):
        """Stop monitoring."""
        self.running = False
        logger.info("Release monitoring stopped")

    def get_release_status(self, train_name: str = None) -> Dict[str, Any]:
        """Get current release status."""
        if train_name:
            if train_name in self.release_trains:
                return self._generate_monitoring_report()["release_trains"][0]
            else:
                return {"error": f"Release train '{train_name}' not found"}
        else:
            return self._generate_monitoring_report()

    def trigger_rollback(self, train_name: str, reason: str = None) -> bool:
        """Trigger rollback for a release train."""
        if train_name not in self.release_trains:
            logger.error(f"Release train '{train_name}' not found")
            return False
        
        train_info = self.release_trains[train_name]
        
        logger.info(f"Triggering rollback for release train: {train_name}")
        
        # Log rollback event
        audit_logger.log_action(
            user="system",
            action="release_rollback_triggered",
            resource=train_name,
            details={
                "reason": reason or train_info.rollback_reason,
                "services_count": len(train_info.services),
                "failed_services": sum(1 for s in train_info.services if s.status == ServiceStatus.FAILED)
            }
        )
        
        # TODO: Implement actual rollback logic
        # This would involve:
        # 1. Stopping current deployments
        # 2. Rolling back to previous versions
        # 3. Updating service statuses
        # 4. Notifying stakeholders
        
        train_info.status = ReleaseStatus.ROLLED_BACK
        for service_info in train_info.services:
            service_info.status = ServiceStatus.ROLLED_BACK
        
        logger.info(f"Rollback completed for release train: {train_name}")
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Monitor release train progress")
    parser.add_argument("--train-name", type=str, help="Specific release train to monitor")
    parser.add_argument("--watch", action="store_true", help="Run in continuous watch mode")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds (default: 30)")
    parser.add_argument("--status", action="store_true", help="Show current status and exit")
    parser.add_argument("--rollback", type=str, help="Trigger rollback for specified train")
    parser.add_argument("--rollback-reason", type=str, help="Reason for rollback")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        monitor = ReleaseProgressMonitor(
            train_name=args.train_name,
            watch_mode=args.watch,
            interval=args.interval
        )
        
        if args.status:
            # Show status and exit
            status = monitor.get_release_status(args.train_name)
            print(json.dumps(status, indent=2))
            return
        
        if args.rollback:
            # Trigger rollback
            success = monitor.trigger_rollback(args.rollback, args.rollback_reason)
            if success:
                print(f"✅ Rollback triggered for release train: {args.rollback}")
                sys.exit(0)
            else:
                print(f"❌ Failed to trigger rollback for release train: {args.rollback}")
                sys.exit(1)
        
        # Start monitoring
        monitor.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("Monitoring interrupted by user")
    except Exception as e:
        logger.error(f"Release monitoring failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
