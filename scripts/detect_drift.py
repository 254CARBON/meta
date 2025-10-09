#!/usr/bin/env python3
"""
254Carbon Meta Repository - Drift Detection Script

Detects drift between declared and actual platform states to surface
actionable gaps and hygiene issues.

Usage:
    python scripts/detect_drift.py [--catalog-file FILE] [--specs-repo REPO]

Overview:
- Loads the unified catalog and a lightweight spec registry snapshot to
  compare pinned API contracts against latest available versions.
- Emits issues for: spec version lag, missing lock files, stale service
  versions, shared dependency hotspots, and unknown event schemas.
- Classifies issues by severity for downstream reporting and triage.

Outputs:
- JSON report written under `analysis/reports/drift/` and a stable pointer
  at `analysis/reports/drift/latest_drift_report.json`.
- Designed to feed report rendering (Markdown) and risk/context generators.

Notes:
- Placeholders are used where external systems would normally be queried
  (schema registry, real lock files). Replace with integrations as they
  become available.
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

from scripts.utils import monitor_execution, audit_logger, redis_client, AuditCategory


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


class _SpecRegistryBackend:
    """Interface for spec registry backends."""

    def fetch_index(self, specs_repo: str) -> Dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError


class _StaticSpecBackend(_SpecRegistryBackend):
    """Static in-memory backend used by default for offline operation."""

    def fetch_index(self, specs_repo: str) -> Dict[str, Any]:
        return {
            "gateway-core": {"latest_version": "1.2.0", "description": "Core gateway API"},
            "curves-api": {"latest_version": "2.1.0", "description": "Curves data API"},
            "pricing-api": {"latest_version": "1.0.0", "description": "Pricing service API"},
            "auth-spec": {"latest_version": "3.0.0", "description": "Authentication spec"}
        }


class _LocalFileSpecBackend(_SpecRegistryBackend):
    """Local file backend for specs index (JSON).

    The path can be provided via `path` or environment variable `SPECS_INDEX_FILE`.
    File format: { "spec-name": { "latest_version": "x.y.z", ... }, ... }
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.getenv("SPECS_INDEX_FILE")

    def fetch_index(self, specs_repo: str) -> Dict[str, Any]:
        if not self.path:
            logger.warning("Local specs index path not provided; falling back to empty index")
            return {}
        try:
            with open(self.path) as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Specs index file not found: {self.path}; returning empty index")
            return {}
        except Exception as e:
            logger.warning(f"Failed to read specs index file '{self.path}': {e}")
            return {}


class SpecRegistry:
    """Manages specification registry and version information."""

    def __init__(self, specs_repo: str = "254carbon/254carbon-specs", backend: Optional[Any] = None,
                 backend_config: Optional[Dict[str, Any]] = None):
        self.specs_repo = specs_repo
        self._backend = self._init_backend(backend, backend_config or {})
        self.specs_index = self._fetch_specs_index()

    def _init_backend(self, backend: Optional[Any], cfg: Dict[str, Any]) -> _SpecRegistryBackend:
        if backend is None:
            backend_name = os.getenv("SPECS_BACKEND", "static").lower()
            if backend_name == "file":
                return _LocalFileSpecBackend(cfg.get("path"))
            return _StaticSpecBackend()
        if isinstance(backend, str):
            if backend.lower() == "file":
                return _LocalFileSpecBackend(cfg.get("path"))
            return _StaticSpecBackend()
        if hasattr(backend, "fetch_index"):
            return backend  # type: ignore[return-value]
        return _StaticSpecBackend()

    def _fetch_specs_index(self) -> Dict[str, Any]:
        """Fetch latest specs index from selected backend.

        Returns:
            A mapping of spec name -> metadata.
        """
        try:
            logger.info(f"Fetching specs index via backend: {self._backend.__class__.__name__}")
            index = self._backend.fetch_index(self.specs_repo)
            logger.info(f"Loaded specs index with {len(index)} specifications")
            return index
        except Exception as e:
            logger.error(f"Failed to fetch specs index: {e}")
            return {}

    def get_latest_version(self, spec_name: str) -> Optional[str]:
        """Get latest version of a specification.

        Args:
            spec_name: Specification identifier.

        Returns:
            Latest version string if known, otherwise None.
        """
        spec_info = self.specs_index.get(spec_name)
        return spec_info.get('latest_version') if spec_info else None

    def get_all_specs(self) -> List[str]:
        """Get all available specification names.

        Returns:
            List of spec names present in the index.
        """
        return list(self.specs_index.keys())


