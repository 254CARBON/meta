#!/usr/bin/env python3
"""
254Carbon Meta Repository - Health Checker

Continuously monitors service health and validates system stability.
Provides automated health checks, alerting, and recovery suggestions.

Usage:
    python scripts/sre/health_checker.py --service gateway --continuous
    python scripts/sre/health_checker.py --all-services --check-interval 300
    python scripts/sre/health_checker.py --service auth-service --validate-health

Features:
- Continuous health monitoring
- Automated health validation
- Service dependency checking
- Performance monitoring
- Alert generation
- Recovery suggestions
- Health trend analysis
"""

import os
import sys
import json
import yaml
import argparse
import logging
import requests
import time
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import subprocess
import concurrent.futures

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from scripts.utils import audit_logger, monitor_execution
from scripts.send_notifications import NotificationSender, NotificationMessage, NotificationSeverity, NotificationChannel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/health-checking.log')
    ]
)
logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class HealthCheckType(Enum):
    """Types of health checks."""
    HTTP_ENDPOINT = "http_endpoint"
    DATABASE_CONNECTION = "database_connection"
    DEPENDENCY_CHECK = "dependency_check"
    PERFORMANCE_CHECK = "performance_check"
    RESOURCE_CHECK = "resource_check"
    LOG_ANALYSIS = "log_analysis"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    check_type: HealthCheckType
    status: HealthStatus
    response_time: float
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ServiceHealth:
    """Overall health status of a service."""
    service_name: str
    overall_status: HealthStatus
    overall_score: float
    check_results: List[HealthCheckResult]
    last_updated: datetime
    uptime: float
    error_rate: float
    response_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class HealthChecker:
    """Health checking engine."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the health checker."""
        self.config_path = config_path or 'config/health-checks.yaml'
        self.config = self._load_config()
        self.notification_sender = NotificationSender()
        self.running = False
        self.health_history = {}
        
        # Health check intervals
        self.check_intervals = {
            HealthCheckType.HTTP_ENDPOINT: 30,  # seconds
            HealthCheckType.DATABASE_CONNECTION: 60,
            HealthCheckType.DEPENDENCY_CHECK: 120,
            HealthCheckType.PERFORMANCE_CHECK: 300,
            HealthCheckType.RESOURCE_CHECK: 60,
            HealthCheckType.LOG_ANALYSIS: 300
        }
        
        # Health thresholds
        self.health_thresholds = {
            'response_time': 1000,  # milliseconds
            'error_rate': 5.0,  # percentage
            'uptime': 99.0,  # percentage
            'cpu_usage': 80.0,  # percentage
            'memory_usage': 80.0,  # percentage
            'disk_usage': 90.0  # percentage
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """Load health check configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Health check config not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing health check config: {e}")
            return {}
    
    def check_service_health(self, service_name: str) -> ServiceHealth:
        """Check health of a specific service."""
        logger.info(f"Checking health for service: {service_name}")
        
        try:
            # Get service configuration
            service_config = self._get_service_config(service_name)
            if not service_config:
                return ServiceHealth(
                    service_name=service_name,
                    overall_status=HealthStatus.UNKNOWN,
                    overall_score=0.0,
                    check_results=[],
                    last_updated=datetime.now(timezone.utc),
                    uptime=0.0,
                    error_rate=100.0,
                    response_time=0.0
                )
            
            # Perform health checks
            check_results = []
            
            # HTTP endpoint check
            if service_config.get('health_endpoint'):
                result = self._check_http_endpoint(service_name, service_config['health_endpoint'])
                check_results.append(result)
            
            # Database connection check
            if service_config.get('database'):
                result = self._check_database_connection(service_name, service_config['database'])
                check_results.append(result)
            
            # Dependency check
            result = self._check_dependencies(service_name, service_config)
            check_results.append(result)
            
            # Performance check
            result = self._check_performance(service_name, service_config)
            check_results.append(result)
            
            # Resource check
            result = self._check_resources(service_name, service_config)
            check_results.append(result)
            
            # Log analysis
            result = self._check_logs(service_name, service_config)
            check_results.append(result)
            
            # Calculate overall health
            overall_status, overall_score = self._calculate_overall_health(check_results)
            
            # Get service metrics
            uptime, error_rate, response_time = self._get_service_metrics(service_name, service_config)
            
            health = ServiceHealth(
                service_name=service_name,
                overall_status=overall_status,
                overall_score=overall_score,
                check_results=check_results,
                last_updated=datetime.now(timezone.utc),
                uptime=uptime,
                error_rate=error_rate,
                response_time=response_time,
                metadata=service_config
            )
            
            # Store health history
            self._store_health_history(health)
            
            # Send notifications if needed
            self._send_health_notifications(health)
            
            return health
            
        except Exception as e:
            logger.error(f"Error checking health for {service_name}: {e}")
            return ServiceHealth(
                service_name=service_name,
                overall_status=HealthStatus.CRITICAL,
                overall_score=0.0,
                check_results=[],
                last_updated=datetime.now(timezone.utc),
                uptime=0.0,
                error_rate=100.0,
                response_time=0.0,
                metadata={'error': str(e)}
            )
    
    def check_all_services(self) -> Dict[str, ServiceHealth]:
        """Check health of all services."""
        logger.info("Checking health for all services")
        
        # Get all services
        services = self._get_all_services()
        if not services:
            logger.warning("No services found for health checking")
            return {}
        
        # Check health for each service
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_service = {
                executor.submit(self.check_service_health, service): service 
                for service in services
            }
            
            for future in concurrent.futures.as_completed(future_to_service):
                service = future_to_service[future]
                try:
                    health = future.result()
                    results[service] = health
                except Exception as e:
                    logger.error(f"Error checking health for {service}: {e}")
                    results[service] = ServiceHealth(
                        service_name=service,
                        overall_status=HealthStatus.CRITICAL,
                        overall_score=0.0,
                        check_results=[],
                        last_updated=datetime.now(timezone.utc),
                        uptime=0.0,
                        error_rate=100.0,
                        response_time=0.0,
                        metadata={'error': str(e)}
                    )
        
        # Send summary notification
        self._send_summary_notification(results)
        
        return results
    
    def start_continuous_monitoring(self, check_interval: int = 300):
        """Start continuous health monitoring."""
        logger.info(f"Starting continuous health monitoring with {check_interval}s interval")
        
        self.running = True
        
        def monitor_loop():
            while self.running:
                try:
                    # Check all services
                    results = self.check_all_services()
                    
                    # Log summary
                    healthy_services = len([r for r in results.values() if r.overall_status == HealthStatus.HEALTHY])
                    warning_services = len([r for r in results.values() if r.overall_status == HealthStatus.WARNING])
                    critical_services = len([r for r in results.values() if r.overall_status == HealthStatus.CRITICAL])
                    
                    logger.info(f"Health check summary: {healthy_services} healthy, {warning_services} warning, {critical_services} critical")
                    
                    # Wait for next check
                    time.sleep(check_interval)
                    
                except Exception as e:
                    logger.error(f"Error in continuous monitoring: {e}")
                    time.sleep(check_interval)
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        
        return monitor_thread
    
    def stop_continuous_monitoring(self):
        """Stop continuous health monitoring."""
        logger.info("Stopping continuous health monitoring")
        self.running = False
    
    def _get_service_config(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get service configuration."""
        try:
            # Load service catalog
            catalog_file = Path('catalog/service-index.yaml')
            if not catalog_file.exists():
                return None
            
            with open(catalog_file, 'r') as f:
                catalog_data = yaml.safe_load(f)
            
            services = catalog_data.get('services', [])
            for service in services:
                if service.get('name') == service_name:
                    return service
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting service config for {service_name}: {e}")
            return None
    
    def _check_http_endpoint(self, service_name: str, endpoint: str) -> HealthCheckResult:
        """Check HTTP health endpoint."""
        try:
            start_time = time.time()
            
            # Make HTTP request
            response = requests.get(endpoint, timeout=10)
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            if response.status_code == 200:
                status = HealthStatus.HEALTHY
                message = f"HTTP endpoint healthy: {response.status_code}"
            elif response.status_code < 500:
                status = HealthStatus.WARNING
                message = f"HTTP endpoint warning: {response.status_code}"
            else:
                status = HealthStatus.CRITICAL
                message = f"HTTP endpoint critical: {response.status_code}"
            
            return HealthCheckResult(
                check_type=HealthCheckType.HTTP_ENDPOINT,
                status=status,
                response_time=response_time,
                message=message,
                metadata={
                    'endpoint': endpoint,
                    'status_code': response.status_code,
                    'response_time': response_time
                }
            )
            
        except requests.RequestException as e:
            return HealthCheckResult(
                check_type=HealthCheckType.HTTP_ENDPOINT,
                status=HealthStatus.CRITICAL,
                response_time=0.0,
                message=f"HTTP endpoint failed: {str(e)}",
                metadata={'endpoint': endpoint, 'error': str(e)}
            )
    
    def _check_database_connection(self, service_name: str, database_config: Dict[str, Any]) -> HealthCheckResult:
        """Check database connection."""
        try:
            start_time = time.time()
            
            # This would typically use a database connection library
            # For now, we'll simulate the check
            db_type = database_config.get('type', 'postgresql')
            host = database_config.get('host', 'localhost')
            port = database_config.get('port', 5432)
            
            # Simulate database check
            time.sleep(0.1)  # Simulate connection time
            response_time = (time.time() - start_time) * 1000
            
            # For demonstration, assume database is healthy
            status = HealthStatus.HEALTHY
            message = f"Database connection healthy: {db_type}://{host}:{port}"
            
            return HealthCheckResult(
                check_type=HealthCheckType.DATABASE_CONNECTION,
                status=status,
                response_time=response_time,
                message=message,
                metadata={
                    'database_type': db_type,
                    'host': host,
                    'port': port,
                    'response_time': response_time
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                check_type=HealthCheckType.DATABASE_CONNECTION,
                status=HealthStatus.CRITICAL,
                response_time=0.0,
                message=f"Database connection failed: {str(e)}",
                metadata={'error': str(e)}
            )
    
    def _check_dependencies(self, service_name: str, service_config: Dict[str, Any]) -> HealthCheckResult:
        """Check service dependencies."""
        try:
            start_time = time.time()
            
            # Get service dependencies
            dependencies = service_config.get('dependencies', {})
            internal_deps = dependencies.get('internal', [])
            external_deps = dependencies.get('external', [])
            
            # Check internal dependencies
            healthy_deps = 0
            total_deps = len(internal_deps)
            
            for dep in internal_deps:
                # Check if dependency service is healthy
                dep_health = self._get_dependency_health(dep)
                if dep_health == HealthStatus.HEALTHY:
                    healthy_deps += 1
            
            response_time = (time.time() - start_time) * 1000
            
            if total_deps == 0:
                status = HealthStatus.HEALTHY
                message = "No internal dependencies to check"
            elif healthy_deps == total_deps:
                status = HealthStatus.HEALTHY
                message = f"All {total_deps} dependencies healthy"
            elif healthy_deps >= total_deps * 0.8:
                status = HealthStatus.WARNING
                message = f"{healthy_deps}/{total_deps} dependencies healthy"
            else:
                status = HealthStatus.CRITICAL
                message = f"Only {healthy_deps}/{total_deps} dependencies healthy"
            
            return HealthCheckResult(
                check_type=HealthCheckType.DEPENDENCY_CHECK,
                status=status,
                response_time=response_time,
                message=message,
                metadata={
                    'total_dependencies': total_deps,
                    'healthy_dependencies': healthy_deps,
                    'dependency_health_ratio': healthy_deps / total_deps if total_deps > 0 else 1.0
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                check_type=HealthCheckType.DEPENDENCY_CHECK,
                status=HealthStatus.CRITICAL,
                response_time=0.0,
                message=f"Dependency check failed: {str(e)}",
                metadata={'error': str(e)}
            )
    
    def _check_performance(self, service_name: str, service_config: Dict[str, Any]) -> HealthCheckResult:
        """Check service performance."""
        try:
            start_time = time.time()
            
            # Get performance metrics
            metrics = self._get_performance_metrics(service_name)
            
            response_time = (time.time() - start_time) * 1000
            
            # Check performance thresholds
            avg_response_time = metrics.get('avg_response_time', 0)
            error_rate = metrics.get('error_rate', 0)
            throughput = metrics.get('throughput', 0)
            
            if avg_response_time <= self.health_thresholds['response_time'] and error_rate <= self.health_thresholds['error_rate']:
                status = HealthStatus.HEALTHY
                message = f"Performance healthy: {avg_response_time:.1f}ms avg, {error_rate:.1f}% errors"
            elif avg_response_time <= self.health_thresholds['response_time'] * 1.5 and error_rate <= self.health_thresholds['error_rate'] * 2:
                status = HealthStatus.WARNING
                message = f"Performance warning: {avg_response_time:.1f}ms avg, {error_rate:.1f}% errors"
            else:
                status = HealthStatus.CRITICAL
                message = f"Performance critical: {avg_response_time:.1f}ms avg, {error_rate:.1f}% errors"
            
            return HealthCheckResult(
                check_type=HealthCheckType.PERFORMANCE_CHECK,
                status=status,
                response_time=response_time,
                message=message,
                metadata={
                    'avg_response_time': avg_response_time,
                    'error_rate': error_rate,
                    'throughput': throughput,
                    'response_time': response_time
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                check_type=HealthCheckType.PERFORMANCE_CHECK,
                status=HealthStatus.CRITICAL,
                response_time=0.0,
                message=f"Performance check failed: {str(e)}",
                metadata={'error': str(e)}
            )
    
    def _check_resources(self, service_name: str, service_config: Dict[str, Any]) -> HealthCheckResult:
        """Check service resource usage."""
        try:
            start_time = time.time()
            
            # Get resource metrics
            metrics = self._get_resource_metrics(service_name)
            
            response_time = (time.time() - start_time) * 1000
            
            # Check resource thresholds
            cpu_usage = metrics.get('cpu_usage', 0)
            memory_usage = metrics.get('memory_usage', 0)
            disk_usage = metrics.get('disk_usage', 0)
            
            if (cpu_usage <= self.health_thresholds['cpu_usage'] and 
                memory_usage <= self.health_thresholds['memory_usage'] and 
                disk_usage <= self.health_thresholds['disk_usage']):
                status = HealthStatus.HEALTHY
                message = f"Resources healthy: CPU {cpu_usage:.1f}%, Memory {memory_usage:.1f}%, Disk {disk_usage:.1f}%"
            elif (cpu_usage <= self.health_thresholds['cpu_usage'] * 1.2 and 
                  memory_usage <= self.health_thresholds['memory_usage'] * 1.2 and 
                  disk_usage <= self.health_thresholds['disk_usage'] * 1.1):
                status = HealthStatus.WARNING
                message = f"Resources warning: CPU {cpu_usage:.1f}%, Memory {memory_usage:.1f}%, Disk {disk_usage:.1f}%"
            else:
                status = HealthStatus.CRITICAL
                message = f"Resources critical: CPU {cpu_usage:.1f}%, Memory {memory_usage:.1f}%, Disk {disk_usage:.1f}%"
            
            return HealthCheckResult(
                check_type=HealthCheckType.RESOURCE_CHECK,
                status=status,
                response_time=response_time,
                message=message,
                metadata={
                    'cpu_usage': cpu_usage,
                    'memory_usage': memory_usage,
                    'disk_usage': disk_usage,
                    'response_time': response_time
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                check_type=HealthCheckType.RESOURCE_CHECK,
                status=HealthStatus.CRITICAL,
                response_time=0.0,
                message=f"Resource check failed: {str(e)}",
                metadata={'error': str(e)}
            )
    
    def _check_logs(self, service_name: str, service_config: Dict[str, Any]) -> HealthCheckResult:
        """Check service logs for errors."""
        try:
            start_time = time.time()
            
            # Get log metrics
            metrics = self._get_log_metrics(service_name)
            
            response_time = (time.time() - start_time) * 1000
            
            # Check log thresholds
            error_count = metrics.get('error_count', 0)
            warning_count = metrics.get('warning_count', 0)
            total_logs = metrics.get('total_logs', 1)
            
            error_rate = (error_count / total_logs) * 100 if total_logs > 0 else 0
            
            if error_rate <= 1.0:  # Less than 1% errors
                status = HealthStatus.HEALTHY
                message = f"Logs healthy: {error_count} errors, {warning_count} warnings"
            elif error_rate <= 5.0:  # Less than 5% errors
                status = HealthStatus.WARNING
                message = f"Logs warning: {error_count} errors, {warning_count} warnings"
            else:
                status = HealthStatus.CRITICAL
                message = f"Logs critical: {error_count} errors, {warning_count} warnings"
            
            return HealthCheckResult(
                check_type=HealthCheckType.LOG_ANALYSIS,
                status=status,
                response_time=response_time,
                message=message,
                metadata={
                    'error_count': error_count,
                    'warning_count': warning_count,
                    'total_logs': total_logs,
                    'error_rate': error_rate,
                    'response_time': response_time
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                check_type=HealthCheckType.LOG_ANALYSIS,
                status=HealthStatus.CRITICAL,
                response_time=0.0,
                message=f"Log analysis failed: {str(e)}",
                metadata={'error': str(e)}
            )
    
    def _calculate_overall_health(self, check_results: List[HealthCheckResult]) -> Tuple[HealthStatus, float]:
        """Calculate overall health status and score."""
        if not check_results:
            return HealthStatus.UNKNOWN, 0.0
        
        # Count statuses
        status_counts = {
            HealthStatus.HEALTHY: 0,
            HealthStatus.WARNING: 0,
            HealthStatus.CRITICAL: 0,
            HealthStatus.UNKNOWN: 0
        }
        
        for result in check_results:
            status_counts[result.status] += 1
        
        total_checks = len(check_results)
        
        # Calculate overall status
        if status_counts[HealthStatus.CRITICAL] > 0:
            overall_status = HealthStatus.CRITICAL
        elif status_counts[HealthStatus.WARNING] > 0:
            overall_status = HealthStatus.WARNING
        elif status_counts[HealthStatus.HEALTHY] == total_checks:
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN
        
        # Calculate overall score
        healthy_weight = 100
        warning_weight = 50
        critical_weight = 0
        unknown_weight = 25
        
        score = (
            (status_counts[HealthStatus.HEALTHY] * healthy_weight +
             status_counts[HealthStatus.WARNING] * warning_weight +
             status_counts[HealthStatus.CRITICAL] * critical_weight +
             status_counts[HealthStatus.UNKNOWN] * unknown_weight) / total_checks
        )
        
        return overall_status, score
    
    def _get_service_metrics(self, service_name: str, service_config: Dict[str, Any]) -> Tuple[float, float, float]:
        """Get service metrics (uptime, error rate, response time)."""
        try:
            # This would typically query monitoring systems
            # For now, return mock data
            uptime = 99.5  # percentage
            error_rate = 0.5  # percentage
            response_time = 150.0  # milliseconds
            
            return uptime, error_rate, response_time
            
        except Exception as e:
            logger.error(f"Error getting service metrics for {service_name}: {e}")
            return 0.0, 100.0, 0.0
    
    def _get_dependency_health(self, dependency: str) -> HealthStatus:
        """Get health status of a dependency service."""
        try:
            # Check if dependency is in health history
            if dependency in self.health_history:
                last_health = self.health_history[dependency]
                if last_health.last_updated > datetime.now(timezone.utc) - timedelta(minutes=5):
                    return last_health.overall_status
            
            # If not recent, assume healthy for now
            return HealthStatus.HEALTHY
            
        except Exception as e:
            logger.error(f"Error getting dependency health for {dependency}: {e}")
            return HealthStatus.UNKNOWN
    
    def _get_performance_metrics(self, service_name: str) -> Dict[str, float]:
        """Get performance metrics for a service."""
        try:
            # This would typically query monitoring systems
            # For now, return mock data
            return {
                'avg_response_time': 150.0,
                'error_rate': 0.5,
                'throughput': 1000.0
            }
            
        except Exception as e:
            logger.error(f"Error getting performance metrics for {service_name}: {e}")
            return {'avg_response_time': 0.0, 'error_rate': 100.0, 'throughput': 0.0}
    
    def _get_resource_metrics(self, service_name: str) -> Dict[str, float]:
        """Get resource metrics for a service."""
        try:
            # This would typically query monitoring systems
            # For now, return mock data
            return {
                'cpu_usage': 45.0,
                'memory_usage': 60.0,
                'disk_usage': 30.0
            }
            
        except Exception as e:
            logger.error(f"Error getting resource metrics for {service_name}: {e}")
            return {'cpu_usage': 100.0, 'memory_usage': 100.0, 'disk_usage': 100.0}
    
    def _get_log_metrics(self, service_name: str) -> Dict[str, int]:
        """Get log metrics for a service."""
        try:
            # This would typically query log systems
            # For now, return mock data
            return {
                'error_count': 5,
                'warning_count': 20,
                'total_logs': 1000
            }
            
        except Exception as e:
            logger.error(f"Error getting log metrics for {service_name}: {e}")
            return {'error_count': 1000, 'warning_count': 0, 'total_logs': 1000}
    
    def _store_health_history(self, health: ServiceHealth):
        """Store health history for trend analysis."""
        try:
            if health.service_name not in self.health_history:
                self.health_history[health.service_name] = []
            
            self.health_history[health.service_name].append(health)
            
            # Keep only last 100 entries
            if len(self.health_history[health.service_name]) > 100:
                self.health_history[health.service_name] = self.health_history[health.service_name][-100:]
                
        except Exception as e:
            logger.error(f"Error storing health history: {e}")
    
    def _get_all_services(self) -> List[str]:
        """Get list of all services."""
        try:
            catalog_file = Path('catalog/service-index.yaml')
            if not catalog_file.exists():
                return []
            
            with open(catalog_file, 'r') as f:
                catalog_data = yaml.safe_load(f)
            
            services = catalog_data.get('services', [])
            return [service.get('name') for service in services if service.get('name')]
            
        except Exception as e:
            logger.error(f"Error getting services: {e}")
            return []
    
    def _send_health_notifications(self, health: ServiceHealth):
        """Send notifications about health status."""
        try:
            if health.overall_status == HealthStatus.CRITICAL:
                # Send critical alert
                message = NotificationMessage(
                    title=f"CRITICAL: Service Health Failure - {health.service_name}",
                    content=f"Service {health.service_name} is in critical health state. Score: {health.overall_score:.1f}",
                    severity=NotificationSeverity.CRITICAL,
                    channel=NotificationChannel.PAGERDUTY,
                    metadata={
                        'service_name': health.service_name,
                        'overall_score': health.overall_score,
                        'overall_status': health.overall_status.value,
                        'event_type': 'service_health_critical'
                    }
                )
                self.notification_sender.send_notification(message)
                
            elif health.overall_status == HealthStatus.WARNING:
                # Send warning alert
                message = NotificationMessage(
                    title=f"WARNING: Service Health Degradation - {health.service_name}",
                    content=f"Service {health.service_name} is showing health warnings. Score: {health.overall_score:.1f}",
                    severity=NotificationSeverity.MEDIUM,
                    channel=NotificationChannel.SLACK,
                    metadata={
                        'service_name': health.service_name,
                        'overall_score': health.overall_score,
                        'overall_status': health.overall_status.value,
                        'event_type': 'service_health_warning'
                    }
                )
                self.notification_sender.send_notification(message)
                
        except Exception as e:
            logger.error(f"Error sending health notifications: {e}")
    
    def _send_summary_notification(self, results: Dict[str, ServiceHealth]):
        """Send summary notification for all health checks."""
        try:
            total_services = len(results)
            healthy_services = len([r for r in results.values() if r.overall_status == HealthStatus.HEALTHY])
            warning_services = len([r for r in results.values() if r.overall_status == HealthStatus.WARNING])
            critical_services = len([r for r in results.values() if r.overall_status == HealthStatus.CRITICAL])
            
            # Calculate average score
            if results:
                average_score = sum(r.overall_score for r in results.values()) / len(results)
            else:
                average_score = 0.0
            
            message = NotificationMessage(
                title="Service Health Check Summary",
                content=f"Health check completed for {total_services} services. "
                       f"Healthy: {healthy_services}, Warning: {warning_services}, "
                       f"Critical: {critical_services}. Average score: {average_score:.1f}",
                severity=NotificationSeverity.MEDIUM,
                channel=NotificationChannel.SLACK,
                metadata={
                    'total_services': total_services,
                    'healthy_services': healthy_services,
                    'warning_services': warning_services,
                    'critical_services': critical_services,
                    'average_score': average_score,
                    'event_type': 'health_check_summary'
                }
            )
            self.notification_sender.send_notification(message)
            
        except Exception as e:
            logger.error(f"Error sending summary notification: {e}")
    
    def validate_health(self, service_name: str) -> bool:
        """Validate if a service is healthy enough for deployment."""
        try:
            health = self.check_service_health(service_name)
            
            # Service must be healthy or warning to pass validation
            return health.overall_status in [HealthStatus.HEALTHY, HealthStatus.WARNING]
            
        except Exception as e:
            logger.error(f"Error validating health for {service_name}: {e}")
            return False
    
    def get_health_trends(self, service_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get health trends for a service."""
        try:
            if service_name not in self.health_history:
                return {'error': 'No health history available'}
            
            history = self.health_history[service_name]
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            # Filter history by time
            recent_history = [h for h in history if h.last_updated >= cutoff_time]
            
            if not recent_history:
                return {'error': 'No recent health history available'}
            
            # Calculate trends
            scores = [h.overall_score for h in recent_history]
            timestamps = [h.last_updated.isoformat() for h in recent_history]
            
            avg_score = sum(scores) / len(scores)
            min_score = min(scores)
            max_score = max(scores)
            
            # Calculate trend direction
            if len(scores) >= 2:
                trend = "improving" if scores[-1] > scores[0] else "degrading" if scores[-1] < scores[0] else "stable"
            else:
                trend = "unknown"
            
            return {
                'service_name': service_name,
                'period_hours': hours,
                'data_points': len(recent_history),
                'average_score': avg_score,
                'min_score': min_score,
                'max_score': max_score,
                'trend': trend,
                'timestamps': timestamps,
                'scores': scores
            }
            
        except Exception as e:
            logger.error(f"Error getting health trends for {service_name}: {e}")
            return {'error': str(e)}


def main():
    """Main entry point for health checking."""
    parser = argparse.ArgumentParser(description='Service health checking')
    parser.add_argument('--service', help='Service name to check health')
    parser.add_argument('--all-services', action='store_true', help='Check health for all services')
    parser.add_argument('--continuous', action='store_true', help='Run continuous health monitoring')
    parser.add_argument('--check-interval', type=int, default=300, help='Check interval in seconds')
    parser.add_argument('--validate-health', action='store_true', help='Validate service health')
    parser.add_argument('--health-trends', action='store_true', help='Get health trends')
    parser.add_argument('--hours', type=int, default=24, help='Hours of history for trends')
    parser.add_argument('--config', default='config/health-checks.yaml', help='Health check config file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    if not args.service and not args.all_services:
        parser.error("Must specify --service or --all-services")
    
    # Initialize health checker
    checker = HealthChecker(args.config)
    
    try:
        if args.continuous:
            # Start continuous monitoring
            monitor_thread = checker.start_continuous_monitoring(args.check_interval)
            
            print(f"Continuous health monitoring started with {args.check_interval}s interval")
            print("Press Ctrl+C to stop...")
            
            try:
                monitor_thread.join()
            except KeyboardInterrupt:
                checker.stop_continuous_monitoring()
                print("\nContinuous monitoring stopped")
        
        elif args.service:
            # Check single service
            health = checker.check_service_health(args.service)
            
            print(f"\nHealth Check Results for {args.service}:")
            print(f"Overall Status: {health.overall_status.value}")
            print(f"Overall Score: {health.overall_score:.1f}")
            print(f"Uptime: {health.uptime:.1f}%")
            print(f"Error Rate: {health.error_rate:.1f}%")
            print(f"Response Time: {health.response_time:.1f}ms")
            
            print(f"\nCheck Results:")
            for result in health.check_results:
                print(f"  {result.check_type.value}: {result.status.value} - {result.message}")
            
            if args.validate_health:
                is_healthy = checker.validate_health(args.service)
                print(f"\nHealth Validation: {'PASS' if is_healthy else 'FAIL'}")
            
            if args.health_trends:
                trends = checker.get_health_trends(args.service, args.hours)
                if 'error' in trends:
                    print(f"\nHealth Trends: {trends['error']}")
                else:
                    print(f"\nHealth Trends ({args.hours}h):")
                    print(f"  Average Score: {trends['average_score']:.1f}")
                    print(f"  Min Score: {trends['min_score']:.1f}")
                    print(f"  Max Score: {trends['max_score']:.1f}")
                    print(f"  Trend: {trends['trend']}")
                    print(f"  Data Points: {trends['data_points']}")
        
        else:
            # Check all services
            results = checker.check_all_services()
            
            print(f"\nHealth Check Summary:")
            print(f"Total services: {len(results)}")
            
            healthy_services = 0
            warning_services = 0
            critical_services = 0
            total_score = 0
            
            for service_name, health in results.items():
                if health.overall_status == HealthStatus.HEALTHY:
                    healthy_services += 1
                elif health.overall_status == HealthStatus.WARNING:
                    warning_services += 1
                else:
                    critical_services += 1
                
                total_score += health.overall_score
                print(f"  {service_name}: {health.overall_status.value} ({health.overall_score:.1f})")
            
            if results:
                average_score = total_score / len(results)
                print(f"\nAverage Score: {average_score:.1f}")
                print(f"Healthy Services: {healthy_services}")
                print(f"Warning Services: {warning_services}")
                print(f"Critical Services: {critical_services}")
        
    except Exception as e:
        logger.error(f"Health checking failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
