#!/usr/bin/env python3
"""
254Carbon Meta Repository - Observability Data Ingestion

Collects SLA/SLO metrics from observability systems (Prometheus/Datadog) and
produces an aggregated snapshot for platform dashboards.

Usage:
    python scripts/ingest_observability.py [--system prometheus] [--config-file FILE]

Design:
- Pluggable client per system with simple query helpers, basic retry, and
  default queries configurable via `config/observability-<system>.yaml`.
- Aggregates per-service metrics, computes global averages/outliers and SLO
  compliance summary.

Outputs:
- Writes a JSON snapshot under `catalog/` and feeds into downstream quality
  and reporting tasks (future integration).
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import our utilities
from scripts.utils.circuit_breaker import observability_circuit_breaker


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/observability-ingestion.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class SLAMetrics:
    """SLA metrics for a service."""
    service_name: str
    availability_percentage: float
    uptime_percentage: float
    downtime_minutes: int
    error_rate_percentage: float
    mean_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    request_throughput: int
    cpu_utilization_percentage: float
    memory_utilization_percentage: float
    slo_compliance_percentage: float


@dataclass
class ObservabilitySnapshot:
    """Complete observability snapshot."""
    metadata: Dict[str, Any]
    services: Dict[str, SLAMetrics]
    global_metrics: Dict[str, Any]
    slo_summary: Dict[str, Any]


class PrometheusClient:
    """Prometheus observability client."""

    def __init__(self, base_url: str, auth_token: str = None):
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.session = requests.Session()

        if auth_token:
            self.session.headers.update({"Authorization": f"Bearer {auth_token}"})

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Initialize circuit breaker for observability system protection
        self.circuit_breaker = observability_circuit_breaker()

    def query(self, query: str, time_range: str = "1h") -> Dict[str, Any]:
        """Execute Prometheus query."""
        def _query_impl():
            url = f"{self.base_url}/api/v1/query"
            params = {"query": query}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()

        return self.circuit_breaker.call(_query_impl)

    def query_range(self, query: str, start_time: datetime, end_time: datetime, step: str = "5m") -> Dict[str, Any]:
        """Execute Prometheus range query."""
        def _query_range_impl():
            url = f"{self.base_url}/api/v1/query_range"
            params = {
                "query": query,
                "start": start_time.timestamp(),
                "end": end_time.timestamp(),
                "step": step
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()

        return self.circuit_breaker.call(_query_range_impl)


class DatadogClient:
    """Datadog observability client."""

    def __init__(self, api_key: str, app_key: str, site: str = "datadoghq.com"):
        self.api_key = api_key
        self.app_key = app_key
        self.base_url = f"https://api.{site}/api/v1"
        self.session = requests.Session()

        self.session.headers.update({
            "DD-API-KEY": api_key,
            "DD-APPLICATION-KEY": app_key,
            "Content-Type": "application/json"
        })

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

        # Initialize circuit breaker for observability system protection
        self.circuit_breaker = observability_circuit_breaker()

    def query_metrics(self, query: str, from_ts: int, to_ts: int) -> Dict[str, Any]:
        """Query Datadog metrics."""
        def _query_metrics_impl():
            url = f"{self.base_url}/query"
            params = {
                "query": query,
                "from": from_ts,
                "to": to_ts
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()

        return self.circuit_breaker.call(_query_metrics_impl)


class ObservabilityIngester:
    """Ingests observability data from various systems."""

    def __init__(self, system: str = "prometheus", config_file: str = None):
        self.system = system
        self.config_file = config_file or f"config/observability-{system}.yaml"

        # Load configuration
        self.config = self._load_config()

        # Initialize client
        self.client = self._initialize_client()

        # Output directory
        self.output_dir = Path("catalog")
        self.output_dir.mkdir(exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Load observability configuration."""
        config_path = Path(self.config_file)

        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return self._get_default_config()

        with open(config_path) as f:
            return yaml.safe_load(f)

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default observability configuration."""
        return {
            'prometheus': {
                'base_url': 'http://localhost:9090',
                'auth_token': None,
                'timeout': 30
            },
            'datadog': {
                'api_key': os.getenv('DD_API_KEY'),
                'app_key': os.getenv('DD_APP_KEY'),
                'site': 'datadoghq.com'
            },
            'metrics': {
                'availability_query': 'up{service="$service"}',
                'latency_query': 'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="$service"}[5m])) * 1000',
                'error_rate_query': 'rate(http_requests_total{service="$service", status=~"5.."}[5m]) / rate(http_requests_total{service="$service"}[5m]) * 100',
                'throughput_query': 'rate(http_requests_total{service="$service"}[5m])',
                'cpu_query': 'rate(container_cpu_usage_seconds_total{pod=~"$service-.*"}[5m]) / rate(container_spec_cpu_quota{pod=~"$service-.*"}[5m]) * 100',
                'memory_query': 'container_memory_usage_bytes{pod=~"$service-.*"} / container_spec_memory_limit_bytes{pod=~"$service-.*"} * 100'
            },
            'slo_config': {
                'availability_target': 99.9,
                'latency_target_p95': 100,  # ms
                'error_rate_target': 0.1   # percentage
            }
        }

    def _initialize_client(self):
        """Initialize observability client."""
        if self.system == 'prometheus':
            config = self.config.get('prometheus', {})
            return PrometheusClient(
                base_url=config['base_url'],
                auth_token=config.get('auth_token')
            )
        elif self.system == 'datadog':
            config = self.config.get('datadog', {})
            return DatadogClient(
                api_key=config['api_key'],
                app_key=config['app_key'],
                site=config.get('site', 'datadoghq.com')
            )
        else:
            raise ValueError(f"Unsupported observability system: {self.system}")

    def _execute_prometheus_query(self, query: str, service_name: str) -> float:
        """Execute Prometheus query for a service."""
        # Replace service placeholder in query
        service_query = query.replace("$service", service_name)

        try:
            response = self.client.query(service_query)

            if response.get('status') == 'success':
                result = response.get('data', {}).get('result', [])
                if result:
                    # Extract numeric value from Prometheus result
                    value = result[0].get('value', [0, '0'])[1]
                    return float(value)

            logger.warning(f"No data for query: {service_query}")
            return 0.0

        except Exception as e:
            logger.error(f"Query failed for {service_name}: {e}")
            return 0.0

    def _execute_datadog_query(self, query: str, service_name: str, from_ts: int, to_ts: int) -> float:
        """Execute Datadog query for a service."""
        # Replace service placeholder in query
        service_query = query.replace("$service", service_name)

        try:
            response = self.client.query_metrics(service_query, from_ts, to_ts)

            if response.get('status') == 'ok':
                series = response.get('series', [])
                if series:
                    # Get latest value from series
                    points = series[0].get('pointlist', [])
                    if points:
                        # Points are [timestamp, value] pairs
                        latest_value = points[-1][1] if len(points[-1]) > 1 else 0
                        return float(latest_value)

            logger.warning(f"No data for query: {service_query}")
            return 0.0

        except Exception as e:
            logger.error(f"Query failed for {service_name}: {e}")
            return 0.0

    def collect_service_metrics(self, service_name: str) -> SLAMetrics:
        """Collect SLA/SLO metrics for a specific service."""
        logger.info(f"Collecting metrics for service: {service_name}")

        metrics_config = self.config.get('metrics', {})
        slo_config = self.config.get('slo_config', {})

        # Define time range (last hour)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)

        if self.system == 'prometheus':
            # Collect Prometheus metrics
            availability = self._execute_prometheus_query(
                metrics_config.get('availability_query', 'up{service="$service"}'),
                service_name
            )

            latency_p95 = self._execute_prometheus_query(
                metrics_config.get('latency_query', 'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="$service"}[5m])) * 1000'),
                service_name
            )

            error_rate = self._execute_prometheus_query(
                metrics_config.get('error_rate_query', 'rate(http_requests_total{service="$service", status=~"5.."}[5m]) / rate(http_requests_total{service="$service"}[5m]) * 100'),
                service_name
            )

            throughput = self._execute_prometheus_query(
                metrics_config.get('throughput_query', 'rate(http_requests_total{service="$service"}[5m])'),
                service_name
            )

            cpu_usage = self._execute_prometheus_query(
                metrics_config.get('cpu_query', 'rate(container_cpu_usage_seconds_total{pod=~"$service-.*"}[5m]) / rate(container_spec_cpu_quota{pod=~"$service-.*"}[5m]) * 100'),
                service_name
            )

            memory_usage = self._execute_prometheus_query(
                metrics_config.get('memory_query', 'container_memory_usage_bytes{pod=~"$service-.*"} / container_spec_memory_limit_bytes{pod=~"$service-.*"} * 100'),
                service_name
            )

        elif self.system == 'datadog':
            # Collect Datadog metrics
            from_ts = int(start_time.timestamp())
            to_ts = int(end_time.timestamp())

            availability = self._execute_datadog_query(
                metrics_config.get('availability_query', 'avg:system.up{service:$service}'),
                service_name, from_ts, to_ts
            )

            latency_p95 = self._execute_datadog_query(
                metrics_config.get('latency_query', 'avg:http.request.duration.p95{service:$service}'),
                service_name, from_ts, to_ts
            )

            error_rate = self._execute_datadog_query(
                metrics_config.get('error_rate_query', 'avg:http.request.error_rate{service:$service} * 100'),
                service_name, from_ts, to_ts
            )

            throughput = self._execute_datadog_query(
                metrics_config.get('throughput_query', 'avg:http.request.throughput{service:$service}'),
                service_name, from_ts, to_ts
            )

            cpu_usage = self._execute_datadog_query(
                metrics_config.get('cpu_query', 'avg:container.cpu.usage{service:$service}'),
                service_name, from_ts, to_ts
            )

            memory_usage = self._execute_datadog_query(
                metrics_config.get('memory_query', 'avg:container.memory.usage{service:$service}'),
                service_name, from_ts, to_ts
            )

        else:
            # Fallback for unsupported systems
            availability = 99.0
            latency_p95 = 50.0
            error_rate = 0.1
            throughput = 100
            cpu_usage = 60.0
            memory_usage = 70.0

        # Calculate derived metrics
        uptime_percentage = availability
        downtime_minutes = int((100 - availability) / 100 * 60)  # Convert to minutes in last hour

        # Calculate SLO compliance
        slo_compliance = self._calculate_slo_compliance(
            availability, latency_p95, error_rate, slo_config
        )

        return SLAMetrics(
            service_name=service_name,
            availability_percentage=availability,
            uptime_percentage=uptime_percentage,
            downtime_minutes=downtime_minutes,
            error_rate_percentage=error_rate,
            mean_latency_ms=latency_p95 * 0.8,  # Estimate mean as 80% of p95
            p95_latency_ms=latency_p95,
            p99_latency_ms=latency_p95 * 1.2,  # Estimate p99 as 120% of p95
            request_throughput=int(throughput),
            cpu_utilization_percentage=cpu_usage,
            memory_utilization_percentage=memory_usage,
            slo_compliance_percentage=slo_compliance
        )

    def _calculate_slo_compliance(self, availability: float, latency_p95: float,
                                error_rate: float, slo_config: Dict[str, Any]) -> float:
        """Calculate overall SLO compliance percentage."""
        availability_target = slo_config.get('availability_target', 99.9)
        latency_target = slo_config.get('latency_target_p95', 100)
        error_rate_target = slo_config.get('error_rate_target', 0.1)

        # Calculate compliance for each SLO
        availability_compliance = min(100, (availability / availability_target) * 100)
        latency_compliance = min(100, (latency_target / latency_p95) * 100) if latency_p95 > 0 else 100
        error_rate_compliance = min(100, ((error_rate_target - error_rate) / error_rate_target) * 100) if error_rate > 0 else 100

        # Average compliance across all SLOs
        return (availability_compliance + latency_compliance + error_rate_compliance) / 3

    def collect_all_service_metrics(self) -> Dict[str, SLAMetrics]:
        """Collect metrics for all services using parallel processing."""
        logger.info("Collecting observability metrics for all services using parallel processing...")

        # Get list of services from catalog
        catalog_path = Path("catalog/service-index.yaml")
        if not catalog_path.exists():
            logger.error("Catalog not found. Run 'make build-catalog' first.")
            return {}

        with open(catalog_path) as f:
            catalog = yaml.safe_load(f)

        services = catalog.get('services', [])
        service_metrics = {}

        logger.info(f"Processing {len(services)} services in parallel...")

        # Use ThreadPoolExecutor for parallel collection
        max_workers = min(len(services), 8)  # Limit to 8 concurrent requests

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all collection tasks
            future_to_service = {
                executor.submit(self.collect_service_metrics, service['name']): service['name']
                for service in services
            }

            # Process results as they complete
            for future in as_completed(future_to_service):
                service_name = future_to_service[future]
                try:
                    metrics = future.result()
                    service_metrics[service_name] = metrics
                    logger.info(f"Collected metrics for {service_name}: {metrics.availability_percentage:.1f}% availability")

                except Exception as e:
                    logger.error(f"Failed to collect metrics for {service_name}: {e}")
                    # Create placeholder metrics for failed services
                    service_metrics[service_name] = SLAMetrics(
                    service_name=service_name,
                    availability_percentage=0.0,
                    uptime_percentage=0.0,
                    downtime_minutes=60,
                    error_rate_percentage=100.0,
                    mean_latency_ms=0.0,
                    p95_latency_ms=0.0,
                    p99_latency_ms=0.0,
                    request_throughput=0,
                    cpu_utilization_percentage=0.0,
                    memory_utilization_percentage=0.0,
                    slo_compliance_percentage=0.0
                )

        logger.info(f"Collected metrics for {len(service_metrics)} services")
        return service_metrics

    def calculate_global_metrics(self, service_metrics: Dict[str, SLAMetrics]) -> Dict[str, Any]:
        """Calculate global observability metrics."""
        if not service_metrics:
            return {}

        # Calculate averages
        avg_availability = sum(m.availability_percentage for m in service_metrics.values()) / len(service_metrics)
        avg_latency = sum(m.p95_latency_ms for m in service_metrics.values()) / len(service_metrics)
        avg_error_rate = sum(m.error_rate_percentage for m in service_metrics.values()) / len(service_metrics)
        avg_slo_compliance = sum(m.slo_compliance_percentage for m in service_metrics.values()) / len(service_metrics)

        # Find outliers
        low_availability = [name for name, m in service_metrics.items() if m.availability_percentage < 99.0]
        high_latency = [name for name, m in service_metrics.items() if m.p95_latency_ms > 200]
        high_error_rate = [name for name, m in service_metrics.items() if m.error_rate_percentage > 1.0]

        return {
            'average_availability': round(avg_availability, 2),
            'average_latency_p95_ms': round(avg_latency, 1),
            'average_error_rate': round(avg_error_rate, 2),
            'average_slo_compliance': round(avg_slo_compliance, 1),
            'services_below_availability_threshold': len(low_availability),
            'services_with_high_latency': len(high_latency),
            'services_with_high_error_rate': len(high_error_rate),
            'outliers': {
                'low_availability': low_availability[:5],  # Top 5
                'high_latency': high_latency[:5],
                'high_error_rate': high_error_rate[:5]
            }
        }

    def generate_slo_summary(self, service_metrics: Dict[str, SLAMetrics]) -> Dict[str, Any]:
        """Generate SLO compliance summary."""
        slo_config = self.config.get('slo_config', {})

        # Count services meeting each SLO
        availability_target = slo_config.get('availability_target', 99.9)
        latency_target = slo_config.get('latency_target_p95', 100)
        error_rate_target = slo_config.get('error_rate_target', 0.1)

        availability_compliant = len([
            m for m in service_metrics.values()
            if m.availability_percentage >= availability_target
        ])

        latency_compliant = len([
            m for m in service_metrics.values()
            if m.p95_latency_ms <= latency_target
        ])

        error_rate_compliant = len([
            m for m in service_metrics.values()
            if m.error_rate_percentage <= error_rate_target
        ])

        overall_compliant = len([
            m for m in service_metrics.values()
            if (m.availability_percentage >= availability_target and
                m.p95_latency_ms <= latency_target and
                m.error_rate_percentage <= error_rate_target)
        ])

        return {
            'slo_targets': {
                'availability': availability_target,
                'latency_p95_ms': latency_target,
                'error_rate_percent': error_rate_target
            },
            'compliance': {
                'availability_compliant': availability_compliant,
                'latency_compliant': latency_compliant,
                'error_rate_compliant': error_rate_compliant,
                'overall_compliant': overall_compliant
            },
            'compliance_percentages': {
                'availability': round(availability_compliant / len(service_metrics) * 100, 1) if service_metrics else 0,
                'latency': round(latency_compliant / len(service_metrics) * 100, 1) if service_metrics else 0,
                'error_rate': round(error_rate_compliant / len(service_metrics) * 100, 1) if service_metrics else 0,
                'overall': round(overall_compliant / len(service_metrics) * 100, 1) if service_metrics else 0
            }
        }

    def generate_observability_snapshot(self) -> ObservabilitySnapshot:
        """Generate complete observability snapshot."""
        logger.info("Generating observability snapshot...")

        # Collect metrics for all services
        service_metrics = self.collect_all_service_metrics()

        # Calculate global metrics
        global_metrics = self.calculate_global_metrics(service_metrics)

        # Generate SLO summary
        slo_summary = self.generate_slo_summary(service_metrics)

        # Create snapshot
        snapshot = ObservabilitySnapshot(
            metadata={
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'system': self.system,
                'total_services': len(service_metrics),
                'collection_window': '1 hour',
                'config_version': '1.0'
            },
            services=service_metrics,
            global_metrics=global_metrics,
            slo_summary=slo_summary
        )

        logger.info("Observability snapshot generated successfully")
        return snapshot

    def save_observability_snapshot(self, snapshot: ObservabilitySnapshot) -> None:
        """Save observability snapshot to file."""
        # Save main snapshot
        snapshot_file = self.output_dir / "observability-snapshot.json"
        snapshot_dict = {
            'metadata': snapshot.metadata,
            'global_metrics': snapshot.global_metrics,
            'slo_summary': snapshot.slo_summary,
            'services': {name: asdict(metrics) for name, metrics in snapshot.services.items()}
        }

        with open(snapshot_file, 'w') as f:
            json.dump(snapshot_dict, f, indent=2)

        logger.info(f"Saved observability snapshot to {snapshot_file}")

        # Save latest for easy access
        latest_file = self.output_dir / "latest_observability_snapshot.json"
        with open(latest_file, 'w') as f:
            json.dump(snapshot_dict, f, indent=2)

        logger.info(f"Updated latest observability snapshot: {latest_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Ingest observability data from monitoring systems")
    parser.add_argument("--system", choices=["prometheus", "datadog"], default="prometheus",
                       help="Observability system to connect to")
    parser.add_argument("--config-file", type=str, help="Path to observability config file")
    parser.add_argument("--service", type=str, help="Specific service to collect metrics for (default: all)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        ingester = ObservabilityIngester(args.system, args.config_file)

        if args.service:
            # Collect metrics for specific service
            metrics = ingester.collect_service_metrics(args.service)
            print(f"Metrics for {args.service}:")
            print(f"  Availability: {metrics.availability_percentage:.2f}%")
            print(f"  Latency (p95): {metrics.p95_latency_ms:.1f}ms")
            print(f"  Error Rate: {metrics.error_rate_percentage:.2f}%")
            print(f"  SLO Compliance: {metrics.slo_compliance_percentage:.1f}%")
        else:
            # Collect metrics for all services
            snapshot = ingester.generate_observability_snapshot()
            ingester.save_observability_snapshot(snapshot)

            # Print summary
            global_metrics = snapshot.global_metrics
            slo_summary = snapshot.slo_summary

            print("\n📊 Observability Summary:")
            print(f"  Services Monitored: {snapshot.metadata['total_services']}")
            print(f"  Avg Availability: {global_metrics.get('average_availability', 0):.2f}%")
            print(f"  Avg Latency (p95): {global_metrics.get('average_latency_p95_ms', 0):.1f}ms")
            print(f"  Avg Error Rate: {global_metrics.get('average_error_rate', 0):.2f}%")
            print(f"  Overall SLO Compliance: {slo_summary.get('compliance_percentages', {}).get('overall', 0):.1f}%")

            if global_metrics.get('services_below_availability_threshold', 0) > 0:
                print(f"  ⚠️ Services Below Availability Threshold: {global_metrics['services_below_availability_threshold']}")

    except Exception as e:
        logger.error(f"Observability ingestion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
