#!/usr/bin/env python3
"""
Execution Monitor for Script Performance Tracking

Provides lightweight monitoring for script execution with minimal overhead.
Tracks execution time, memory usage, success/failure rates, and resource consumption.

Features:
- Decorator-based monitoring with minimal code changes
- In-memory metrics storage with periodic file flush
- Memory usage tracking during execution
- Performance trend analysis
- Health status reporting
- Future enhancement ready for detailed profiling

Usage:
    from scripts.utils.execution_monitor import monitor_execution

    @monitor_execution("catalog-build")
    def build_catalog():
        # Your script logic here
        pass

    # Get performance metrics
    monitor = ExecutionMonitor.get_instance()
    metrics = monitor.get_metrics("catalog-build")
"""

import time
import psutil
import json
import logging
import threading
from functools import wraps
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    """Metrics for a single script execution."""
    script_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    memory_start: float = 0.0
    memory_peak: float = 0.0
    memory_end: float = 0.0
    success: bool = False
    error_message: Optional[str] = None
    cpu_percent: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScriptStats:
    """Aggregated statistics for a script."""
    script_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_duration: float = 0.0
    avg_duration: float = 0.0
    min_duration: float = float('inf')
    max_duration: float = 0.0
    avg_memory_peak: float = 0.0
    avg_cpu_percent: float = 0.0
    last_execution: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    recent_trend: str = "stable"  # improving, stable, degrading


