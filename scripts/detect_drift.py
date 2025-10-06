#!/usr/bin/env python3
"""
254Carbon Meta Repository - Drift Detection Script

Detects drift between declared and actual states.

Usage:
    python scripts/detect_drift.py [--catalog-file FILE] [--specs-repo REPO]
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
import requests
from dataclasses import dataclass
from packaging import version


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/drift.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class SpecPin:
    """Represents a specification pin."""
    name: str
    version: str
    source: str

    def __post_init__(self):
        if isinstance(self.version, str):
            self.version_obj = version.parse(self.version)
        else:
            self.version_obj = self.version


@dataclass
class SpecInfo:
    """Represents specification information."""
    name: str
    latest_version: str
    pins: List[SpecPin]


@dataclass
class DriftIssue:
    """Represents a drift issue."""
    type: str
    severity: str
    service: str
    description: str
    current_value: Any
    expected_value: Any
    remediation: str


class SpecRegistry:
    """Manages specification registry and version information."""

    def __init__(self, specs_repo: str = "254carbon/254carbon-specs"):
        self.specs_repo = specs_repo
        self.specs_index = self._fetch_specs_index()

    def _fetch_specs_index(self) -> Dict[str, Any]:
        """Fetch latest specs index from repository."""
        try:
            # This would typically fetch from GitHub API or a specs service
            # For now, we'll use a placeholder implementation
            logger.info(f"Fetching specs index from {self.specs_repo}")

            # Placeholder: in a real implementation, this would fetch from:
            # - GitHub API to get latest specs index file
            # - A specs service endpoint
            # - Local cache of specs

            # For demonstration, we'll create a sample specs index
            sample_specs = {
                "gateway-core": {"latest_version": "1.2.0", "description": "Core gateway API"},
                "curves-api": {"latest_version": "2.1.0", "description": "Curves data API"},
                "pricing-api": {"latest_version": "1.0.0", "description": "Pricing service API"},
                "auth-spec": {"latest_version": "3.0.0", "description": "Authentication spec"}
            }

            logger.info(f"Loaded specs index with {len(sample_specs)} specifications")
            return sample_specs

        except Exception as e:
            logger.error(f"Failed to fetch specs index: {e}")
            return {}

    def get_latest_version(self, spec_name: str) -> Optional[str]:
        """Get latest version of a specification."""
        spec_info = self.specs_index.get(spec_name)
        return spec_info.get('latest_version') if spec_info else None

    def get_all_specs(self) -> List[str]:
        """Get all available specification names."""
        return list(self.specs_index.keys())


class DriftDetector:
    """Detects various types of drift in the platform."""

    def __init__(self, catalog_file: str = None, specs_repo: str = "254carbon/254carbon-specs"):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.specs_registry = SpecRegistry(specs_repo)

        # Load catalog
        self.catalog = self._load_catalog()

        # Reports directory
        self.reports_dir = Path("analysis/reports/drift")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

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
        """Load catalog from file."""
        logger.info(f"Loading catalog from {self.catalog_path}")

        with open(self.catalog_path) as f:
            if self.catalog_path.suffix == '.yaml':
                return yaml.safe_load(f)
            else:
                return json.load(f)

    def detect_spec_lag(self) -> List[DriftIssue]:
        """Detect specification version lag."""
        logger.info("Detecting specification version lag...")
        issues = []

        services = self.catalog.get('services', [])

        for service in services:
            service_name = service['name']
            api_contracts = service.get('api_contracts', [])

            for contract in api_contracts:
                if '@' in contract:
                    spec_name, pinned_version = contract.split('@', 1)

                    latest_version = self.specs_registry.get_latest_version(spec_name)
                    if latest_version:
                        try:
                            pinned_ver = version.parse(pinned_version)
                            latest_ver = version.parse(latest_version)

                            if pinned_ver < latest_ver:
                                # Calculate lag severity
                                minor_behind = latest_ver.minor - pinned_ver.minor
                                major_behind = latest_ver.major - pinned_ver.major

                                if major_behind > 0:
                                    severity = "high"
                                    remediation = f"⚠️ Major version lag ({major_behind} major versions behind). Manual review required."
                                elif minor_behind > 2:
                                    severity = "moderate"
                                    remediation = "📦 Consider upgrading to latest minor version."
                                else:
                                    severity = "low"
                                    remediation = "📋 Minor version lag. Upgrade when convenient."

                                issue = DriftIssue(
                                    type="spec_lag",
                                    severity=severity,
                                    service=service_name,
                                    description=f"Service pins {spec_name}@{pinned_version} but latest is {latest_version}",
                                    current_value=pinned_version,
                                    expected_value=latest_version,
                                    remediation=remediation
                                )
                                issues.append(issue)

                        except version.InvalidVersion:
                            issue = DriftIssue(
                                type="invalid_version",
                                severity="error",
                                service=service_name,
                                description=f"Invalid version format in contract: {contract}",
                                current_value=contract,
                                expected_value="valid semver",
                                remediation="Fix version format in service manifest"
                            )
                            issues.append(issue)

        logger.info(f"Found {len(issues)} spec lag issues")
        return issues

    def detect_missing_locks(self) -> List[DriftIssue]:
        """Detect missing specs.lock.json files."""
        logger.info("Detecting missing lock files...")
        issues = []

        services = self.catalog.get('services', [])

        for service in services:
            service_name = service['name']

            # Check if service has API contracts but no lock file indication
            api_contracts = service.get('api_contracts', [])
            if api_contracts:
                # In a real implementation, this would check for actual lock file presence
                # For now, we'll simulate this check
                has_lock_file = service.get('_has_lock_file', True)  # Placeholder

                if not has_lock_file:
                    issue = DriftIssue(
                        type="missing_lock",
                        severity="high",
                        service=service_name,
                        description="Service uses API contracts but missing specs.lock.json",
                        current_value="no lock file",
                        expected_value="specs.lock.json present",
                        remediation="Generate specs.lock.json to pin exact contract versions"
                    )
                    issues.append(issue)

        logger.info(f"Found {len(issues)} missing lock file issues")
        return issues

    def detect_version_staleness(self) -> List[DriftIssue]:
        """Detect stale service versions."""
        logger.info("Detecting version staleness...")
        issues = []

        services = self.catalog.get('services', [])

        for service in services:
            service_name = service['name']
            current_version = service.get('version', '0.0.0')
            last_update = service.get('last_update')

            if last_update:
                try:
                    # Parse timestamp
                    update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)

                    # Calculate days since last update
                    days_since_update = (now - update_time).days

                    # Determine staleness thresholds (customizable)
                    stale_threshold = 90  # days
                    very_stale_threshold = 180  # days

                    if days_since_update > very_stale_threshold:
                        severity = "high"
                        remediation = "🔴 Service version is very stale. Immediate update recommended."
                    elif days_since_update > stale_threshold:
                        severity = "moderate"
                        remediation = "🟡 Service version is stale. Plan update in next sprint."
                    else:
                        continue  # Not stale enough to report

                    issue = DriftIssue(
                        type="version_staleness",
                        severity=severity,
                        service=service_name,
                        description=f"Service version {current_version} is {days_since_update} days old",
                        current_value=f"{current_version} ({days_since_update} days old)",
                        expected_value=f"< {stale_threshold} days old",
                        remediation=remediation
                    )
                    issues.append(issue)

                except (ValueError, AttributeError) as e:
                    logger.debug(f"Could not parse last_update for {service_name}: {e}")

        logger.info(f"Found {len(issues)} version staleness issues")
        return issues

    def detect_dependency_drift(self) -> List[DriftIssue]:
        """Detect dependency version drift."""
        logger.info("Detecting dependency version drift...")
        issues = []

        services = self.catalog.get('services', [])

        # Group services by shared dependencies to detect version mismatches
        dependency_versions = {}

        for service in services:
            service_name = service['name']
            dependencies = service.get('dependencies', {}).get('external', [])

            for dep in dependencies:
                if dep not in dependency_versions:
                    dependency_versions[dep] = []
                dependency_versions[dep].append(service_name)

        # Check for version divergence in shared dependencies
        for dep, services_using in dependency_versions.items():
            if len(services_using) > 1:
                # In a real implementation, this would check actual dependency versions
                # For now, we'll flag shared dependencies as potential drift points
                if len(services_using) > 3:  # Many services using same dep
                    issue = DriftIssue(
                        type="shared_dependency",
                        severity="low",
                        service=", ".join(services_using),
                        description=f"Shared external dependency: {dep} used by {len(services_using)} services",
                        current_value=f"used by {len(services_using)} services",
                        expected_value="consistent versions across services",
                        remediation="Monitor for version conflicts in shared dependencies"
                    )
                    issues.append(issue)

        logger.info(f"Found {len(issues)} dependency drift issues")
        return issues

    def detect_event_schema_unknown(self) -> List[DriftIssue]:
        """Detect unknown event schemas."""
        logger.info("Detecting unknown event schemas...")
        issues = []

        services = self.catalog.get('services', [])

        # In a real implementation, this would check against a schema registry
        # For now, we'll flag any events as potentially unknown
        for service in services:
            service_name = service['name']
            events_in = service.get('events_in', [])
            events_out = service.get('events_out', [])

            all_events = events_in + events_out

            for event in all_events:
                # Placeholder: in reality, check against schema registry
                issue = DriftIssue(
                    type="event_schema_unknown",
                    severity="low",
                    service=service_name,
                    description=f"Event schema not found in registry: {event}",
                    current_value=event,
                    expected_value="registered event schema",
                    remediation="Register event schema or verify naming convention"
                )
                issues.append(issue)

        logger.info(f"Found {len(issues)} unknown event schema issues")
        return issues

    def generate_drift_report(self) -> Dict[str, Any]:
        """Generate comprehensive drift report."""
        logger.info("Generating drift report...")

        # Run all drift detection checks
        drift_issues = []

        detectors = [
            ("spec_lag", self.detect_spec_lag),
            ("missing_locks", self.detect_missing_locks),
            ("version_staleness", self.detect_version_staleness),
            ("dependency_drift", self.detect_dependency_drift),
            ("event_schemas", self.detect_event_schema_unknown)
        ]

        for name, detector_func in detectors:
            try:
                issues = detector_func()
                drift_issues.extend(issues)
                logger.info(f"  - {name}: {len(issues)} issues")
            except Exception as e:
                logger.error(f"Detector '{name}' failed: {e}")

        # Categorize by severity
        issues_by_severity = {
            "high": [i for i in drift_issues if i.severity == "high"],
            "moderate": [i for i in drift_issues if i.severity == "moderate"],
            "low": [i for i in drift_issues if i.severity == "low"],
            "error": [i for i in drift_issues if i.severity == "error"]
        }

        # Generate summary
        total_issues = len(drift_issues)
        high_severity = len(issues_by_severity["high"]) + len(issues_by_severity["error"])
        overall_healthy = high_severity == 0

        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "catalog_timestamp": self.catalog.get('metadata', {}).get('generated_at'),
                "total_services": len(self.catalog.get('services', [])),
                "total_issues": total_issues,
                "overall_healthy": overall_healthy
            },
            "summary": {
                "issues_by_severity": {
                    "high": len(issues_by_severity["high"]),
                    "moderate": len(issues_by_severity["moderate"]),
                    "low": len(issues_by_severity["low"]),
                    "error": len(issues_by_severity["error"])
                },
                "issues_by_type": {}
            },
            "issues": drift_issues,
            "recommendations": self._generate_recommendations(drift_issues)
        }

        # Count issues by type
        for issue in drift_issues:
            issue_type = issue.type
            if issue_type not in report["summary"]["issues_by_type"]:
                report["summary"]["issues_by_type"][issue_type] = 0
            report["summary"]["issues_by_type"][issue_type] += 1

        return report

    def _generate_recommendations(self, issues: List[DriftIssue]) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        high_issues = [i for i in issues if i.severity in ["high", "error"]]

        if high_issues:
            recommendations.append(f"🚨 {len(high_issues)} high-priority issues require immediate attention")

            # Group by issue type
            type_counts = {}
            for issue in high_issues:
                if issue.type not in type_counts:
                    type_counts[issue.type] = 0
                type_counts[issue.type] += 1

            for issue_type, count in type_counts.items():
                recommendations.append(f"  - {count} {issue_type} issues")

        if not high_issues and issues:
            recommendations.append("✅ No critical drift issues detected")

        return recommendations

    def save_report(self, report: Dict[str, Any]) -> None:
        """Save drift report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.reports_dir / f"{timestamp}_drift_report.json"

        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Saved drift report to {report_file}")

        # Also save latest report for easy access
        latest_file = self.reports_dir / "latest_drift_report.json"
        with open(latest_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Updated latest drift report: {latest_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Detect drift between declared and actual states")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file (default: auto-detect)")
    parser.add_argument("--specs-repo", type=str, default="254carbon/254carbon-specs", help="Specs repository")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        detector = DriftDetector(args.catalog_file, args.specs_repo)
        report = detector.generate_drift_report()
        detector.save_report(report)

        # Exit with error if there are high-severity issues
        high_issues = len(report['summary']['issues_by_severity'].get('high', 0))
        error_issues = len(report['summary']['issues_by_severity'].get('error', 0))

        if high_issues > 0 or error_issues > 0:
            logger.warning(f"Found {high_issues} high-priority and {error_issues} error issues")
            # Don't exit with error code for drift detection - it's informational

        logger.info("Drift detection completed successfully")

    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
