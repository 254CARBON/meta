#!/usr/bin/env python3
"""
254Carbon Meta Repository - Change Impact Analysis

Analyzes the impact of proposed changes across the platform by inspecting PR
diffs, catalog relationships, and signal data (drift/quality).

Usage:
    python scripts/analyze_impact.py --pr 123 [--github-token TOKEN]

Approach:
- Pulls changed files for a PR, classifies change types (manifest, API, event,
  dependency), and identifies the primarily affected service.
- Traverses the internal dependency graph to find direct/transitive consumers
  and domain peers; considers shared contracts for broader contract impact.
- Summarizes blast radius, severity, testing scope, rollback, and comms plan.

Outputs:
- Writes a structured JSON report under `analysis/reports/impact/` and a
  `*_latest_impact.json` pointer for quick reference.
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
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/impact-analysis.log')
    ]
)
logger = logging.getLogger(__name__)


class ImpactSeverity(Enum):
    """Impact severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ImpactedService:
    """Represents a service impacted by a change."""
    name: str
    domain: str
    impact_type: str  # 'direct', 'transitive', 'domain', 'contract', 'data'
    impact_reason: str
    risk_level: str
    estimated_effort: str
    testing_required: bool
    rollback_complexity: str


@dataclass
class ChangeImpact:
    """Complete impact analysis for a change."""
    change_id: str
    change_type: str
    changed_service: str
    changed_files: List[str]
    impacted_services: List[ImpactedService]
    blast_radius: int
    overall_severity: ImpactSeverity
    risk_assessment: str
    testing_scope: List[str]
    rollback_plan: Dict[str, Any]
    communication_plan: Dict[str, Any]


class GitHubAPI:
    """GitHub API client for PR analysis."""

    def __init__(self, token: str, repo_owner: str = "254carbon", repo_name: str = "254carbon-meta"):
        self.token = token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "254Carbon-Meta/1.0"
        })

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def get_pr_details(self, pr_number: int) -> Dict[str, Any]:
        """Get PR details including files changed."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_number}"

        response = self.session.get(url)
        response.raise_for_status()

        pr_data = response.json()

        # Get files changed
        files_url = pr_data.get('url', '').replace('/pulls/', '/pulls/') + '/files'
        files_response = self.session.get(files_url)
        files_response.raise_for_status()

        pr_data['files'] = files_response.json()

        return pr_data

    def get_pr_commits(self, pr_number: int) -> List[Dict[str, Any]]:
        """Get commits in a PR."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_number}/commits"

        response = self.session.get(url)
        response.raise_for_status()

        return response.json()


