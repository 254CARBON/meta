#!/usr/bin/env python3
"""
254Carbon Meta Repository - Architecture Analysis

Detects architectural anti-patterns and suggests improvements.

Usage:
    python scripts/analyze_architecture.py [--catalog-file FILE] [--output-format json]

Overview:
- Consumes the unified service catalog (YAML/JSON) to construct a directed
  dependency graph (internal dependencies only) and a reverse graph for fan-in.
- Computes coarse architecture metrics per service (fan-in/out, coupling,
  cohesion heuristic, and complexity heuristic) to support rule-of-thumb checks.
- Detects common issues such as cycles, excessive fan-in/out, domain boundary
  violations, and potential "god services" based on combined indicators.
- Produces a structured JSON report with scoring, per-domain health, normalized
  metrics, and suggested refactoring opportunities.

Outputs:
- Writes a timestamped JSON report under `analysis/reports/` and maintains
  `analysis/reports/latest_architecture_health.json` for convenient consumption.
- Console-friendly summary in either JSON or Markdown-style text.

Design notes:
- Heuristics intentionally err on the side of surfacing candidates, not absolute
  truths. Review recommendations with domain context before acting.
- Severity thresholds are tuned for medium-size graphs and can be adjusted when
  integrating with larger platforms.
- External dependencies are not part of graph edges; they influence cohesion
  and complexity heuristics only.
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/architecture-analysis.log')
    ]
)
logger = logging.getLogger(__name__)


class ArchitectureIssueSeverity(Enum):
    """Severity levels for architecture issues."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ArchitectureIssue:
    """Represents an architectural issue."""
    issue_type: str
    severity: ArchitectureIssueSeverity
    service: str
    description: str
    impact: str
    recommendation: str
    affected_services: List[str]
    effort_to_fix: str


@dataclass
class ServiceMetrics:
    """Architecture metrics for a service."""
    name: str
    domain: str
    fan_in: int  # Number of services depending on this
    fan_out: int  # Number of services this depends on
    coupling_score: float
    cohesion_score: float
    complexity_score: float


@dataclass
class ArchitectureHealth:
    """Overall architecture health assessment."""
    overall_score: float
    issues: List[ArchitectureIssue]
    service_metrics: Dict[str, ServiceMetrics]
    recommendations: List[str]
    domain_health: Dict[str, float]