class DriftDetector:
    """Detects various types of drift in the platform."""

    def __init__(self, catalog_file: str = None, specs_repo: str = "254carbon/254carbon-specs"):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.specs_registry = SpecRegistry(specs_repo)
        self.event_registry = self._load_event_registry()

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
        """Detect specification version lag.

        Compares pinned API contracts in the catalog to the latest known
        versions and emits drift issues with severity based on major/minor lag.

        Returns:
            List of DriftIssue entries describing spec lag per service/contract.
        """
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
        """Detect missing specs.lock.json files.

        Heuristic detection of services declaring API contracts but lacking a
        lockfile indicator.

        Returns:
            List of DriftIssue entries for missing lockfiles.
        """
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
        """Detect stale service versions.

        Flags services with last_update timestamps older than defined thresholds.

        Returns:
            List of DriftIssue entries with severity by age window.
        """
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
        """Detect dependency version drift.

        Identifies shared external dependencies as potential drift hotspots.

        Returns:
            List of DriftIssue entries for shared dependency clusters.
        """
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
        """Detect unknown event schemas.

        Placeholder that flags events as unknown without a registry lookup.

        Returns:
            List of DriftIssue entries marking unverified events.
        """
        logger.info("Detecting unknown event schemas...")
        issues = []
        known_events = self.event_registry

        services = self.catalog.get('services', [])

        # In a real implementation, this would check against a schema registry
        # For now, we'll flag any events as potentially unknown
        for service in services:
            service_name = service['name']
            events_in = service.get('events_in', [])
            events_out = service.get('events_out', [])

            all_events = events_in + events_out

            for event in all_events:
                if not event:
                    continue
                if known_events and event in known_events:
                    continue
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

    def _load_event_registry(self) -> set[str]:
        """Load the canonical event schema registry."""
        registry_path = Path("config/events-registry.yaml")

        if not registry_path.exists():
            logger.debug("Event registry file not found: %s", registry_path)
            return set()

        try:
            with registry_path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except Exception as exc:
            logger.warning(f"Failed to load event registry: {exc}")
            return set()

        events = data.get("events", [])
        return {str(event).strip() for event in events if event}

    @monitor_execution("drift-detection")
    def generate_drift_report(self) -> Dict[str, Any]:
        """Generate comprehensive drift report.

        Runs all detectors, aggregates results into severities/types, and
        returns a normalized report structure.

        Returns:
            A dictionary suitable for downstream rendering and persistence.
        """
        logger.info("Generating drift report...")

        # Try to load cached drift state first
        cached_drift = redis_client.get("drift_state", fallback_to_file=True)
        if cached_drift:
            logger.info("Using cached drift state")
            return cached_drift

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

        # Cache the drift state
        redis_client.set("drift_state", report, ttl=1800, fallback_to_file=True)

        return report

    def _generate_recommendations(self, issues: List[DriftIssue]) -> List[str]:
        """Generate actionable recommendations.

        Args:
            issues: Collected drift issues.

        Returns:
            A list of human-readable recommendation strings.
        """
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
        """Save drift report to file.

        Persists a timestamped report and a stable `latest_drift_report.json`.

        Args:
            report: The drift report dictionary to write.
        """
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

        # Log drift detection completion
        severity_counts = report.get("summary", {}).get("issues_by_severity", {})
        issues_by_type = report.get("summary", {}).get("issues_by_type", {})
        metadata = report.get("metadata", {})
        audit_logger.log_action(
            user="system",
            action="drift_detection",
            resource="drift_report",
            resource_type="drift_data",
            details={
                "total_issues": metadata.get("total_issues", 0),
                "issues_by_severity": severity_counts,
                "issues_by_type": issues_by_type,
                "generated_at": metadata.get("generated_at"),
                "report_file": str(report_file)
            },
            category=AuditCategory.DRIFT
        )


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
        severity_counts = report['summary']['issues_by_severity']
        high_issues = severity_counts.get('high', 0)
        error_issues = severity_counts.get('error', 0)

        if high_issues > 0 or error_issues > 0:
            logger.warning(f"Found {high_issues} high-priority and {error_issues} error issues")
            # Don't exit with error code for drift detection - it's informational

        logger.info("Drift detection completed successfully")

    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
