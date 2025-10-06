#!/usr/bin/env python3
"""
254Carbon Meta Repository - Performance Monitoring

Monitors and analyzes performance metrics for catalog operations,
service discovery, quality computation, and other system components.

Usage:
    python scripts/monitor_performance.py --component catalog --duration 300
    python scripts/monitor_performance.py --component all --export-prometheus
    python scripts/monitor_performance.py --analyze-trends --days 7

Features:
- Real-time performance monitoring
- Historical trend analysis
- Performance regression detection
- Resource usage tracking
- Alert generation
- Prometheus metrics export
- Performance benchmarking
- Bottleneck identification
"""

import os
import sys
import json
import yaml
import argparse
import logging
import time
import psutil
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import concurrent.futures
import statistics

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from scripts.utils import audit_logger, monitor_execution, redis_client
from scripts.send_notifications import NotificationSender, NotificationMessage, NotificationSeverity, NotificationChannel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/performance-monitoring.log')
    ]
)
logger = logging.getLogger(__name__)


class ComponentType(Enum):
    """Performance monitoring component types."""
    CATALOG_BUILD = "catalog_build"
    SERVICE_DISCOVERY = "service_discovery"
    QUALITY_COMPUTATION = "quality_computation"
    DRIFT_DETECTION = "drift_detection"
    HEALTH_CHECKING = "health_checking"
    NOTIFICATION_SENDING = "notification_sending"
    DASHBOARD_GENERATION = "dashboard_generation"
    MANIFEST_VALIDATION = "manifest_validation"


class MetricType(Enum):
    """Metric types."""
    EXECUTION_TIME = "execution_time"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"
    DISK_USAGE = "disk_usage"
    NETWORK_IO = "network_io"
    CACHE_HIT_RATE = "cache_hit_rate"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"


@dataclass
class PerformanceMetric:
    """Performance metric data."""
    component: ComponentType
    metric_type: MetricType
    value: float
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceThreshold:
    """Performance threshold configuration."""
    component: ComponentType
    metric_type: MetricType
    warning_threshold: float
    critical_threshold: float
    unit: str