class ArchitectureAnalyzer:
    """Analyzes platform architecture for issues and improvements."""

    def __init__(self, catalog_file: str = None):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.catalog = self._load_catalog()

        # Build dependency graph and metrics
        self.dependency_graph = self._build_dependency_graph()
        self.reverse_graph = self._build_reverse_dependency_graph()
        self.service_metrics = self._calculate_service_metrics()

    def _find_catalog_file(self, catalog_file: str = None) -> Path:
        """Find catalog file."""
        if catalog_file:
            return Path(catalog_file)

        # Default locations
        yaml_path = Path("catalog/service-index.yaml")
        json_path = Path("catalog/service-index.json")

        if yaml_path.exists():
            return yaml_path
        elif json_path.exists():
            return json_path
        else:
            raise FileNotFoundError("No catalog file found. Run 'make build-catalog' first.")

    def _load_catalog(self) -> Dict[str, Any]:
        """Load service catalog."""
        logger.info(f"Loading catalog from {self.catalog_path}")

        with open(self.catalog_path) as f:
            if self.catalog_path.suffix == '.yaml':
                return yaml.safe_load(f)
            else:
                return json.load(f)

    def _build_dependency_graph(self) -> Dict[str, Set[str]]:
        """Build dependency graph (service -> dependencies)."""
        graph = {}

        for service in self.catalog.get('services', []):
            service_name = service['name']
            graph[service_name] = set()

            # Add internal dependencies
            internal_deps = service.get('dependencies', {}).get('internal', [])
            graph[service_name].update(internal_deps)

        return graph

    def _build_reverse_dependency_graph(self) -> Dict[str, Set[str]]:
        """Build reverse dependency graph (service -> dependents)."""
        reverse_graph = defaultdict(set)

        for service, dependencies in self.dependency_graph.items():
            for dependency in dependencies:
                reverse_graph[dependency].add(service)

        return dict(reverse_graph)

    def _calculate_service_metrics(self) -> Dict[str, ServiceMetrics]:
        """Calculate architecture metrics for each service."""
        metrics = {}

        for service in self.catalog.get('services', []):
            service_name = service['name']

            # Calculate fan-in and fan-out
            fan_in = len(self.reverse_graph.get(service_name, set()))
            fan_out = len(self.dependency_graph.get(service_name, set()))

            # Calculate coupling score (0-1, higher = more coupled)
            total_connections = fan_in + fan_out
            max_possible_connections = len(self.catalog.get('services', [])) - 1
            coupling_score = min(1.0, total_connections / max_possible_connections) if max_possible_connections > 0 else 0.0

            # Calculate cohesion score (simplified)
            # Higher cohesion = fewer external dependencies, more focused responsibility
            external_deps = len(service.get('dependencies', {}).get('external', []))
            cohesion_score = max(0.0, 1.0 - (external_deps / 10.0))  # Assume 10+ external deps = low cohesion

            # Calculate complexity score
            # Based on number of dependencies and API contracts
            api_contracts = len(service.get('api_contracts', []))
            events = len(service.get('events_in', [])) + len(service.get('events_out', []))
            complexity_score = min(1.0, (fan_in + fan_out + api_contracts + events) / 20.0)

            metrics[service_name] = ServiceMetrics(
                name=service_name,
                domain=service.get('domain', 'unknown'),
                fan_in=fan_in,
                fan_out=fan_out,
                coupling_score=coupling_score,
                cohesion_score=cohesion_score,
                complexity_score=complexity_score
            )

        return metrics

    def detect_circular_dependencies(self) -> List[ArchitectureIssue]:
        """Detect circular dependencies in the graph."""
        issues = []

        # Use DFS to detect cycles
        visited = set()
        rec_stack = set()

        def has_cycle(node: str, path: List[str] = None) -> Optional[List[str]]:
            if path is None:
                path = []

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.dependency_graph.get(node, set()):
                if neighbor not in visited:
                    cycle = has_cycle(neighbor, path.copy())
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]

            rec_stack.remove(node)
            return None

        for service in self.dependency_graph:
            if service not in visited:
                cycle = has_cycle(service)
                if cycle:
                    issues.append(ArchitectureIssue(
                        issue_type="circular_dependency",
                        severity=ArchitectureIssueSeverity.CRITICAL,
                        service=cycle[0],  # Main service in cycle
                        description=f"Circular dependency detected: {' -> '.join(cycle)}",
                        impact="Prevents proper service startup ordering and creates tight coupling",
                        recommendation="Break cycle by introducing proper abstraction layer or event-driven communication",
                        affected_services=cycle,
                        effort_to_fix="high"
                    ))

        return issues

    def detect_excessive_fan_out(self) -> List[ArchitectureIssue]:
        """Detect services with too many dependencies."""
        issues = []

        for service_name, deps in self.dependency_graph.items():
            if len(deps) > 5:  # Threshold for excessive dependencies
                metrics = self.service_metrics[service_name]

                issues.append(ArchitectureIssue(
                    issue_type="excessive_fan_out",
                    severity=ArchitectureIssueSeverity.HIGH if len(deps) > 8 else ArchitectureIssueSeverity.MEDIUM,
                    service=service_name,
                    description=f"Service depends on {len(deps)} other services",
                    impact="High coupling makes service fragile to changes in dependencies",
                    recommendation="Consider reducing dependencies or introducing facade/abstraction layers",
                    affected_services=list(deps),
                    effort_to_fix="medium"
                ))

        return issues

    def detect_excessive_fan_in(self) -> List[ArchitectureIssue]:
        """Detect services with too many dependents."""
        issues = []

        for service_name, dependents in self.reverse_graph.items():
            if len(dependents) > 5:  # Threshold for excessive dependents
                metrics = self.service_metrics[service_name]

                issues.append(ArchitectureIssue(
                    issue_type="excessive_fan_in",
                    severity=ArchitectureIssueSeverity.HIGH if len(dependents) > 8 else ArchitectureIssueSeverity.MEDIUM,
                    service=service_name,
                    description=f"{len(dependents)} services depend on this service",
                    impact="Changes to this service affect many others, high blast radius",
                    recommendation="Consider splitting into smaller, focused services or adding abstraction layers",
                    affected_services=list(dependents),
                    effort_to_fix="high"
                ))

        return issues

    def detect_domain_pollution(self) -> List[ArchitectureIssue]:
        """Detect services that violate domain boundaries."""
        issues = []

        # Group services by domain
        services_by_domain = defaultdict(list)
        for service in self.catalog.get('services', []):
            domain = service.get('domain', 'unknown')
            services_by_domain[domain].append(service)

        # Check for cross-domain dependencies that shouldn't exist
        forbidden_cross_domain = {
            'access': ['data-processing', 'ml'],  # Access shouldn't depend on processing layers
            'shared': ['access', 'data-processing', 'ml']  # Shared shouldn't depend on domain-specific
        }

        for service in self.catalog.get('services', []):
            service_name = service['name']
            service_domain = service.get('domain', 'unknown')
            dependencies = service.get('dependencies', {}).get('internal', [])

            for dep in dependencies:
                dep_service = next((s for s in self.catalog.get('services', []) if s['name'] == dep), None)
                if dep_service:
                    dep_domain = dep_service.get('domain', 'unknown')

                    # Check if this dependency violates domain rules
                    if (service_domain in forbidden_cross_domain and
                        dep_domain in forbidden_cross_domain[service_domain]):

                        issues.append(ArchitectureIssue(
                            issue_type="domain_pollution",
                            severity=ArchitectureIssueSeverity.HIGH,
                            service=service_name,
                            description=f"Service in {service_domain} domain depends on {dep_domain} domain service",
                            impact="Violates domain boundaries and creates inappropriate coupling",
                            recommendation="Move shared functionality to appropriate domain or use proper abstraction",
                            affected_services=[dep],
                            effort_to_fix="medium"
                        ))

        return issues

    def detect_god_services(self) -> List[ArchitectureIssue]:
        """Detect god services (too many responsibilities)."""
        issues = []

        for service_name, metrics in self.service_metrics.items():
            # God service indicators:
            # - High complexity score
            # - Many API contracts
            # - Many events
            # - High coupling

            service = next(s for s in self.catalog.get('services', []) if s['name'] == service_name)
            api_contracts = len(service.get('api_contracts', []))
            events = len(service.get('events_in', [])) + len(service.get('events_out', []))

            # Heuristic for god service detection
            god_score = (
                metrics.complexity_score * 0.3 +
                (api_contracts / 10.0) * 0.3 +  # Normalize to 0-1
                (events / 15.0) * 0.2 +         # Normalize to 0-1
                metrics.coupling_score * 0.2
            )

            if god_score > 0.7:
                issues.append(ArchitectureIssue(
                    issue_type="god_service",
                    severity=ArchitectureIssueSeverity.HIGH,
                    service=service_name,
                    description=f"Service has {api_contracts} API contracts and {events} events - potential god service",
                    impact="Single point of failure, difficult to maintain and test",
                    recommendation="Consider splitting into smaller, focused services",
                    affected_services=[service_name],
                    effort_to_fix="high"
                ))

        return issues

    def detect_data_coupling(self) -> List[ArchitectureIssue]:
        """Detect inappropriate data coupling."""
        issues = []

        # Look for services sharing external data dependencies
        external_deps_by_service = {}
        for service in self.catalog.get('services', []):
            service_name = service['name']
            external_deps = service.get('dependencies', {}).get('external', [])
            external_deps_by_service[service_name] = set(external_deps)

        # Find services sharing data dependencies inappropriately
        shared_external_deps = defaultdict(list)

        for service, deps in external_deps_by_service.items():
            for dep in deps:
                shared_external_deps[dep].append(service)

        # Flag shared data dependencies across different domains
        for dep, services in shared_external_deps.items():
            if len(services) > 2:  # More than 2 services sharing same data
                service_domains = set()
                for service_name in services:
                    service = next(s for s in self.catalog.get('services', []) if s['name'] == service_name)
                    service_domains.add(service.get('domain', 'unknown'))

                if len(service_domains) > 1:  # Cross-domain sharing
                    issues.append(ArchitectureIssue(
                        issue_type="data_coupling",
                        severity=ArchitectureIssueSeverity.MEDIUM,
                        service=services[0],  # Representative service
                        description=f"{len(services)} services share {dep} across {len(service_domains)} domains",
                        impact="Tight coupling through shared data dependencies",
                        recommendation="Consider introducing data abstraction layer or event-driven communication",
                        affected_services=services,
                        effort_to_fix="medium"
                    ))

        return issues

    def analyze_architecture_health(self) -> ArchitectureHealth:
        """Analyze overall architecture health."""
        logger.info("Analyzing architecture health...")

        # Detect all types of issues
        all_issues = []
        all_issues.extend(self.detect_circular_dependencies())
        all_issues.extend(self.detect_excessive_fan_out())
        all_issues.extend(self.detect_excessive_fan_in())
        all_issues.extend(self.detect_domain_pollution())
        all_issues.extend(self.detect_god_services())
        all_issues.extend(self.detect_data_coupling())

        # Calculate overall score (0-100, higher is better)
        base_score = 100

        # Deduct points for issues
        critical_issues = len([i for i in all_issues if i.severity == ArchitectureIssueSeverity.CRITICAL])
        high_issues = len([i for i in all_issues if i.severity == ArchitectureIssueSeverity.HIGH])
        medium_issues = len([i for i in all_issues if i.severity == ArchitectureIssueSeverity.MEDIUM])

        score_deduction = (critical_issues * 20) + (high_issues * 10) + (medium_issues * 5)
        overall_score = max(0, base_score - score_deduction)

        # Generate recommendations
        recommendations = self._generate_architecture_recommendations(all_issues)

        # Calculate domain health
        domain_health = self._calculate_domain_health()

        return ArchitectureHealth(
            overall_score=overall_score,
            issues=all_issues,
            service_metrics=self.service_metrics,
            recommendations=recommendations,
            domain_health=domain_health
        )

    def _generate_architecture_recommendations(self, issues: List[ArchitectureIssue]) -> List[str]:
        """Generate architecture improvement recommendations."""
        recommendations = []

        if not issues:
            recommendations.append("✅ Architecture is healthy - no major issues detected")
            return recommendations

        # Group issues by type
        issues_by_type = defaultdict(list)
        for issue in issues:
            issues_by_type[issue.issue_type].append(issue)

        # Generate recommendations for each issue type
        if issues_by_type.get('circular_dependency'):
            recommendations.append(f"🚨 Critical: Resolve {len(issues_by_type['circular_dependency'])} circular dependencies immediately")

        if issues_by_type.get('excessive_fan_out'):
            recommendations.append(f"🔶 High: Reduce coupling in {len(issues_by_type['excessive_fan_out'])} services with too many dependencies")

        if issues_by_type.get('excessive_fan_in'):
            recommendations.append(f"🔶 High: Split or abstract {len(issues_by_type['excessive_fan_in'])} god services")

        if issues_by_type.get('domain_pollution'):
            recommendations.append(f"🔶 High: Fix {len(issues_by_type['domain_pollution'])} domain boundary violations")

        if issues_by_type.get('god_service'):
            recommendations.append(f"🟠 Medium: Consider splitting {len(issues_by_type['god_service'])} god services")

        if issues_by_type.get('data_coupling'):
            recommendations.append(f"🟡 Low: Address {len(issues_by_type['data_coupling'])} data coupling issues")

        # General recommendations
        if len(issues) > 10:
            recommendations.append("📋 General: Schedule regular architecture reviews to prevent issue accumulation")

        return recommendations

    def _calculate_domain_health(self) -> Dict[str, float]:
        """Calculate health score for each domain."""
        domain_health = {}

        # Group services by domain
        services_by_domain = defaultdict(list)
        for service in self.catalog.get('services', []):
            domain = service.get('domain', 'unknown')
            services_by_domain[domain].append(service)

        # Calculate health for each domain
        for domain, services in services_by_domain.items():
            if not services:
                continue

            # Average quality score for domain
            avg_quality = sum(s.get('quality', {}).get('score', 50) for s in services) / len(services)

            # Count issues in domain
            domain_issues = [
                issue for issue in self.analyze_architecture_health().issues
                if any(s['name'] == issue.service for s in services)
            ]

            issue_penalty = len(domain_issues) * 5
            domain_score = max(0, avg_quality - issue_penalty)

            domain_health[domain] = round(domain_score, 1)

        return domain_health

    def suggest_refactoring_opportunities(self) -> List[Dict[str, Any]]:
        """Suggest specific refactoring opportunities."""
        suggestions = []

        # Service splitting opportunities
        for service_name, metrics in self.service_metrics.items():
            if metrics.complexity_score > 0.7 or metrics.fan_in > 3:
                suggestions.append({
                    'type': 'service_splitting',
                    'service': service_name,
                    'priority': 'high' if metrics.complexity_score > 0.8 else 'medium',
                    'description': f"Split {service_name} - high complexity ({metrics.complexity_score:.2f}) and coupling",
                    'estimated_effort': 'high',
                    'expected_benefit': 'Improved maintainability and reduced blast radius'
                })

        # Dependency reduction opportunities
        for service_name, deps in self.dependency_graph.items():
            if len(deps) > 6:
                suggestions.append({
                    'type': 'dependency_reduction',
                    'service': service_name,
                    'priority': 'medium',
                    'description': f"Reduce dependencies for {service_name} ({len(deps)} dependencies)",
                    'estimated_effort': 'medium',
                    'expected_benefit': 'Reduced coupling and faster builds'
                })

        # Domain boundary improvements
        domain_issues = [i for i in self.analyze_architecture_health().issues if i.issue_type == 'domain_pollution']
        if domain_issues:
            suggestions.append({
                'type': 'domain_realignment',
                'service': 'multiple',
                'priority': 'high',
                'description': f"Fix {len(domain_issues)} domain boundary violations",
                'estimated_effort': 'medium',
                'expected_benefit': 'Cleaner domain separation and better modularity'
            })

        return suggestions

    def save_architecture_report(self, health: ArchitectureHealth) -> None:
        """Save architecture analysis to file."""
        reports_dir = Path("analysis/reports/architecture")
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"architecture_health_{timestamp}.json"

        report_dict = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'total_services': len(self.service_metrics),
                'total_domains': len(set(s.domain for s in self.service_metrics.values())),
                'analysis_version': '1.0'
            },
            'overall_health': {
                'score': health.overall_score,
                'grade': self._get_health_grade(health.overall_score),
                'total_issues': len(health.issues)
            },
            'issues_by_severity': {
                'critical': len([i for i in health.issues if i.severity == ArchitectureIssueSeverity.CRITICAL]),
                'high': len([i for i in health.issues if i.severity == ArchitectureIssueSeverity.HIGH]),
                'medium': len([i for i in health.issues if i.severity == ArchitectureIssueSeverity.MEDIUM]),
                'low': len([i for i in health.issues if i.severity == ArchitectureIssueSeverity.LOW])
            },
            'issues': [asdict(issue) for issue in health.issues],
            'service_metrics': {name: asdict(metrics) for name, metrics in health.service_metrics.items()},
            'domain_health': health.domain_health,
            'recommendations': health.recommendations,
            'refactoring_suggestions': self.suggest_refactoring_opportunities()
        }

        with open(report_file, 'w') as f:
            json.dump(report_dict, f, indent=2)

        logger.info(f"Saved architecture analysis to {report_file}")

        # Update latest report
        latest_file = reports_dir / "latest_architecture_health.json"
        with open(latest_file, 'w') as f:
            json.dump(report_dict, f, indent=2)

    def _get_health_grade(self, score: float) -> str:
        """Convert health score to letter grade."""
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze platform architecture for issues and improvements")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file")
    parser.add_argument("--output-format", choices=["json", "markdown"], default="markdown",
                       help="Output format (default: markdown)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        analyzer = ArchitectureAnalyzer(args.catalog_file)
        health = analyzer.analyze_architecture_health()
        analyzer.save_architecture_report(health)

        if args.output_format == "json":
            # Output as JSON
            report_dict = {
                'metadata': {
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'total_services': len(analyzer.service_metrics),
                    'total_domains': len(set(s.domain for s in analyzer.service_metrics.values())),
                },
                'overall_health': {
                    'score': health.overall_score,
                    'grade': analyzer._get_health_grade(health.overall_score),
                    'total_issues': len(health.issues)
                },
                'issues': [asdict(issue) for issue in health.issues],
                'service_metrics': {name: asdict(metrics) for name, metrics in health.service_metrics.items()},
                'domain_health': health.domain_health,
                'recommendations': health.recommendations,
                'refactoring_suggestions': analyzer.suggest_refactoring_opportunities()
            }

            print(json.dumps(report_dict, indent=2))
        else:
            # Output as markdown
            print("\n🏗️ Architecture Health Report:")
            print(f"  Overall Score: {health.overall_score}/100 ({analyzer._get_health_grade(health.overall_score)})")
            print(f"  Total Issues: {len(health.issues)}")

            if health.issues:
                print("\n🚨 Critical Issues:")
                for issue in health.issues[:5]:
                    if issue.severity == ArchitectureIssueSeverity.CRITICAL:
                        print(f"  • {issue.service}: {issue.description}")

            print("\n📊 Domain Health:")
            for domain, score in health.domain_health.items():
                print(f"  • {domain.title()}: {score}/100")

            print("\n🎯 Top Recommendations:")
            for rec in health.recommendations[:5]:
                print(f"  • {rec}")

            print("\n🔧 Refactoring Opportunities:")
            for suggestion in analyzer.suggest_refactoring_opportunities()[:3]:
                print(f"  • {suggestion['type'].replace('_', ' ').title()}: {suggestion['description']}")

    except Exception as e:
        logger.error(f"Architecture analysis failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