class ImpactAnalyzer:
    """Analyzes change impact across the platform."""

    def __init__(self, catalog_file: str = None, drift_file: str = None, quality_file: str = None):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.drift_file = drift_file or "catalog/latest_drift_report.json"
        self.quality_file = quality_file or "catalog/latest_quality_snapshot.json"

        # Load data sources
        self.catalog = self._load_catalog()
        self.drift_data = self._load_drift_data()
        self.quality_data = self._load_quality_data()

        # Build dependency graph
        self.dependency_graph = self._build_dependency_graph()

        # Build service index for quick lookup
        self.services_by_name = {s['name']: s for s in self.catalog.get('services', [])}

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

    def _load_drift_data(self) -> Dict[str, Any]:
        """Load drift report data."""
        drift_path = Path(self.drift_file)

        if not drift_path.exists():
            logger.warning(f"Drift file not found: {drift_path}")
            return {}

        try:
            with open(drift_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load drift data: {e}")
            return {}

    def _load_quality_data(self) -> Dict[str, Any]:
        """Load quality snapshot data."""
        quality_path = Path(self.quality_file)

        if not quality_path.exists():
            logger.warning(f"Quality file not found: {quality_path}")
            return {}

        try:
            with open(quality_path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load quality data: {e}")
            return {}

    def _build_dependency_graph(self) -> Dict[str, Set[str]]:
        """Build dependency graph for impact analysis."""
        graph = {}

        for service in self.catalog.get('services', []):
            service_name = service['name']
            graph[service_name] = set()

            # Add internal dependencies
            internal_deps = service.get('dependencies', {}).get('internal', [])
            graph[service_name].update(internal_deps)

            # Add external dependencies (for data flow analysis)
            external_deps = service.get('dependencies', {}).get('external', [])
            # External deps don't create service dependencies but may affect data flow

        return graph

    def analyze_pr_impact(self, pr_number: int, github_token: str) -> ChangeImpact:
        """Analyze impact of a GitHub PR.

        Pulls PR metadata and changed files, infers the primarily affected
        service and change type, and computes a structured impact assessment
        across direct, transitive, domain, and contract dimensions.

        Args:
            pr_number: The pull request number to analyze.
            github_token: Token used to access GitHub API.

        Returns:
            A populated `ChangeImpact` including blast radius, severity,
            testing scope, rollback plan, and communication plan.

        Raises:
            ValueError: If an affected service cannot be determined.
        """
        logger.info(f"Analyzing impact of PR #{pr_number}")

        # Get PR details
        github_api = GitHubAPI(github_token)
        pr_data = github_api.get_pr_details(pr_number)

        # Determine changed service and change type
        changed_service, change_type = self._analyze_pr_changes(pr_data)

        if not changed_service:
            raise ValueError(f"Could not determine changed service for PR #{pr_number}")

        # Find all impacted services
        impacted_services = self._find_impacted_services(changed_service, change_type, pr_data)

        # Calculate blast radius
        blast_radius = len(impacted_services)

        # Assess overall severity
        overall_severity = self._assess_overall_severity(impacted_services, change_type)

        # Generate testing scope
        testing_scope = self._generate_testing_scope(impacted_services, change_type)

        # Generate rollback plan
        rollback_plan = self._generate_rollback_plan(changed_service, impacted_services)

        # Generate communication plan
        communication_plan = self._generate_communication_plan(changed_service, impacted_services, overall_severity)

        return ChangeImpact(
            change_id=f"pr-{pr_number}",
            change_type=change_type,
            changed_service=changed_service,
            changed_files=[f['filename'] for f in pr_data.get('files', [])],
            impacted_services=impacted_services,
            blast_radius=blast_radius,
            overall_severity=overall_severity,
            risk_assessment=self._assess_risk_summary(impacted_services, change_type),
            testing_scope=testing_scope,
            rollback_plan=rollback_plan,
            communication_plan=communication_plan
        )

    def _analyze_pr_changes(self, pr_data: Dict[str, Any]) -> Tuple[Optional[str], str]:
        """Analyze PR to determine changed service and change type.

        Heuristically inspects file paths to infer the service being changed
        and categorizes the change (manifest, API contract, event schema,
        dependency, other).

        Args:
            pr_data: Raw PR JSON from GitHub including `files` array.

        Returns:
            Tuple of (changed_service, change_type). `changed_service` may be
            None if detection fails; `change_type` defaults to 'other'.
        """
        files = pr_data.get('files', [])

        # Look for service-specific files
        service_manifests = [f for f in files if 'service-manifest.yaml' in f['filename']]
        api_contracts = [f for f in files if any(pattern in f['filename'] for pattern in ['api', 'contract', 'spec'])]
        event_schemas = [f for f in files if 'event' in f['filename'].lower()]
        dependency_files = [f for f in files if any(pattern in f['filename'] for pattern in ['package.json', 'requirements.txt', 'go.mod'])]

        # Determine primary change type
        if service_manifests:
            change_type = "service_manifest"
        elif api_contracts:
            change_type = "api_contract"
        elif event_schemas:
            change_type = "event_schema"
        elif dependency_files:
            change_type = "dependency"
        else:
            change_type = "other"

        # Try to determine changed service from file paths
        changed_service = None

        for file_info in files:
            filename = file_info['filename']

            # Look for service-specific patterns
            if 'service-manifest.yaml' in filename:
                # Extract service name from path
                path_parts = filename.split('/')
                if len(path_parts) >= 2:
                    changed_service = path_parts[-2]  # Assume service-name/service-manifest.yaml

            # Look for API contract patterns
            if any(pattern in filename for pattern in ['api', 'contract']):
                # Try to extract service name from API file path
                path_parts = filename.split('/')
                if len(path_parts) >= 2:
                    changed_service = path_parts[-2]

        return changed_service, change_type

    def _find_impacted_services(self, changed_service: str, change_type: str, pr_data: Dict[str, Any]) -> List[ImpactedService]:
        """Find all services impacted by the change.

        Aggregates direct, transitive, domain, and contract-based impacts,
        deduplicating results with a stable priority ordering.

        Args:
            changed_service: The primary service affected by the PR.
            change_type: Classification of the PR change.
            pr_data: Raw PR JSON from GitHub.

        Returns:
            Ordered list of unique `ImpactedService` entries.
        """
        impacted = []

        # Direct dependencies (services that depend on changed service)
        direct_impact = self._find_direct_impact(changed_service)
        impacted.extend(direct_impact)

        # Transitive dependencies (dependencies of dependencies)
        transitive_impact = self._find_transitive_impact(changed_service, direct_impact)
        impacted.extend(transitive_impact)

        # Domain impact (all services in same domain)
        domain_impact = self._find_domain_impact(changed_service)
        impacted.extend(domain_impact)

        # Contract impact (services using same APIs/events)
        contract_impact = self._find_contract_impact(changed_service, change_type)
        impacted.extend(contract_impact)

        # Remove duplicates and sort by impact type priority
        seen = set()
        unique_impacted = []

        impact_priority = {'direct': 0, 'contract': 1, 'domain': 2, 'transitive': 3}

        for service in sorted(impacted, key=lambda x: impact_priority.get(x.impact_type, 999)):
            if service.name not in seen:
                unique_impacted.append(service)
                seen.add(service.name)

        return unique_impacted

    def _find_direct_impact(self, changed_service: str) -> List[ImpactedService]:
        """Find services directly depending on changed service.

        Returns services whose internal dependency list includes the changed
        service, excluding self-dependencies.

        Args:
            changed_service: Service whose consumers should be identified.

        Returns:
            List of `ImpactedService` with impact_type='direct'.
        """
        impacted = []

        for service_name, dependencies in self.dependency_graph.items():
            if changed_service in dependencies and service_name != changed_service:
                service = self.services_by_name.get(service_name)
                if service:
                    risk_level = self._get_service_risk_level(service_name)

                    impacted.append(ImpactedService(
                        name=service_name,
                        domain=service.get('domain', 'unknown'),
                        impact_type='direct',
                        impact_reason=f"Directly depends on {changed_service}",
                        risk_level=risk_level,
                        estimated_effort='medium',
                        testing_required=True,
                        rollback_complexity='medium'
                    ))

        return impacted

    def _find_transitive_impact(self, changed_service: str, direct_impact: List[ImpactedService]) -> List[ImpactedService]:
        """Find services transitively impacted.

        Identifies services that depend on any directly impacted service but
        are not themselves directly impacted by the change.

        Args:
            changed_service: Primary service being modified.
            direct_impact: Previously computed direct impact list.

        Returns:
            List of `ImpactedService` with impact_type='transitive'.
        """
        impacted = []

        # Get services that depend on directly impacted services
        direct_names = {s.name for s in direct_impact}

        for service_name, dependencies in self.dependency_graph.items():
            if (service_name not in direct_names and
                changed_service not in dependencies and
                any(dep in direct_names for dep in dependencies)):

                service = self.services_by_name.get(service_name)
                if service:
                    impacted.append(ImpactedService(
                        name=service_name,
                        domain=service.get('domain', 'unknown'),
                        impact_type='transitive',
                        impact_reason=f"Depends on services impacted by {changed_service}",
                        risk_level='low',
                        estimated_effort='low',
                        testing_required=False,
                        rollback_complexity='low'
                    ))

        return impacted

    def _find_domain_impact(self, changed_service: str) -> List[ImpactedService]:
        """Find all services in the same domain.

        Args:
            changed_service: Primary service being modified.

        Returns:
            List of `ImpactedService` in the same domain, excluding the changed service.
        """
        impacted = []

        changed_service_data = self.services_by_name.get(changed_service)
        if not changed_service_data:
            return impacted

        changed_domain = changed_service_data.get('domain')

        for service_name, service in self.services_by_name.items():
            if (service_name != changed_service and
                service.get('domain') == changed_domain):

                risk_level = self._get_service_risk_level(service_name)

                impacted.append(ImpactedService(
                    name=service_name,
                    domain=changed_domain,
                    impact_type='domain',
                    impact_reason=f"Same domain as {changed_service}",
                    risk_level=risk_level,
                    estimated_effort='low',
                    testing_required=False,
                    rollback_complexity='low'
                ))

        return impacted

    def _find_contract_impact(self, changed_service: str, change_type: str) -> List[ImpactedService]:
        """Find services impacted by contract changes.

        If the PR concerns API/contracts, identify consumer services likely
        to be affected based on shared contract names.

        Args:
            changed_service: Primary service being modified.
            change_type: Classification of the PR change.

        Returns:
            List of `ImpactedService` with impact_type='contract'.
        """
        impacted = []

        # If it's an API contract change, find all consumers
        if 'api' in change_type.lower() or 'contract' in change_type.lower():
            changed_service_data = self.services_by_name.get(changed_service)
            if changed_service_data:
                api_contracts = changed_service_data.get('api_contracts', [])

                for contract in api_contracts:
                    if '@' in contract:
                        contract_name = contract.split('@')[0]

                        # Find all services that use this contract
                        for service_name, service in self.services_by_name.items():
                            if (service_name != changed_service and
                                contract_name in str(service.get('dependencies', {}).get('external', []))):

                                risk_level = self._get_service_risk_level(service_name)

                                impacted.append(ImpactedService(
                                    name=service_name,
                                    domain=service.get('domain', 'unknown'),
                                    impact_type='contract',
                                    impact_reason=f"Uses {contract_name} contract from {changed_service}",
                                    risk_level=risk_level,
                                    estimated_effort='high',
                                    testing_required=True,
                                    rollback_complexity='high'
                                ))

        return impacted

    def _get_service_risk_level(self, service_name: str) -> str:
        """Get risk level for a service."""
        service = self.services_by_name.get(service_name)
        if not service:
            return 'medium'

        # Base risk on quality score
        quality_score = service.get('quality', {}).get('score', 75)

        if quality_score >= 90:
            return 'low'
        elif quality_score >= 75:
            return 'medium'
        else:
            return 'high'

    def _assess_overall_severity(self, impacted_services: List[ImpactedService], change_type: str) -> ImpactSeverity:
        """Assess overall change severity.

        Simple heuristic combining blast radius and change type to map to an
        `ImpactSeverity` classification.

        Args:
            impacted_services: List of impacted services across categories.
            change_type: Classification of the PR change.

        Returns:
            `ImpactSeverity` value (LOW, MEDIUM, HIGH, CRITICAL).
        """
        if not impacted_services:
            return ImpactSeverity.LOW

        # Count high-risk impacted services
        high_risk_count = len([s for s in impacted_services if s.risk_level == 'high'])

        # Count critical impact types
        critical_impacts = len([s for s in impacted_services if s.impact_type in ['direct', 'contract']])

        if high_risk_count >= 3 or critical_impacts >= 5:
            return ImpactSeverity.CRITICAL
        elif high_risk_count >= 2 or critical_impacts >= 3:
            return ImpactSeverity.HIGH
        elif len(impacted_services) >= 5:
            return ImpactSeverity.MEDIUM
        else:
            return ImpactSeverity.LOW

    def _generate_testing_scope(self, impacted_services: List[ImpactedService], change_type: str) -> List[str]:
        """Generate recommended testing scope.

        Args:
            impacted_services: Impact list to drive test selection.
            change_type: Classification of the PR change.

        Returns:
            Ordered list of suggested test categories to run.
        """
        testing = []

        # Base testing requirements
        testing.append(f"Unit tests for {len(impacted_services)} impacted services")

        # Direct impact testing
        direct_services = [s for s in impacted_services if s.impact_type == 'direct']
        if direct_services:
            testing.append(f"Integration tests for {len(direct_services)} directly impacted services")

        # Contract testing
        contract_services = [s for s in impacted_services if s.impact_type == 'contract']
        if contract_services:
            testing.append(f"Contract/API tests for {len(contract_services)} affected consumers")

        # Domain testing
        if len(set(s.domain for s in impacted_services)) > 1:
            testing.append("Cross-domain integration tests")

        # Performance testing for certain change types
        if 'performance' in change_type.lower() or 'latency' in change_type.lower():
            testing.append("Performance regression tests")

        return testing

    def _generate_rollback_plan(self, changed_service: str, impacted_services: List[ImpactedService]) -> Dict[str, Any]:
        """Generate rollback plan.

        Args:
            changed_service: Service being modified.
            impacted_services: Top impacted services to verify during rollback.

        Returns:
            Dictionary describing the rollback strategy and steps.
        """
        return {
            'strategy': 'Automated rollback with manual verification',
            'steps': [
                f"Revert changes to {changed_service}",
                "Deploy previous version",
                "Verify impacted services: {', '.join([s.name for s in impacted_services[:3]])}",
                "Run smoke tests",
                "Monitor for 30 minutes"
            ],
            'estimated_time': '45 minutes',
            'automation_possible': True,
            'verification_required': True
        }

    def _generate_communication_plan(self, changed_service: str, impacted_services: List[ImpactedService],
                                   severity: ImpactSeverity) -> Dict[str, Any]:
        """Generate communication plan.

        Args:
            changed_service: Service being modified.
            impacted_services: Impacted services to derive stakeholders.
            severity: Overall impact severity.

        Returns:
            A communication plan with stakeholders, channels, and timeline.
        """
        stakeholders = set()

        # Add service owners
        for service in impacted_services[:5]:  # Limit to avoid spam
            stakeholders.add(f"owner-{service.name}")

        # Add domain stakeholders
        domains = set(s.domain for s in impacted_services)
        for domain in domains:
            stakeholders.add(f"{domain}-team")

        # Add platform team for significant changes
        if severity in [ImpactSeverity.HIGH, ImpactSeverity.CRITICAL]:
            stakeholders.add("platform-team")

        return {
            'stakeholders': list(stakeholders),
            'notification_channels': ['Slack #platform-changes'],
            'urgency': severity.value,
            'communication_timeline': [
                'Pre-deployment: Notify stakeholders',
                'During deployment: Real-time status updates',
                'Post-deployment: Success/failure notification',
                '24h post-deployment: Follow-up summary'
            ]
        }

    def _assess_risk_summary(self, impacted_services: List[ImpactedService], change_type: str) -> str:
        """Generate risk assessment summary.

        Args:
            impacted_services: Impact list with risk levels for each service.
            change_type: Classification of the PR change.

        Returns:
            A concise, human-readable summary string for CLI/PR rendering.
        """
        high_risk_services = [s for s in impacted_services if s.risk_level == 'high']

        if len(high_risk_services) >= 3:
            return "High Risk: Multiple high-risk services impacted"
        elif len(impacted_services) >= 10:
            return "Medium Risk: Broad impact across many services"
        elif any(s.impact_type == 'contract' for s in impacted_services):
            return "Medium Risk: Contract changes require careful testing"
        else:
            return "Low Risk: Limited, well-understood impact"

    def save_impact_report(self, impact: ChangeImpact) -> None:
        """Save impact analysis to file.

        Writes a timestamped JSON report and a "latest" pointer for quick
        consumption by other scripts and dashboards.

        Args:
            impact: The computed `ChangeImpact` result to persist.
        """
        reports_dir = Path("analysis/reports/impact")
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"{impact.change_id}_{timestamp}_impact.json"

        report_dict = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'change_id': impact.change_id,
                'analysis_version': '1.0'
            },
            'summary': {
                'changed_service': impact.changed_service,
                'change_type': impact.change_type,
                'blast_radius': impact.blast_radius,
                'overall_severity': impact.overall_severity.value,
                'impacted_services_count': len(impact.impacted_services)
            },
            'impact_analysis': asdict(impact)
        }

        with open(report_file, 'w') as f:
            json.dump(report_dict, f, indent=2)

        logger.info(f"Saved impact analysis to {report_file}")

        # Update latest report
        latest_file = reports_dir / f"{impact.change_id}_latest_impact.json"
        with open(latest_file, 'w') as f:
            json.dump(report_dict, f, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze change impact across the platform")
    parser.add_argument("--pr", type=int, required=True, help="Pull request number to analyze")
    parser.add_argument("--github-token", help="GitHub token (default: GITHUB_TOKEN env var)")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file")
    parser.add_argument("--output-file", type=str, help="Output file for impact report")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get GitHub token
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable or --github-token is required")
        sys.exit(1)

    try:
        analyzer = ImpactAnalyzer(args.catalog_file)
        impact = analyzer.analyze_pr_impact(args.pr, github_token)

        # Save report
        if args.output_file:
            with open(args.output_file, 'w') as f:
                json.dump(asdict(impact), f, indent=2)
        else:
            analyzer.save_impact_report(impact)

        # Print summary
        print("\n🔍 Change Impact Analysis:")
        print(f"  PR: #{args.pr}")
        print(f"  Changed Service: {impact.changed_service}")
        print(f"  Change Type: {impact.change_type}")
        print(f"  Blast Radius: {impact.blast_radius} services")
        print(f"  Severity: {impact.overall_severity.value.upper()}")
        print(f"  Risk Assessment: {impact.risk_assessment}")

        print("\n🎯 Impacted Services:")
        for service in impact.impacted_services[:10]:
            print(f"  • {service.name} ({service.impact_type}) - {service.risk_level} risk")

        print("\n📋 Testing Scope:")
        for test in impact.testing_scope:
            print(f"  • {test}")

        print("\n🔄 Rollback Plan:")
        for step in impact.rollback_plan['steps']:
            print(f"  • {step}")

    except Exception as e:
        logger.error(f"Impact analysis failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