class PerformanceMonitor:
    """Performance monitoring engine."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the performance monitor."""
        self.config_path = config_path or 'config/performance.yaml'
        self.config = self._load_config()
        self.notification_sender = NotificationSender()
        self.metrics_history = []
        self.thresholds = self._load_thresholds()
        self.monitoring_active = False
        self.monitor_thread = None
        
        # Performance tracking
        self.current_metrics = {}
        self.baseline_metrics = {}
        self.performance_alerts = []
        
        # System resource tracking
        self.system_stats = {
            'cpu_percent': 0.0,
            'memory_percent': 0.0,
            'disk_percent': 0.0,
            'network_io': {'bytes_sent': 0, 'bytes_recv': 0}
        }
        
        # Component performance tracking
        self.component_stats = {
            component: {
                'execution_times': [],
                'error_count': 0,
                'success_count': 0,
                'last_execution': None,
                'avg_execution_time': 0.0,
                'max_execution_time': 0.0,
                'min_execution_time': float('inf')
            }
            for component in ComponentType
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """Load performance monitoring configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Performance config not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing performance config: {e}")
            return {}
    
    def _load_thresholds(self) -> List[PerformanceThreshold]:
        """Load performance thresholds."""
        thresholds = []
        
        # Default thresholds
        default_thresholds = {
            ComponentType.CATALOG_BUILD: {
                MetricType.EXECUTION_TIME: (300.0, 600.0, "seconds"),
                MetricType.MEMORY_USAGE: (512.0, 1024.0, "MB"),
                MetricType.CPU_USAGE: (80.0, 95.0, "percent")
            },
            ComponentType.SERVICE_DISCOVERY: {
                MetricType.EXECUTION_TIME: (60.0, 120.0, "seconds"),
                MetricType.MEMORY_USAGE: (256.0, 512.0, "MB"),
                MetricType.CPU_USAGE: (70.0, 90.0, "percent")
            },
            ComponentType.QUALITY_COMPUTATION: {
                MetricType.EXECUTION_TIME: (180.0, 360.0, "seconds"),
                MetricType.MEMORY_USAGE: (384.0, 768.0, "MB"),
                MetricType.CPU_USAGE: (75.0, 90.0, "percent")
            },
            ComponentType.DRIFT_DETECTION: {
                MetricType.EXECUTION_TIME: (120.0, 240.0, "seconds"),
                MetricType.MEMORY_USAGE: (256.0, 512.0, "MB"),
                MetricType.CPU_USAGE: (70.0, 85.0, "percent")
            },
            ComponentType.HEALTH_CHECKING: {
                MetricType.EXECUTION_TIME: (30.0, 60.0, "seconds"),
                MetricType.MEMORY_USAGE: (128.0, 256.0, "MB"),
                MetricType.CPU_USAGE: (60.0, 80.0, "percent")
            }
        }
        
        for component, metrics in default_thresholds.items():
            for metric_type, (warning, critical, unit) in metrics.items():
                thresholds.append(PerformanceThreshold(
                    component=component,
                    metric_type=metric_type,
                    warning_threshold=warning,
                    critical_threshold=critical,
                    unit=unit
                ))
        
        return thresholds
    
    def start_monitoring(self, interval: int = 60):
        """Start continuous performance monitoring."""
        logger.info(f"Starting performance monitoring with {interval}s interval")
        
        self.monitoring_active = True
        
        def monitor_loop():
            while self.monitoring_active:
                try:
                    # Collect system metrics
                    self._collect_system_metrics()
                    
                    # Collect component metrics
                    self._collect_component_metrics()
                    
                    # Check thresholds
                    self._check_thresholds()
                    
                    # Store metrics
                    self._store_metrics()
                    
                    # Wait for next collection
                    time.sleep(interval)
                    
                except Exception as e:
                    logger.error(f"Error in performance monitoring: {e}")
                    time.sleep(interval)
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        return self.monitor_thread
    
    def stop_monitoring(self):
        """Stop continuous performance monitoring."""
        logger.info("Stopping performance monitoring")
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
    
    def record_execution_time(self, component: ComponentType, execution_time: float, metadata: Dict[str, Any] = None):
        """Record execution time for a component."""
        try:
            # Update component stats
            stats = self.component_stats[component]
            stats['execution_times'].append(execution_time)
            stats['last_execution'] = datetime.now(timezone.utc)
            stats['success_count'] += 1
            
            # Keep only last 100 execution times
            if len(stats['execution_times']) > 100:
                stats['execution_times'] = stats['execution_times'][-100:]
            
            # Update statistics
            stats['avg_execution_time'] = statistics.mean(stats['execution_times'])
            stats['max_execution_time'] = max(stats['execution_times'])
            stats['min_execution_time'] = min(stats['execution_times'])
            
            # Create metric
            metric = PerformanceMetric(
                component=component,
                metric_type=MetricType.EXECUTION_TIME,
                value=execution_time,
                timestamp=datetime.now(timezone.utc),
                metadata=metadata or {}
            )
            
            # Store metric
            self.metrics_history.append(metric)
            
            # Check thresholds
            self._check_component_threshold(metric)
            
            logger.debug(f"Recorded execution time for {component.value}: {execution_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Error recording execution time: {e}")
    
    def record_error(self, component: ComponentType, error: Exception, metadata: Dict[str, Any] = None):
        """Record an error for a component."""
        try:
            # Update component stats
            stats = self.component_stats[component]
            stats['error_count'] += 1
            
            # Create metric
            metric = PerformanceMetric(
                component=component,
                metric_type=MetricType.ERROR_RATE,
                value=1.0,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    'error_type': type(error).__name__,
                    'error_message': str(error),
                    **(metadata or {})
                }
            )
            
            # Store metric
            self.metrics_history.append(metric)
            
            logger.warning(f"Recorded error for {component.value}: {error}")
            
        except Exception as e:
            logger.error(f"Error recording error: {e}")
    
    def _collect_system_metrics(self):
        """Collect system resource metrics."""
        try:
            # CPU usage
            self.system_stats['cpu_percent'] = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.system_stats['memory_percent'] = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.system_stats['disk_percent'] = (disk.used / disk.total) * 100
            
            # Network I/O
            network = psutil.net_io_counters()
            self.system_stats['network_io'] = {
                'bytes_sent': network.bytes_sent,
                'bytes_recv': network.bytes_recv
            }
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    def _collect_component_metrics(self):
        """Collect component-specific metrics."""
        try:
            # Get Redis stats
            redis_stats = redis_client.get_stats()
            
            # Create cache hit rate metric
            if redis_stats['stats']['hits'] + redis_stats['stats']['misses'] > 0:
                hit_rate = redis_stats['stats']['hits'] / (redis_stats['stats']['hits'] + redis_stats['stats']['misses'])
                
                metric = PerformanceMetric(
                    component=ComponentType.CATALOG_BUILD,
                    metric_type=MetricType.CACHE_HIT_RATE,
                    value=hit_rate * 100,  # Convert to percentage
                    timestamp=datetime.now(timezone.utc),
                    metadata={'redis_available': redis_stats['redis_available']}
                )
                
                self.metrics_history.append(metric)
            
        except Exception as e:
            logger.error(f"Error collecting component metrics: {e}")
    
    def _check_thresholds(self):
        """Check performance thresholds."""
        try:
            for metric in self.metrics_history[-100:]:  # Check last 100 metrics
                self._check_component_threshold(metric)
                
        except Exception as e:
            logger.error(f"Error checking thresholds: {e}")
    
    def _check_component_threshold(self, metric: PerformanceMetric):
        """Check threshold for a specific metric."""
        try:
            # Find matching threshold
            threshold = None
            for t in self.thresholds:
                if t.component == metric.component and t.metric_type == metric.metric_type:
                    threshold = t
                    break
            
            if not threshold:
                return
            
            # Check thresholds
            if metric.value >= threshold.critical_threshold:
                self._send_threshold_alert(metric, threshold, "CRITICAL")
            elif metric.value >= threshold.warning_threshold:
                self._send_threshold_alert(metric, threshold, "WARNING")
                
        except Exception as e:
            logger.error(f"Error checking component threshold: {e}")
    
    def _send_threshold_alert(self, metric: PerformanceMetric, threshold: PerformanceThreshold, severity: str):
        """Send threshold alert."""
        try:
            # Check if we already sent this alert recently
            alert_key = f"{metric.component.value}_{metric.metric_type.value}_{severity}"
            recent_alerts = [a for a in self.performance_alerts 
                           if a['key'] == alert_key and 
                           datetime.now(timezone.utc) - a['timestamp'] < timedelta(minutes=5)]
            
            if recent_alerts:
                return  # Don't spam alerts
            
            # Create alert
            alert = {
                'key': alert_key,
                'timestamp': datetime.now(timezone.utc),
                'component': metric.component.value,
                'metric_type': metric.metric_type.value,
                'value': metric.value,
                'threshold': threshold.warning_threshold if severity == "WARNING" else threshold.critical_threshold,
                'severity': severity
            }
            
            self.performance_alerts.append(alert)
            
            # Send notification
            if severity == "CRITICAL":
                notification_severity = NotificationSeverity.CRITICAL
                channel = NotificationChannel.PAGERDUTY
            else:
                notification_severity = NotificationSeverity.MEDIUM
                channel = NotificationChannel.SLACK
            
            message = NotificationMessage(
                title=f"{severity}: Performance Threshold Breached - {metric.component.value}",
                content=f"Component {metric.component.value} exceeded {severity.lower()} threshold for {metric.metric_type.value}. "
                       f"Value: {metric.value:.2f} {threshold.unit}, Threshold: {threshold.warning_threshold if severity == 'WARNING' else threshold.critical_threshold} {threshold.unit}",
                severity=notification_severity,
                channel=channel,
                metadata={
                    'component': metric.component.value,
                    'metric_type': metric.metric_type.value,
                    'value': metric.value,
                    'threshold': threshold.warning_threshold if severity == "WARNING" else threshold.critical_threshold,
                    'unit': threshold.unit,
                    'event_type': 'performance_threshold_breach'
                }
            )
            
            self.notification_sender.send_notification(message)
            
        except Exception as e:
            logger.error(f"Error sending threshold alert: {e}")
    
    def _store_metrics(self):
        """Store metrics to persistent storage."""
        try:
            # Keep only last 1000 metrics
            if len(self.metrics_history) > 1000:
                self.metrics_history = self.metrics_history[-1000:]
            
            # Store to Redis cache
            metrics_data = {
                'metrics': [
                    {
                        'component': m.component.value,
                        'metric_type': m.metric_type.value,
                        'value': m.value,
                        'timestamp': m.timestamp.isoformat(),
                        'metadata': m.metadata
                    }
                    for m in self.metrics_history[-100:]  # Store last 100 metrics
                ],
                'system_stats': self.system_stats,
                'component_stats': {
                    component.value: {
                        'avg_execution_time': stats['avg_execution_time'],
                        'max_execution_time': stats['max_execution_time'],
                        'min_execution_time': stats['min_execution_time'],
                        'error_count': stats['error_count'],
                        'success_count': stats['success_count'],
                        'last_execution': stats['last_execution'].isoformat() if stats['last_execution'] else None
                    }
                    for component, stats in self.component_stats.items()
                },
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            redis_client.set("performance_metrics", metrics_data, ttl=3600, fallback_to_file=True)
            
        except Exception as e:
            logger.error(f"Error storing metrics: {e}")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        try:
            # Calculate summary statistics
            summary = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'system_stats': self.system_stats,
                'component_stats': {},
                'recent_alerts': len([a for a in self.performance_alerts 
                                    if datetime.now(timezone.utc) - a['timestamp'] < timedelta(hours=1)]),
                'total_metrics': len(self.metrics_history)
            }
            
            # Add component statistics
            for component, stats in self.component_stats.items():
                summary['component_stats'][component.value] = {
                    'avg_execution_time': stats['avg_execution_time'],
                    'max_execution_time': stats['max_execution_time'],
                    'min_execution_time': stats['min_execution_time'],
                    'error_count': stats['error_count'],
                    'success_count': stats['success_count'],
                    'error_rate': stats['error_count'] / max(stats['error_count'] + stats['success_count'], 1) * 100,
                    'last_execution': stats['last_execution'].isoformat() if stats['last_execution'] else None
                }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {}
    
    def analyze_trends(self, days: int = 7) -> Dict[str, Any]:
        """Analyze performance trends."""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
            recent_metrics = [m for m in self.metrics_history if m.timestamp >= cutoff_time]
            
            if not recent_metrics:
                return {'error': 'No recent metrics available'}
            
            # Group metrics by component and type
            trends = {}
            
            for metric in recent_metrics:
                key = f"{metric.component.value}_{metric.metric_type.value}"
                if key not in trends:
                    trends[key] = []
                trends[key].append(metric.value)
            
            # Calculate trend statistics
            trend_analysis = {}
            for key, values in trends.items():
                if len(values) >= 2:
                    # Calculate trend direction
                    first_half = values[:len(values)//2]
                    second_half = values[len(values)//2:]
                    
                    first_avg = statistics.mean(first_half)
                    second_avg = statistics.mean(second_half)
                    
                    trend_direction = "improving" if second_avg < first_avg else "degrading" if second_avg > first_avg else "stable"
                    trend_percentage = abs(second_avg - first_avg) / first_avg * 100 if first_avg > 0 else 0
                    
                    trend_analysis[key] = {
                        'trend_direction': trend_direction,
                        'trend_percentage': trend_percentage,
                        'current_avg': second_avg,
                        'previous_avg': first_avg,
                        'data_points': len(values),
                        'min_value': min(values),
                        'max_value': max(values)
                    }
            
            return {
                'period_days': days,
                'total_metrics': len(recent_metrics),
                'trends': trend_analysis,
                'analysis_timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            return {'error': str(e)}
    
    def benchmark_component(self, component: ComponentType, iterations: int = 10) -> Dict[str, Any]:
        """Benchmark a specific component."""
        try:
            logger.info(f"Benchmarking {component.value} with {iterations} iterations")
            
            # This would typically run the actual component
            # For now, we'll simulate benchmarking
            execution_times = []
            
            for i in range(iterations):
                start_time = time.time()
                
                # Simulate component execution
                time.sleep(0.1)  # Simulate work
                
                execution_time = time.time() - start_time
                execution_times.append(execution_time)
                
                # Record the execution time
                self.record_execution_time(component, execution_time, {'iteration': i})
            
            # Calculate statistics
            avg_time = statistics.mean(execution_times)
            min_time = min(execution_times)
            max_time = max(execution_times)
            std_dev = statistics.stdev(execution_times) if len(execution_times) > 1 else 0
            
            return {
                'component': component.value,
                'iterations': iterations,
                'avg_execution_time': avg_time,
                'min_execution_time': min_time,
                'max_execution_time': max_time,
                'std_deviation': std_dev,
                'execution_times': execution_times,
                'benchmark_timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error benchmarking component {component.value}: {e}")
            return {'error': str(e)}
    
    def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format."""
        try:
            metrics = []
            
            # System metrics
            metrics.append(f"# HELP system_cpu_percent CPU usage percentage")
            metrics.append(f"# TYPE system_cpu_percent gauge")
            metrics.append(f"system_cpu_percent {self.system_stats['cpu_percent']}")
            
            metrics.append(f"# HELP system_memory_percent Memory usage percentage")
            metrics.append(f"# TYPE system_memory_percent gauge")
            metrics.append(f"system_memory_percent {self.system_stats['memory_percent']}")
            
            metrics.append(f"# HELP system_disk_percent Disk usage percentage")
            metrics.append(f"# TYPE system_disk_percent gauge")
            metrics.append(f"system_disk_percent {self.system_stats['disk_percent']}")
            
            # Component metrics
            for component, stats in self.component_stats.items():
                component_name = component.value.replace('_', '_')
                
                metrics.append(f"# HELP component_avg_execution_time Average execution time per component")
                metrics.append(f"# TYPE component_avg_execution_time gauge")
                metrics.append(f"component_avg_execution_time{{component=\"{component_name}\"}} {stats['avg_execution_time']}")
                
                metrics.append(f"# HELP component_error_count Error count per component")
                metrics.append(f"# TYPE component_error_count counter")
                metrics.append(f"component_error_count{{component=\"{component_name}\"}} {stats['error_count']}")
                
                metrics.append(f"# HELP component_success_count Success count per component")
                metrics.append(f"# TYPE component_success_count counter")
                metrics.append(f"component_success_count{{component=\"{component_name}\"}} {stats['success_count']}")
            
            return "\n".join(metrics)
            
        except Exception as e:
            logger.error(f"Error exporting Prometheus metrics: {e}")
            return f"# Error exporting metrics: {e}"


def main():
    """Main entry point for performance monitoring."""
    parser = argparse.ArgumentParser(description='Performance monitoring and analysis')
    parser.add_argument('--component', help='Component to monitor', 
                       choices=[c.value for c in ComponentType] + ['all'])
    parser.add_argument('--duration', type=int, default=300, help='Monitoring duration in seconds')
    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval in seconds')
    parser.add_argument('--analyze-trends', action='store_true', help='Analyze performance trends')
    parser.add_argument('--days', type=int, default=7, help='Days of history for trend analysis')
    parser.add_argument('--benchmark', action='store_true', help='Run performance benchmark')
    parser.add_argument('--iterations', type=int, default=10, help='Benchmark iterations')
    parser.add_argument('--export-prometheus', action='store_true', help='Export Prometheus metrics')
    parser.add_argument('--config', default='config/performance.yaml', help='Performance config file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    # Initialize performance monitor
    monitor = PerformanceMonitor(args.config)
    
    try:
        if args.export_prometheus:
            # Export Prometheus metrics
            metrics = monitor.export_prometheus_metrics()
            print(metrics)
        
        elif args.analyze_trends:
            # Analyze trends
            trends = monitor.analyze_trends(args.days)
            print(f"\nPerformance Trend Analysis ({args.days} days):")
            print(json.dumps(trends, indent=2))
        
        elif args.benchmark:
            # Run benchmark
            if args.component and args.component != 'all':
                component = ComponentType(args.component)
                results = monitor.benchmark_component(component, args.iterations)
                print(f"\nBenchmark Results for {component.value}:")
                print(json.dumps(results, indent=2))
            else:
                print("Must specify a component for benchmarking")
        
        else:
            # Start monitoring
            if args.component == 'all':
                components = list(ComponentType)
            elif args.component:
                components = [ComponentType(args.component)]
            else:
                components = [ComponentType.CATALOG_BUILD]  # Default
            
            print(f"Starting performance monitoring for {len(components)} components...")
            print(f"Duration: {args.duration}s, Interval: {args.interval}s")
            
            # Start monitoring
            monitor_thread = monitor.start_monitoring(args.interval)
            
            try:
                # Wait for specified duration
                time.sleep(args.duration)
            except KeyboardInterrupt:
                print("\nMonitoring interrupted by user")
            
            # Stop monitoring
            monitor.stop_monitoring()
            
            # Get summary
            summary = monitor.get_performance_summary()
            print(f"\nPerformance Summary:")
            print(json.dumps(summary, indent=2))
        
    except Exception as e:
        logger.error(f"Performance monitoring failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
