#!/usr/bin/env python3
"""
Performance Regression Test Suite

Tracks performance over time and detects performance regressions.
Compares current performance against historical baselines and alerts on degradation.

Usage:
    python tests/performance/test_performance_regression.py [--baseline-file FILE] [--threshold 0.1]

Features:
- Performance baseline establishment
- Regression detection
- Trend analysis
- Alert generation
- Historical comparison
- Performance threshold monitoring
- Automated regression testing
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import statistics
import math

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.utils import ExecutionMonitor
from tests.performance.benchmark_suite import BenchmarkSuite

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('tests/performance/regression.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceBaseline:
    """Performance baseline for a script and catalog size."""
    script_name: str
    catalog_size: int
    avg_execution_time: float
    avg_memory_peak: float
    avg_cpu_percent: float
    std_dev_execution_time: float
    std_dev_memory_peak: float
    std_dev_cpu_percent: float
    sample_count: int
    established_at: str
    last_updated: str


@dataclass
class RegressionAlert:
    """Performance regression alert."""
    script_name: str
    catalog_size: int
    metric_type: str
    baseline_value: float
    current_value: float
    degradation_percent: float
    severity: str
    threshold: float
    timestamp: str
    recommendation: str


@dataclass
class PerformanceTrend:
    """Performance trend analysis."""
    script_name: str
    catalog_size: int
    metric_type: str
    trend_direction: str
    trend_strength: float
    recent_values: List[float]
    historical_values: List[float]
    trend_period_days: int


class PerformanceRegressionDetector:
    """Detects performance regressions and tracks trends."""
    
    def __init__(self, baseline_file: str = "tests/performance/baseline.json", threshold: float = 0.1):
        """
        Initialize performance regression detector.
        
        Args:
            baseline_file: Path to baseline file
            threshold: Performance degradation threshold (0.1 = 10%)
        """
        self.baseline_file = Path(baseline_file)
        self.threshold = threshold
        self.baselines: Dict[Tuple[str, int], PerformanceBaseline] = {}
        self.historical_data: List[Dict[str, Any]] = []
        
        # Load existing baselines
        self._load_baselines()
        
        logger.info(f"Performance regression detector initialized: threshold={threshold:.1%}")
    
    def _load_baselines(self):
        """Load performance baselines from file."""
        if not self.baseline_file.exists():
            logger.info("No baseline file found, will create new baselines")
            return
        
        try:
            with open(self.baseline_file, 'r') as f:
                data = json.load(f)
            
            for baseline_data in data.get('baselines', []):
                key = (baseline_data['script_name'], baseline_data['catalog_size'])
                baseline = PerformanceBaseline(**baseline_data)
                self.baselines[key] = baseline
            
            self.historical_data = data.get('historical_data', [])
            
            logger.info(f"Loaded {len(self.baselines)} baselines from {self.baseline_file}")
            
        except Exception as e:
            logger.error(f"Failed to load baselines: {e}")
    
    def _save_baselines(self):
        """Save performance baselines to file."""
        try:
            self.baseline_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "metadata": {
                    "last_updated": datetime.now().isoformat(),
                    "threshold": self.threshold,
                    "baseline_count": len(self.baselines)
                },
                "baselines": [asdict(baseline) for baseline in self.baselines.values()],
                "historical_data": self.historical_data
            }
            
            with open(self.baseline_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            
            logger.info(f"Saved {len(self.baselines)} baselines to {self.baseline_file}")
            
        except Exception as e:
            logger.error(f"Failed to save baselines: {e}")
    
    def establish_baseline(self, benchmark_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Establish performance baselines from benchmark results.
        
        Args:
            benchmark_results: List of benchmark result summaries
        
        Returns:
            Baseline establishment report
        """
        logger.info("Establishing performance baselines")
        
        new_baselines = 0
        updated_baselines = 0
        
        for summary in benchmark_results:
            script_name = summary['script_name']
            catalog_size = summary['catalog_size']
            key = (script_name, catalog_size)
            
            # Calculate statistics
            avg_execution_time = summary['avg_execution_time']
            avg_memory_peak = summary['avg_memory_peak']
            avg_cpu_percent = summary['avg_cpu_percent']
            
            # For now, use simple standard deviation calculation
            # In a real implementation, you'd want to store individual measurements
            std_dev_execution_time = avg_execution_time * 0.1  # Assume 10% variation
            std_dev_memory_peak = avg_memory_peak * 0.1
            std_dev_cpu_percent = avg_cpu_percent * 0.1
            
            baseline = PerformanceBaseline(
                script_name=script_name,
                catalog_size=catalog_size,
                avg_execution_time=avg_execution_time,
                avg_memory_peak=avg_memory_peak,
                avg_cpu_percent=avg_cpu_percent,
                std_dev_execution_time=std_dev_execution_time,
                std_dev_memory_peak=std_dev_memory_peak,
                std_dev_cpu_percent=std_dev_cpu_percent,
                sample_count=summary['successful_runs'],
                established_at=datetime.now().isoformat(),
                last_updated=datetime.now().isoformat()
            )
            
            if key in self.baselines:
                updated_baselines += 1
            else:
                new_baselines += 1
            
            self.baselines[key] = baseline
        
        # Save baselines
        self._save_baselines()
        
        return {
            "new_baselines": new_baselines,
            "updated_baselines": updated_baselines,
            "total_baselines": len(self.baselines),
            "timestamp": datetime.now().isoformat()
        }
    
    def detect_regressions(self, current_results: List[Dict[str, Any]]) -> List[RegressionAlert]:
        """
        Detect performance regressions by comparing current results to baselines.
        
        Args:
            current_results: Current benchmark results
        
        Returns:
            List of regression alerts
        """
        alerts = []
        
        for result in current_results:
            script_name = result['script_name']
            catalog_size = result['catalog_size']
            key = (script_name, catalog_size)
            
            if key not in self.baselines:
                logger.warning(f"No baseline found for {script_name} (size={catalog_size})")
                continue
            
            baseline = self.baselines[key]
            
            # Check execution time regression
            time_degradation = self._calculate_degradation(
                baseline.avg_execution_time,
                result['avg_execution_time']
            )
            
            if time_degradation > self.threshold:
                alerts.append(RegressionAlert(
                    script_name=script_name,
                    catalog_size=catalog_size,
                    metric_type="execution_time",
                    baseline_value=baseline.avg_execution_time,
                    current_value=result['avg_execution_time'],
                    degradation_percent=time_degradation,
                    severity=self._determine_severity(time_degradation),
                    threshold=self.threshold,
                    timestamp=datetime.now().isoformat(),
                    recommendation=self._get_recommendation("execution_time", time_degradation)
                ))
            
            # Check memory regression
            memory_degradation = self._calculate_degradation(
                baseline.avg_memory_peak,
                result['avg_memory_peak']
            )
            
            if memory_degradation > self.threshold:
                alerts.append(RegressionAlert(
                    script_name=script_name,
                    catalog_size=catalog_size,
                    metric_type="memory_peak",
                    baseline_value=baseline.avg_memory_peak,
                    current_value=result['avg_memory_peak'],
                    degradation_percent=memory_degradation,
                    severity=self._determine_severity(memory_degradation),
                    threshold=self.threshold,
                    timestamp=datetime.now().isoformat(),
                    recommendation=self._get_recommendation("memory_peak", memory_degradation)
                ))
            
            # Check CPU regression
            cpu_degradation = self._calculate_degradation(
                baseline.avg_cpu_percent,
                result['avg_cpu_percent']
            )
            
            if cpu_degradation > self.threshold:
                alerts.append(RegressionAlert(
                    script_name=script_name,
                    catalog_size=catalog_size,
                    metric_type="cpu_percent",
                    baseline_value=baseline.avg_cpu_percent,
                    current_value=result['avg_cpu_percent'],
                    degradation_percent=cpu_degradation,
                    severity=self._determine_severity(cpu_degradation),
                    threshold=self.threshold,
                    timestamp=datetime.now().isoformat(),
                    recommendation=self._get_recommendation("cpu_percent", cpu_degradation)
                ))
        
        logger.info(f"Detected {len(alerts)} performance regressions")
        return alerts
    
    def analyze_trends(self, days: int = 30) -> List[PerformanceTrend]:
        """
        Analyze performance trends over time.
        
        Args:
            days: Number of days to analyze
        
        Returns:
            List of performance trends
        """
        trends = []
        
        try:
            # Group historical data by script and catalog size
            grouped_data = {}
            cutoff_date = datetime.now() - timedelta(days=days)
            
            for data_point in self.historical_data:
                try:
                    data_date = datetime.fromisoformat(data_point['timestamp'].replace('Z', ''))
                    if data_date < cutoff_date:
                        continue
                    
                    key = (data_point['script_name'], data_point['catalog_size'])
                    if key not in grouped_data:
                        grouped_data[key] = []
                    grouped_data[key].append(data_point)
                except:
                    continue
            
            # Analyze trends for each group
            for (script_name, catalog_size), data_points in grouped_data.items():
                if len(data_points) < 3:  # Need at least 3 data points
                    continue
                
                # Sort by timestamp
                data_points.sort(key=lambda x: x['timestamp'])
                
                # Analyze each metric
                for metric in ['avg_execution_time', 'avg_memory_peak', 'avg_cpu_percent']:
                    values = [dp[metric] for dp in data_points if metric in dp]
                    
                    if len(values) >= 3:
                        trend = self._calculate_trend(values)
                        
                        trends.append(PerformanceTrend(
                            script_name=script_name,
                            catalog_size=catalog_size,
                            metric_type=metric,
                            trend_direction=trend['direction'],
                            trend_strength=trend['strength'],
                            recent_values=values[-5:],  # Last 5 values
                            historical_values=values,
                            trend_period_days=days
                        ))
            
            logger.info(f"Analyzed {len(trends)} performance trends")
            return trends
            
        except Exception as e:
            logger.error(f"Failed to analyze trends: {e}")
            return []
    
    def _calculate_degradation(self, baseline: float, current: float) -> float:
        """Calculate performance degradation percentage."""
        if baseline == 0:
            return 0.0
        
        return (current - baseline) / baseline
    
    def _determine_severity(self, degradation: float) -> str:
        """Determine severity of performance degradation."""
        if degradation > 0.5:  # > 50% degradation
            return "critical"
        elif degradation > 0.25:  # > 25% degradation
            return "high"
        elif degradation > 0.1:  # > 10% degradation
            return "medium"
        else:
            return "low"
    
    def _get_recommendation(self, metric_type: str, degradation: float) -> str:
        """Get recommendation for performance regression."""
        if metric_type == "execution_time":
            if degradation > 0.5:
                return "Critical performance regression. Investigate algorithm complexity or I/O bottlenecks."
            elif degradation > 0.25:
                return "Significant performance regression. Profile code and optimize hot paths."
            else:
                return "Minor performance regression. Monitor and consider optimization."
        
        elif metric_type == "memory_peak":
            if degradation > 0.5:
                return "Critical memory regression. Check for memory leaks or inefficient data structures."
            elif degradation > 0.25:
                return "Significant memory regression. Review memory usage patterns and data structures."
            else:
                return "Minor memory regression. Monitor memory usage and consider optimization."
        
        elif metric_type == "cpu_percent":
            if degradation > 0.5:
                return "Critical CPU regression. Investigate CPU-intensive operations and algorithms."
            elif degradation > 0.25:
                return "Significant CPU regression. Profile CPU usage and optimize algorithms."
            else:
                return "Minor CPU regression. Monitor CPU usage and consider optimization."
        
        return "Performance regression detected. Investigate and optimize."
    
    def _calculate_trend(self, values: List[float]) -> Dict[str, Any]:
        """Calculate trend direction and strength."""
        if len(values) < 3:
            return {"direction": "stable", "strength": 0.0}
        
        # Simple linear regression
        n = len(values)
        x = list(range(n))
        
        # Calculate slope
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(xi * xi for xi in x)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        # Determine direction and strength
        if abs(slope) < 0.01:  # Very small slope
            direction = "stable"
            strength = 0.0
        elif slope > 0:
            direction = "degrading"
            strength = min(1.0, abs(slope) * 100)  # Normalize strength
        else:
            direction = "improving"
            strength = min(1.0, abs(slope) * 100)
        
        return {"direction": direction, "strength": strength}
    
    def add_historical_data(self, benchmark_results: List[Dict[str, Any]]):
        """Add benchmark results to historical data."""
        timestamp = datetime.now().isoformat()
        
        for result in benchmark_results:
            data_point = {
                "timestamp": timestamp,
                "script_name": result['script_name'],
                "catalog_size": result['catalog_size'],
                "avg_execution_time": result['avg_execution_time'],
                "avg_memory_peak": result['avg_memory_peak'],
                "avg_cpu_percent": result['avg_cpu_percent'],
                "success_rate": result['success_rate']
            }
            
            self.historical_data.append(data_point)
        
        # Keep only last 1000 data points to prevent file from growing too large
        if len(self.historical_data) > 1000:
            self.historical_data = self.historical_data[-1000:]
        
        # Save updated data
        self._save_baselines()
    
    def generate_report(self, alerts: List[RegressionAlert], trends: List[PerformanceTrend]) -> Dict[str, Any]:
        """Generate comprehensive performance regression report."""
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "threshold": self.threshold,
                "baseline_count": len(self.baselines)
            },
            "alerts": [asdict(alert) for alert in alerts],
            "trends": [asdict(trend) for trend in trends],
            "summary": {
                "total_alerts": len(alerts),
                "critical_alerts": sum(1 for alert in alerts if alert.severity == "critical"),
                "high_alerts": sum(1 for alert in alerts if alert.severity == "high"),
                "medium_alerts": sum(1 for alert in alerts if alert.severity == "medium"),
                "low_alerts": sum(1 for alert in alerts if alert.severity == "low"),
                "trends_analyzed": len(trends),
                "degrading_trends": sum(1 for trend in trends if trend.trend_direction == "degrading"),
                "improving_trends": sum(1 for trend in trends if trend.trend_direction == "improving"),
                "stable_trends": sum(1 for trend in trends if trend.trend_direction == "stable")
            }
        }
    
    def save_report(self, report: Dict[str, Any], output_file: str = None) -> str:
        """Save regression report to file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"tests/performance/regression_report_{timestamp}.json"
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Regression report saved: {output_path}")
        return str(output_path)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Test for performance regressions")
    parser.add_argument(
        "--baseline-file",
        default="tests/performance/baseline.json",
        help="Path to baseline file (default: tests/performance/baseline.json)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
        help="Performance degradation threshold (default: 0.1 = 10%)"
    )
    parser.add_argument(
        "--catalog-sizes",
        type=str,
        default="10,25,50",
        help="Comma-separated list of catalog sizes (default: 10,25,50)"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of iterations per test (default: 3)"
    )
    parser.add_argument(
        "--establish-baseline",
        action="store_true",
        help="Establish new baselines from current run"
    )
    parser.add_argument(
        "--trend-days",
        type=int,
        default=30,
        help="Number of days for trend analysis (default: 30)"
    )
    parser.add_argument(
        "--output-file",
        help="Output file for regression report (default: auto-generated)"
    )
    
    args = parser.parse_args()
    
    try:
        # Parse catalog sizes
        catalog_sizes = [int(size.strip()) for size in args.catalog_sizes.split(",")]
        
        # Initialize regression detector
        detector = PerformanceRegressionDetector(
            baseline_file=args.baseline_file,
            threshold=args.threshold
        )
        
        # Run benchmark suite
        suite = BenchmarkSuite(catalog_sizes=catalog_sizes, iterations=args.iterations)
        results = suite.run_all_benchmarks()
        
        # Generate summary
        summary = suite.generate_summary()
        current_results = summary['summaries']
        
        # Add to historical data
        detector.add_historical_data(current_results)
        
        # Establish baselines if requested
        if args.establish_baseline:
            baseline_report = detector.establish_baseline(current_results)
            print(f"Established {baseline_report['new_baselines']} new baselines, "
                  f"updated {baseline_report['updated_baselines']} existing baselines")
        
        # Detect regressions
        alerts = detector.detect_regressions(current_results)
        
        # Analyze trends
        trends = detector.analyze_trends(args.trend_days)
        
        # Generate report
        report = detector.generate_report(alerts, trends)
        
        # Save report
        output_file = detector.save_report(report, args.output_file)
        
        # Print summary
        print(f"\nPerformance Regression Analysis: {output_file}")
        print(f"Total Alerts: {report['summary']['total_alerts']}")
        print(f"Critical: {report['summary']['critical_alerts']}")
        print(f"High: {report['summary']['high_alerts']}")
        print(f"Medium: {report['summary']['medium_alerts']}")
        print(f"Low: {report['summary']['low_alerts']}")
        
        if report['summary']['total_alerts'] > 0:
            print("\n⚠️  Performance regressions detected!")
            for alert in alerts:
                print(f"  - {alert.script_name} (size={alert.catalog_size}): "
                      f"{alert.metric_type} {alert.degradation_percent:.1%} degradation ({alert.severity})")
        else:
            print("\n✅ No performance regressions detected.")
        
        # Print trends
        if trends:
            print(f"\nTrends Analyzed: {len(trends)}")
            degrading_trends = [t for t in trends if t.trend_direction == "degrading"]
            if degrading_trends:
                print("⚠️  Degrading trends detected:")
                for trend in degrading_trends:
                    print(f"  - {trend.script_name} (size={trend.catalog_size}): "
                          f"{trend.metric_type} ({trend.trend_strength:.1%} strength)")
        
    except Exception as e:
        logger.error(f"Performance regression test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