class ExecutionMonitor:
    """
    Execution monitor for tracking script performance and health.
    
    Provides decorator-based monitoring with minimal overhead and
    comprehensive metrics collection for performance analysis.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, metrics_file: str = "execution_metrics.json"):
        """Initialize the execution monitor."""
        self.metrics_file = Path(metrics_file)
        self.current_executions: Dict[str, ExecutionMetrics] = {}
        self.execution_history: Dict[str, list] = {}
        self.script_stats: Dict[str, ScriptStats] = {}
        self._lock = threading.Lock()
        
        # Load existing metrics
        self._load_metrics()
        
        # Start background flush thread
        self._flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self._flush_thread.start()
        
        logger.info("Execution monitor initialized")
    
    @classmethod
    def get_instance(cls, metrics_file: str = "execution_metrics.json") -> 'ExecutionMonitor':
        """Get singleton instance of execution monitor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(metrics_file)
        return cls._instance
    
    def start_execution(self, script_name: str, parameters: Dict[str, Any] = None) -> str:
        """Start monitoring an execution."""
        execution_id = f"{script_name}_{int(time.time() * 1000)}"
        
        with self._lock:
            # Get current process memory usage
            process = psutil.Process()
            memory_info = process.memory_info()
            
            metrics = ExecutionMetrics(
                script_name=script_name,
                start_time=time.time(),
                memory_start=memory_info.rss / 1024 / 1024,  # MB
                parameters=parameters or {}
            )
            
            self.current_executions[execution_id] = metrics
            
            logger.debug(f"Started monitoring execution: {execution_id}")
            return execution_id
    
    def end_execution(self, execution_id: str, success: bool = True, error_message: str = None):
        """End monitoring an execution."""
        with self._lock:
            if execution_id not in self.current_executions:
                logger.warning(f"Execution ID not found: {execution_id}")
                return
            
            metrics = self.current_executions[execution_id]
            
            # Calculate final metrics
            metrics.end_time = time.time()
            metrics.duration = metrics.end_time - metrics.start_time
            metrics.success = success
            metrics.error_message = error_message
            
            # Get final memory usage
            process = psutil.Process()
            memory_info = process.memory_info()
            metrics.memory_end = memory_info.rss / 1024 / 1024  # MB
            
            # Get CPU usage (approximate)
            metrics.cpu_percent = process.cpu_percent()
            
            # Move to history
            if metrics.script_name not in self.execution_history:
                self.execution_history[metrics.script_name] = []
            
            self.execution_history[metrics.script_name].append(metrics)
            
            # Update aggregated stats
            self._update_script_stats(metrics)
            
            # Remove from current executions
            del self.current_executions[execution_id]
            
            logger.debug(f"Completed monitoring execution: {execution_id} "
                        f"(duration: {metrics.duration:.2f}s, "
                        f"success: {success})")
    
    def _update_script_stats(self, metrics: ExecutionMetrics):
        """Update aggregated statistics for a script."""
        script_name = metrics.script_name
        
        if script_name not in self.script_stats:
            self.script_stats[script_name] = ScriptStats(script_name=script_name)
        
        stats = self.script_stats[script_name]
        
        # Update counters
        stats.total_executions += 1
        if metrics.success:
            stats.successful_executions += 1
            stats.last_success = datetime.now()
        else:
            stats.failed_executions += 1
            stats.last_failure = datetime.now()
        
        stats.last_execution = datetime.now()
        
        # Update duration stats
        stats.total_duration += metrics.duration
        stats.avg_duration = stats.total_duration / stats.total_executions
        stats.min_duration = min(stats.min_duration, metrics.duration)
        stats.max_duration = max(stats.max_duration, metrics.duration)
        
        # Update memory and CPU stats
        stats.avg_memory_peak = (
            (stats.avg_memory_peak * (stats.total_executions - 1) + metrics.memory_peak) 
            / stats.total_executions
        )
        stats.avg_cpu_percent = (
            (stats.avg_cpu_percent * (stats.total_executions - 1) + metrics.cpu_percent) 
            / stats.total_executions
        )
        
        # Calculate trend (simplified)
        self._calculate_trend(stats)
    
    def _calculate_trend(self, stats: ScriptStats):
        """Calculate performance trend for a script."""
        if stats.total_executions < 3:
            stats.recent_trend = "stable"
            return
        
        # Get last 5 executions
        recent_executions = self.execution_history[stats.script_name][-5:]
        durations = [ex.duration for ex in recent_executions if ex.duration is not None]
        
        if len(durations) < 3:
            stats.recent_trend = "stable"
            return
        
        # Simple trend calculation
        first_half = durations[:len(durations)//2]
        second_half = durations[len(durations)//2:]
        
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        
        change_percent = (avg_second - avg_first) / avg_first * 100
        
        if change_percent > 10:
            stats.recent_trend = "degrading"
        elif change_percent < -10:
            stats.recent_trend = "improving"
        else:
            stats.recent_trend = "stable"
    
    def get_metrics(self, script_name: str = None) -> Dict[str, Any]:
        """Get metrics for a specific script or all scripts."""
        with self._lock:
            if script_name:
                if script_name in self.script_stats:
                    stats = self.script_stats[script_name]
                    return {
                        "script_name": script_name,
                        "stats": {
                            "total_executions": stats.total_executions,
                            "successful_executions": stats.successful_executions,
                            "failed_executions": stats.failed_executions,
                            "success_rate": stats.successful_executions / max(stats.total_executions, 1),
                            "avg_duration": stats.avg_duration,
                            "min_duration": stats.min_duration if stats.min_duration != float('inf') else 0,
                            "max_duration": stats.max_duration,
                            "avg_memory_peak": stats.avg_memory_peak,
                            "avg_cpu_percent": stats.avg_cpu_percent,
                            "recent_trend": stats.recent_trend,
                            "last_execution": stats.last_execution.isoformat() if stats.last_execution else None,
                            "last_success": stats.last_success.isoformat() if stats.last_success else None,
                            "last_failure": stats.last_failure.isoformat() if stats.last_failure else None
                        },
                        "recent_executions": [
                            {
                                "start_time": ex.start_time,
                                "duration": ex.duration,
                                "success": ex.success,
                                "memory_peak": ex.memory_peak,
                                "error_message": ex.error_message
                            }
                            for ex in self.execution_history.get(script_name, [])[-10:]
                        ]
                    }
                else:
                    return {"script_name": script_name, "stats": None, "recent_executions": []}
            else:
                return {
                    "all_scripts": {
                        name: self.get_metrics(name) for name in self.script_stats.keys()
                    },
                    "current_executions": len(self.current_executions),
                    "total_scripts_monitored": len(self.script_stats)
                }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status of monitored scripts."""
        with self._lock:
            if not self.script_stats:
                return {"status": "no_data", "message": "No scripts monitored yet"}
            
            total_scripts = len(self.script_stats)
            healthy_scripts = 0
            degraded_scripts = 0
            failed_scripts = 0
            
            for stats in self.script_stats.values():
                if stats.total_executions == 0:
                    continue
                
                success_rate = stats.successful_executions / stats.total_executions
                
                if success_rate >= 0.95 and stats.recent_trend in ["stable", "improving"]:
                    healthy_scripts += 1
                elif success_rate >= 0.8:
                    degraded_scripts += 1
                else:
                    failed_scripts += 1
            
            if healthy_scripts == total_scripts:
                status = "healthy"
            elif healthy_scripts + degraded_scripts >= total_scripts * 0.8:
                status = "degraded"
            else:
                status = "unhealthy"
            
            return {
                "status": status,
                "total_scripts": total_scripts,
                "healthy_scripts": healthy_scripts,
                "degraded_scripts": degraded_scripts,
                "failed_scripts": failed_scripts,
                "health_percentage": (healthy_scripts / total_scripts * 100) if total_scripts > 0 else 0
            }
    
    def _load_metrics(self):
        """Load metrics from file."""
        if not self.metrics_file.exists():
            return
        
        try:
            with open(self.metrics_file, 'r') as f:
                data = json.load(f)
            
            # Load script stats
            if 'script_stats' in data:
                for script_name, stats_data in data['script_stats'].items():
                    stats = ScriptStats(script_name=script_name)
                    for key, value in stats_data.items():
                        if key == 'last_execution' and value:
                            stats.last_execution = datetime.fromisoformat(value)
                        elif key == 'last_success' and value:
                            stats.last_success = datetime.fromisoformat(value)
                        elif key == 'last_failure' and value:
                            stats.last_failure = datetime.fromisoformat(value)
                        else:
                            setattr(stats, key, value)
                    self.script_stats[script_name] = stats
            
            logger.info(f"Loaded metrics for {len(self.script_stats)} scripts")
            
        except Exception as e:
            logger.warning(f"Failed to load metrics: {e}")
    
    def _save_metrics(self):
        """Save metrics to file."""
        try:
            with self._lock:
                data = {
                    'script_stats': {
                        name: {
                            'script_name': stats.script_name,
                            'total_executions': stats.total_executions,
                            'successful_executions': stats.successful_executions,
                            'failed_executions': stats.failed_executions,
                            'total_duration': stats.total_duration,
                            'avg_duration': stats.avg_duration,
                            'min_duration': stats.min_duration if stats.min_duration != float('inf') else 0,
                            'max_duration': stats.max_duration,
                            'avg_memory_peak': stats.avg_memory_peak,
                            'avg_cpu_percent': stats.avg_cpu_percent,
                            'recent_trend': stats.recent_trend,
                            'last_execution': stats.last_execution.isoformat() if stats.last_execution else None,
                            'last_success': stats.last_success.isoformat() if stats.last_success else None,
                            'last_failure': stats.last_failure.isoformat() if stats.last_failure else None
                        }
                        for name, stats in self.script_stats.items()
                    },
                    'last_updated': datetime.now().isoformat()
                }
            
            with open(self.metrics_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug("Metrics saved to file")
            
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def _periodic_flush(self):
        """Periodically flush metrics to file."""
        while True:
            time.sleep(300)  # Flush every 5 minutes
            self._save_metrics()
    
    def cleanup_old_metrics(self, days_to_keep: int = 30):
        """Clean up old execution history."""
        cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
        
        with self._lock:
            for script_name, executions in self.execution_history.items():
                self.execution_history[script_name] = [
                    ex for ex in executions if ex.start_time > cutoff_time
                ]
        
        logger.info(f"Cleaned up metrics older than {days_to_keep} days")


def monitor_execution(script_name: str, parameters: Dict[str, Any] = None):
    """
    Decorator for monitoring script execution.
    
    Args:
        script_name: Name identifier for the script
        parameters: Optional parameters to track
    
    Usage:
        @monitor_execution("catalog-build")
        def build_catalog():
            # Script logic here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            monitor = ExecutionMonitor.get_instance()
            execution_id = monitor.start_execution(script_name, parameters)
            
            try:
                result = func(*args, **kwargs)
                monitor.end_execution(execution_id, success=True)
                return result
            except Exception as e:
                monitor.end_execution(execution_id, success=False, error_message=str(e))
                raise
        
        return wrapper
    return decorator


# Example usage and testing
if __name__ == "__main__":
    import logging
    import random
    import time
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n=== Execution Monitor Demo ===\n")
    
    # Example 1: Basic monitoring
    print("1. Basic execution monitoring:")
    
    @monitor_execution("demo-script")
    def demo_script(sleep_time: float = 0.1):
        """Simulate a script execution."""
        time.sleep(sleep_time)
        if random.random() < 0.1:  # 10% failure rate
            raise Exception("Simulated failure")
        return {"status": "success", "sleep_time": sleep_time}
    
    # Run multiple executions
    for i in range(5):
        try:
            result = demo_script(sleep_time=random.uniform(0.05, 0.2))
            print(f"   Execution {i+1}: Success")
        except Exception as e:
            print(f"   Execution {i+1}: Failed - {e}")
    
    # Example 2: Get metrics
    print("\n2. Execution metrics:")
    monitor = ExecutionMonitor.get_instance()
    metrics = monitor.get_metrics("demo-script")
    
    if metrics["stats"]:
        stats = metrics["stats"]
        print(f"   Total executions: {stats['total_executions']}")
        print(f"   Success rate: {stats['success_rate']:.2%}")
        print(f"   Average duration: {stats['avg_duration']:.3f}s")
        print(f"   Memory peak: {stats['avg_memory_peak']:.1f}MB")
        print(f"   Trend: {stats['recent_trend']}")
    
    # Example 3: Health status
    print("\n3. Health status:")
    health = monitor.get_health_status()
    print(f"   Status: {health['status']}")
    print(f"   Health percentage: {health['health_percentage']:.1f}%")
    
    print("\n=== Demo complete ===\n")
    print("Execution monitor is ready for production use!")
    print("Apply @monitor_execution decorator to scripts for performance tracking.")
