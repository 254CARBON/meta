#!/usr/bin/env python3
"""
Performance Benchmark Suite

Comprehensive performance testing for 254Carbon Meta scripts with various catalog sizes.
Establishes baseline metrics and performance characteristics.

Usage:
    python tests/performance/benchmark_suite.py [--catalog-sizes 10,25,50] [--iterations 3]

Features:
- Multiple catalog sizes (10-50 services)
- Performance metrics collection
- Memory usage tracking
- Execution time measurement
- Baseline establishment
- Performance regression detection
- Report generation
"""

import os
import sys
import json
import time
import psutil
import argparse
import logging
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.build_catalog import CatalogBuilder
from scripts.compute_quality import QualityComputer
from scripts.detect_drift import DriftDetector
from scripts.utils import ExecutionMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('tests/performance/benchmark.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    script_name: str
    catalog_size: int
    iteration: int
    execution_time: float
    memory_peak: float
    memory_avg: float
    cpu_percent: float
    success: bool
    error_message: Optional[str]
    timestamp: str
    metadata: Dict[str, Any]


@dataclass
class BenchmarkSummary:
    """Summary of benchmark results for a script and catalog size."""
    script_name: str
    catalog_size: int
    total_runs: int
    successful_runs: int
    avg_execution_time: float
    min_execution_time: float
    max_execution_time: float
    avg_memory_peak: float
    avg_memory_avg: float
    avg_cpu_percent: float
    success_rate: float
    performance_grade: str


class PerformanceMonitor:
    """Monitor performance metrics during script execution."""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.memory_samples = []
        self.cpu_samples = []
        self.process = None
        self.monitoring_thread = None
        self.monitoring = False
    
    def start_monitoring(self, process_id: int = None):
        """Start monitoring performance metrics."""
        self.start_time = time.time()
        self.memory_samples = []
        self.cpu_samples = []
        
        if process_id:
            self.process = psutil.Process(process_id)
        else:
            self.process = psutil.Process()
        
        self.monitoring = True
        self.monitoring_thread = threading.Thread(target=self._monitor_loop)
        self.monitoring_thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring and calculate final metrics."""
        self.monitoring = False
        if self.monitoring_thread:
            self.monitoring_thread.join()
        
        self.end_time = time.time()
    
    def _monitor_loop(self):
        """Monitoring loop running in separate thread."""
        while self.monitoring:
            try:
                if self.process:
                    memory_info = self.process.memory_info()
                    cpu_percent = self.process.cpu_percent()
                    
                    self.memory_samples.append(memory_info.rss / 1024 / 1024)  # MB
                    self.cpu_samples.append(cpu_percent)
                
                time.sleep(0.1)  # Sample every 100ms
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
    
    def get_metrics(self) -> Dict[str, float]:
        """Get calculated performance metrics."""
        if not self.memory_samples or not self.cpu_samples:
            return {
                "execution_time": 0.0,
                "memory_peak": 0.0,
                "memory_avg": 0.0,
                "cpu_percent": 0.0
            }
        
        execution_time = (self.end_time - self.start_time) if self.end_time and self.start_time else 0.0
        
        return {
            "execution_time": execution_time,
            "memory_peak": max(self.memory_samples),
            "memory_avg": sum(self.memory_samples) / len(self.memory_samples),
            "cpu_percent": sum(self.cpu_samples) / len(self.cpu_samples)
        }


class BenchmarkSuite:
    """Comprehensive performance benchmark suite."""
    
    def __init__(self, catalog_sizes: List[int] = None, iterations: int = 3):
        """
        Initialize benchmark suite.
        
        Args:
            catalog_sizes: List of catalog sizes to test
            iterations: Number of iterations per test
        """
        self.catalog_sizes = catalog_sizes or [10, 25, 50]
        self.iterations = iterations
        self.results: List[BenchmarkResult] = []
        self.temp_dir = None
        
        # Scripts to benchmark
        self.scripts = [
            "build_catalog",
            "compute_quality", 
            "detect_drift"
        ]
        
        logger.info(f"Benchmark suite initialized: sizes={self.catalog_sizes}, iterations={self.iterations}")
    
    def setup_test_environment(self) -> Path:
        """Setup temporary test environment."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="benchmark_"))
        
        # Create necessary directories
        (self.temp_dir / "catalog").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "manifests" / "collected").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "config").mkdir(parents=True, exist_ok=True)
        (self.temp_dir / "analysis" / "reports").mkdir(parents=True, exist_ok=True)
        
        # Copy test fixtures
        fixtures_dir = Path(__file__).parent.parent / "fixtures"
        if fixtures_dir.exists():
            for fixture_file in fixtures_dir.glob("*.json"):
                shutil.copy2(fixture_file, self.temp_dir / "catalog")
            for fixture_file in fixtures_dir.glob("*.yaml"):
                shutil.copy2(fixture_file, self.temp_dir / "manifests" / "collected")
        
        logger.info(f"Test environment setup: {self.temp_dir}")
        return self.temp_dir
    
    def cleanup_test_environment(self):
        """Cleanup temporary test environment."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            logger.info("Test environment cleaned up")
    
    def generate_test_catalog(self, size: int) -> Dict[str, Any]:
        """Generate test catalog with specified number of services."""
        services = {}
        
        for i in range(size):
            service_name = f"service-{i:03d}"
            services[service_name] = {
                "name": service_name,
                "domain": f"domain-{i % 5}",
                "maturity": ["experimental", "stable", "deprecated"][i % 3],
                "repository": f"254carbon/{service_name}",
                "path": ".",
                "api_contracts": [f"{service_name}-core@1.0.0"],
                "dependencies": [f"service-{(i-1) % size:03d}"] if i > 0 else [],
                "quality_hints": {
                    "security_score": 0.8 + (i % 20) * 0.01,
                    "reliability_score": 0.7 + (i % 15) * 0.02,
                    "maintainability_score": 0.75 + (i % 25) * 0.01
                },
                "deployment_info": {
                    "image": f"254carbon/{service_name}:1.0.0",
                    "replicas": 1 + (i % 3),
                    "resources": {
                        "cpu": "100m",
                        "memory": "256Mi"
                    }
                }
            }
        
        catalog = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_services": size,
                "version": "1.0.0"
            },
            "services": services
        }
        
        return catalog
    
    def run_script_benchmark(
        self,
        script_name: str,
        catalog_size: int,
        iteration: int,
        test_dir: Path
    ) -> BenchmarkResult:
        """Run benchmark for a single script."""
        logger.info(f"Running benchmark: {script_name} (size={catalog_size}, iter={iteration})")
        
        monitor = PerformanceMonitor()
        success = True
        error_message = None
        metadata = {}
        
        try:
            # Change to test directory
            original_cwd = os.getcwd()
            os.chdir(test_dir)
            
            # Generate test catalog
            catalog = self.generate_test_catalog(catalog_size)
            
            # Write catalog file
            catalog_file = test_dir / "catalog" / "service-index.json"
            with open(catalog_file, 'w') as f:
                json.dump(catalog, f, indent=2)
            
            # Start monitoring
            monitor.start_monitoring()
            
            # Run script based on type
            if script_name == "build_catalog":
                result = self._benchmark_build_catalog(test_dir, catalog_size)
                metadata = {"services_processed": catalog_size}
            
            elif script_name == "compute_quality":
                result = self._benchmark_compute_quality(test_dir, catalog_size)
                metadata = {"services_processed": catalog_size}
            
            elif script_name == "detect_drift":
                result = self._benchmark_detect_drift(test_dir, catalog_size)
                metadata = {"services_processed": catalog_size}
            
            else:
                raise ValueError(f"Unknown script: {script_name}")
            
            # Stop monitoring
            monitor.stop_monitoring()
            
            # Get metrics
            metrics = monitor.get_metrics()
            
            return BenchmarkResult(
                script_name=script_name,
                catalog_size=catalog_size,
                iteration=iteration,
                execution_time=metrics["execution_time"],
                memory_peak=metrics["memory_peak"],
                memory_avg=metrics["memory_avg"],
                cpu_percent=metrics["cpu_percent"],
                success=success,
                error_message=error_message,
                timestamp=datetime.now().isoformat(),
                metadata=metadata
            )
            
        except Exception as e:
            monitor.stop_monitoring()
            logger.error(f"Benchmark failed: {script_name} (size={catalog_size}, iter={iteration}): {e}")
            
            metrics = monitor.get_metrics()
            
            return BenchmarkResult(
                script_name=script_name,
                catalog_size=catalog_size,
                iteration=iteration,
                execution_time=metrics["execution_time"],
                memory_peak=metrics["memory_peak"],
                memory_avg=metrics["memory_avg"],
                cpu_percent=metrics["cpu_percent"],
                success=False,
                error_message=str(e),
                timestamp=datetime.now().isoformat(),
                metadata={}
            )
        
        finally:
            # Restore original directory
            os.chdir(original_cwd)
    
    def _benchmark_build_catalog(self, test_dir: Path, catalog_size: int) -> Dict[str, Any]:
        """Benchmark catalog building."""
        # Create test manifests
        manifests_dir = test_dir / "manifests" / "collected"
        manifests_dir.mkdir(parents=True, exist_ok=True)
        
        for i in range(catalog_size):
            manifest = {
                "name": f"service-{i:03d}",
                "domain": f"domain-{i % 5}",
                "maturity": ["experimental", "stable", "deprecated"][i % 3],
                "repository": f"254carbon/service-{i:03d}",
                "path": ".",
                "api_contracts": [f"service-{i:03d}-core@1.0.0"]
            }
            
            manifest_file = manifests_dir / f"service-{i:03d}.yaml"
            import yaml
            with open(manifest_file, 'w') as f:
                yaml.dump(manifest, f)
        
        # Run catalog builder
        builder = CatalogBuilder(validate_only=False, force=True)
        result = builder.build_catalog()
        
        return result
    
    def _benchmark_compute_quality(self, test_dir: Path, catalog_size: int) -> Dict[str, Any]:
        """Benchmark quality computation."""
        # Load catalog
        catalog_file = test_dir / "catalog" / "service-index.json"
        with open(catalog_file, 'r') as f:
            catalog = json.load(f)
        
        # Run quality computer
        computer = QualityComputer(catalog)
        result = computer.compute_all_quality_scores_parallel()
        
        return result
    
    def _benchmark_detect_drift(self, test_dir: Path, catalog_size: int) -> Dict[str, Any]:
        """Benchmark drift detection."""
        # Load catalog
        catalog_file = test_dir / "catalog" / "service-index.json"
        with open(catalog_file, 'r') as f:
            catalog = json.load(f)
        
        # Run drift detector
        detector = DriftDetector(catalog)
        result = detector.generate_drift_report()
        
        return result
    
    def run_all_benchmarks(self) -> List[BenchmarkResult]:
        """Run all benchmarks."""
        logger.info("Starting comprehensive benchmark suite")
        
        # Setup test environment
        test_dir = self.setup_test_environment()
        
        try:
            # Run benchmarks for each script and catalog size
            for script_name in self.scripts:
                for catalog_size in self.catalog_sizes:
                    for iteration in range(1, self.iterations + 1):
                        result = self.run_script_benchmark(
                            script_name, catalog_size, iteration, test_dir
                        )
                        self.results.append(result)
                        
                        # Small delay between iterations
                        time.sleep(0.5)
            
            logger.info(f"Benchmark suite completed: {len(self.results)} runs")
            return self.results
            
        finally:
            # Cleanup test environment
            self.cleanup_test_environment()
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate benchmark summary."""
        if not self.results:
            return {"error": "No benchmark results available"}
        
        # Group results by script and catalog size
        grouped_results = {}
        for result in self.results:
            key = (result.script_name, result.catalog_size)
            if key not in grouped_results:
                grouped_results[key] = []
            grouped_results[key].append(result)
        
        # Calculate summaries
        summaries = []
        for (script_name, catalog_size), results in grouped_results.items():
            successful_results = [r for r in results if r.success]
            
            if successful_results:
                execution_times = [r.execution_time for r in successful_results]
                memory_peaks = [r.memory_peak for r in successful_results]
                memory_avgs = [r.memory_avg for r in successful_results]
                cpu_percents = [r.cpu_percent for r in successful_results]
                
                summary = BenchmarkSummary(
                    script_name=script_name,
                    catalog_size=catalog_size,
                    total_runs=len(results),
                    successful_runs=len(successful_results),
                    avg_execution_time=sum(execution_times) / len(execution_times),
                    min_execution_time=min(execution_times),
                    max_execution_time=max(execution_times),
                    avg_memory_peak=sum(memory_peaks) / len(memory_peaks),
                    avg_memory_avg=sum(memory_avgs) / len(memory_avgs),
                    avg_cpu_percent=sum(cpu_percents) / len(cpu_percents),
                    success_rate=len(successful_results) / len(results),
                    performance_grade=self._grade_performance(execution_times, memory_peaks)
                )
                
                summaries.append(summary)
        
        # Overall statistics
        total_runs = len(self.results)
        successful_runs = sum(1 for r in self.results if r.success)
        overall_success_rate = successful_runs / total_runs if total_runs > 0 else 0
        
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_runs": total_runs,
                "successful_runs": successful_runs,
                "overall_success_rate": overall_success_rate,
                "catalog_sizes": self.catalog_sizes,
                "iterations": self.iterations
            },
            "summaries": [asdict(summary) for summary in summaries],
            "raw_results": [asdict(result) for result in self.results]
        }
    
    def _grade_performance(self, execution_times: List[float], memory_peaks: List[float]) -> str:
        """Grade performance based on execution time and memory usage."""
        try:
            avg_time = sum(execution_times) / len(execution_times)
            avg_memory = sum(memory_peaks) / len(memory_peaks)
            
            # Simple grading based on thresholds
            if avg_time < 1.0 and avg_memory < 100:
                return "A"
            elif avg_time < 5.0 and avg_memory < 200:
                return "B"
            elif avg_time < 10.0 and avg_memory < 500:
                return "C"
            else:
                return "D"
                
        except Exception:
            return "F"
    
    def save_results(self, output_file: str = None) -> str:
        """Save benchmark results to file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"tests/performance/benchmark_results_{timestamp}.json"
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        summary = self.generate_summary()
        
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"Benchmark results saved: {output_path}")
        return str(output_path)
    
    def print_summary(self):
        """Print benchmark summary to console."""
        summary = self.generate_summary()
        
        print("\n" + "="*80)
        print("BENCHMARK SUITE RESULTS")
        print("="*80)
        
        print(f"Total Runs: {summary['metadata']['total_runs']}")
        print(f"Successful Runs: {summary['metadata']['successful_runs']}")
        print(f"Overall Success Rate: {summary['metadata']['overall_success_rate']:.1%}")
        print(f"Catalog Sizes: {summary['metadata']['catalog_sizes']}")
        print(f"Iterations: {summary['metadata']['iterations']}")
        
        print("\n" + "-"*80)
        print("PERFORMANCE SUMMARY")
        print("-"*80)
        
        print(f"{'Script':<20} {'Size':<6} {'Success':<8} {'Avg Time':<10} {'Avg Memory':<12} {'Grade':<6}")
        print("-"*80)
        
        for summary_data in summary['summaries']:
            print(f"{summary_data['script_name']:<20} "
                  f"{summary_data['catalog_size']:<6} "
                  f"{summary_data['success_rate']:<8.1%} "
                  f"{summary_data['avg_execution_time']:<10.3f} "
                  f"{summary_data['avg_memory_peak']:<12.1f} "
                  f"{summary_data['performance_grade']:<6}")
        
        print("\n" + "="*80)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Run performance benchmark suite")
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
        "--output-file",
        help="Output file for results (default: auto-generated)"
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print summary to console"
    )
    
    args = parser.parse_args()
    
    try:
        # Parse catalog sizes
        catalog_sizes = [int(size.strip()) for size in args.catalog_sizes.split(",")]
        
        # Initialize benchmark suite
        suite = BenchmarkSuite(catalog_sizes=catalog_sizes, iterations=args.iterations)
        
        # Run benchmarks
        results = suite.run_all_benchmarks()
        
        # Save results
        output_file = suite.save_results(args.output_file)
        
        # Print summary if requested
        if args.print_summary:
            suite.print_summary()
        
        print(f"Benchmark suite completed: {output_file}")
        
        # Check for performance issues
        summary = suite.generate_summary()
        if summary['metadata']['overall_success_rate'] < 0.9:
            print("⚠️  Low success rate detected. Check results for issues.")
        else:
            print("✅ Benchmark suite completed successfully.")
        
    except Exception as e:
        logger.error(f"Benchmark suite failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
