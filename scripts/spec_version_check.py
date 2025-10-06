#!/usr/bin/env python3
"""
254Carbon Meta Repository - Spec Version Check Script

Checks for specification version updates across services and generates upgrade
recommendations categorized by type and priority; can optionally propose PRs.

Usage:
    python scripts/spec_version_check.py [--dry-run] [--auto-upgrade] [--upgrade-policies FILE]

Design:
- Reads API contract pins from the catalog, compares to a registry snapshot, and
  assigns upgrade types (patch/minor/major) along with effort/priority hints.
- Policies from `config/upgrade-policies.yaml` control eligibility and review.

Outputs:
- Writes `catalog/spec-version-report.json` summarizing opportunities and policy context.
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
from dataclasses import dataclass
from packaging import version

# Import our utilities
from scripts.utils.circuit_breaker import github_api_circuit_breaker


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/spec-version-check.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class SpecVersion:
    """Represents a specification version."""
    name: str
    current_version: str
    latest_version: str
    upgrade_type: str  # 'major', 'minor', 'patch'
    breaking_changes: bool = False
    changelog_url: str = ""

    def __post_init__(self):
        if isinstance(self.current_version, str):
            self.current_ver = version.parse(self.current_version)
        else:
            self.current_ver = self.current_version

        if isinstance(self.latest_version, str):
            self.latest_ver = version.parse(self.latest_version)
        else:
            self.latest_ver = self.latest_version

        # Determine upgrade type
        if self.latest_ver.major > self.current_ver.major:
            self.upgrade_type = 'major'
            self.breaking_changes = True
        elif self.latest_ver.minor > self.current_ver.minor:
            self.upgrade_type = 'minor'
            self.breaking_changes = False
        elif self.latest_ver.micro > self.current_ver.micro:
            self.upgrade_type = 'patch'
            self.breaking_changes = False
        else:
            self.upgrade_type = 'none'


@dataclass
class UpgradeRecommendation:
    """Represents an upgrade recommendation."""
    service: str
    spec_name: str
    current_version: str
    recommended_version: str
    upgrade_type: str
    priority: str  # 'high', 'medium', 'low'
    rationale: str
    breaking_changes: bool
    estimated_effort: str  # 'minimal', 'moderate', 'significant'
    auto_upgrade_safe: bool


class SpecVersionChecker:
    """Checks for specification version updates."""

    def __init__(self, catalog_file: str = None, specs_repo: str = "254carbon/254carbon-specs",
                 upgrade_policies_file: str = None, dry_run: bool = False):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.catalog_file = catalog_file
        self.specs_repo = specs_repo
        self.upgrade_policies_file = upgrade_policies_file or "config/upgrade-policies.yaml"
        self.dry_run = dry_run

        # Initialize circuit breaker for GitHub API protection
        self.circuit_breaker = github_api_circuit_breaker()

        # Load catalog
        self.catalog = self._load_catalog()

        # Load upgrade policies
        self.upgrade_policies = self._load_upgrade_policies()

        # Specs registry (would be fetched in real implementation)
        self.specs_registry = self._fetch_specs_registry()

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

    def _load_upgrade_policies(self) -> Dict[str, Any]:
        """Load upgrade policies."""
        policies_path = Path(self.upgrade_policies_file)

        if not policies_path.exists():
            logger.warning(f"Upgrade policies file not found: {policies_path}, using defaults")
            return self._get_default_policies()

        with open(policies_path) as f:
            return yaml.safe_load(f)

    def _get_default_policies(self) -> Dict[str, Any]:
        """Get default upgrade policies."""
        return {
            "auto_upgrade": {
                "patch": True,
                "minor": True,
                "major": False
            },
            "require_review": {
                "patch": False,
                "minor": False,
                "major": True
            },
            "notification_thresholds": {
                "patch": 7,    # days
                "minor": 30,   # days
                "major": 90    # days
            }
        }

    def _fetch_specs_registry(self) -> Dict[str, Any]:
        """Fetch specifications registry."""
        def _fetch_registry_impl():
            # In a real implementation, this would fetch from:
            # - GitHub API to get latest specs
            # - A dedicated specs service
            # - Package registry

            logger.info(f"Fetching specs registry from {self.specs_repo}")

            # Placeholder implementation with sample data
            registry = {
            "gateway-core": {
                "versions": [
                    {"version": "1.0.0", "release_date": "2024-01-01", "breaking": False},
                    {"version": "1.1.0", "release_date": "2024-02-01", "breaking": False},
                    {"version": "1.2.0", "release_date": "2024-03-01", "breaking": False},
                    {"version": "2.0.0", "release_date": "2024-06-01", "breaking": True}
                ]
            },
            "curves-api": {
                "versions": [
                    {"version": "1.0.0", "release_date": "2024-01-01", "breaking": False},
                    {"version": "1.1.0", "release_date": "2024-02-15", "breaking": False},
                    {"version": "2.0.0", "release_date": "2024-05-01", "breaking": True},
                    {"version": "2.1.0", "release_date": "2024-08-01", "breaking": False}
                ]
            },
            "pricing-api": {
                "versions": [
                    {"version": "1.0.0", "release_date": "2024-03-01", "breaking": False}
                ]
            },
            "auth-spec": {
                "versions": [
                    {"version": "1.0.0", "release_date": "2024-01-01", "breaking": False},
                    {"version": "2.0.0", "release_date": "2024-04-01", "breaking": True},
                    {"version": "3.0.0", "release_date": "2024-07-01", "breaking": True}
                ]
            }
            }

            logger.info(f"Loaded specs registry with {len(registry)} specifications")
            return registry

        return self.circuit_breaker.call(_fetch_registry_impl)

    def check_service_spec_versions(self) -> List[UpgradeRecommendation]:
        """Check specification versions for all services."""
        logger.info("Checking specification versions...")
        recommendations = []

        services = self.catalog.get('services', [])

        for service in services:
            service_name = service['name']
            api_contracts = service.get('api_contracts', [])

            for contract in api_contracts:
                if '@' in contract:
                    spec_name, current_version = contract.split('@', 1)

                    # Get latest version from registry
                    spec_info = self.specs_registry.get(spec_name)
                    if not spec_info:
                        logger.warning(f"No registry info found for spec: {spec_name}")
                        continue

                    # Find latest version
                    versions = spec_info.get('versions', [])
                    if not versions:
                        continue

                    latest_version_info = max(versions, key=lambda v: version.parse(v['version']))
                    latest_version = latest_version_info['version']

                    if current_version != latest_version:
                        # Create version comparison
                        spec_version = SpecVersion(
                            spec_name, current_version, latest_version,
                            breaking_changes=latest_version_info.get('breaking', False)
                        )

                        # Generate recommendation
                        recommendation = self._generate_recommendation(service_name, spec_version)
                        if recommendation:
                            recommendations.append(recommendation)

        logger.info(f"Generated {len(recommendations)} upgrade recommendations")
        return recommendations

    def _generate_recommendation(self, service_name: str, spec_version: SpecVersion) -> Optional[UpgradeRecommendation]:
        """Generate upgrade recommendation for a service/spec combination."""
        if spec_version.upgrade_type == 'none':
            return None

        # Determine priority based on upgrade type and policies
        policies = self.upgrade_policies.get('auto_upgrade', {})

        if spec_version.upgrade_type == 'patch' and policies.get('patch', False):
            priority = 'high'
            auto_upgrade_safe = True
            estimated_effort = 'minimal'
        elif spec_version.upgrade_type == 'minor' and policies.get('minor', False):
            priority = 'medium'
            auto_upgrade_safe = True
            estimated_effort = 'minimal'
        elif spec_version.upgrade_type == 'major':
            priority = 'low'
            auto_upgrade_safe = False
            estimated_effort = 'significant'
        else:
            priority = 'medium'
            auto_upgrade_safe = False
            estimated_effort = 'moderate'

        # Generate rationale
        if spec_version.breaking_changes:
            rationale = f"Major version upgrade available ({spec_version.current_version} → {spec_version.latest_version}). Breaking changes present."
        else:
            rationale = f"{spec_version.upgrade_type.title()} version upgrade available ({spec_version.current_version} → {spec_version.latest_version})."

        return UpgradeRecommendation(
            service=service_name,
            spec_name=spec_version.name,
            current_version=spec_version.current_version,
            recommended_version=spec_version.latest_version,
            upgrade_type=spec_version.upgrade_type,
            priority=priority,
            rationale=rationale,
            breaking_changes=spec_version.breaking_changes,
            estimated_effort=estimated_effort,
            auto_upgrade_safe=auto_upgrade_safe
        )

    def generate_upgrade_prs(self, recommendations: List[UpgradeRecommendation], dry_run: bool = True) -> Dict[str, Any]:
        """Generate upgrade PRs for eligible recommendations."""
        logger.info("Generating upgrade PRs...")

        eligible_for_auto = [r for r in recommendations if r.auto_upgrade_safe]
        need_review = [r for r in recommendations if not r.auto_upgrade_safe]

        results = {
            "auto_upgrade_candidates": len(eligible_for_auto),
            "review_required": len(need_review),
            "total_recommendations": len(recommendations),
            "generated_prs": 0,
            "dry_run": dry_run
        }

        # In a real implementation, this would:
        # 1. Create PR branches
        # 2. Update service-manifest.yaml files
        # 3. Update specs.lock.json files
        # 4. Create PRs with proper templates

        if dry_run:
            logger.info(f"Dry run: Would create {len(eligible_for_auto)} auto-upgrade PRs")
            logger.info(f"Dry run: Would flag {len(need_review)} PRs for manual review")
        else:
            logger.info(f"Would create {len(eligible_for_auto)} auto-upgrade PRs")
            logger.info(f"Would flag {len(need_review)} PRs for manual review")
            # results["generated_prs"] = actual_pr_count

        return results

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive spec version report."""
        logger.info("Generating spec version report...")

        # Get upgrade recommendations
        recommendations = self.check_service_spec_versions()

        # Categorize recommendations
        by_priority = {
            'high': [r for r in recommendations if r.priority == 'high'],
            'medium': [r for r in recommendations if r.priority == 'medium'],
            'low': [r for r in recommendations if r.priority == 'low']
        }

        by_upgrade_type = {
            'patch': [r for r in recommendations if r.upgrade_type == 'patch'],
            'minor': [r for r in recommendations if r.upgrade_type == 'minor'],
            'major': [r for r in recommendations if r.upgrade_type == 'major']
        }

        # Generate summary
        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "catalog_timestamp": self.catalog.get('metadata', {}).get('generated_at'),
                "specs_repo": self.specs_repo,
                "total_services": len(self.catalog.get('services', [])),
                "total_recommendations": len(recommendations)
            },
            "summary": {
                "by_priority": {
                    "high": len(by_priority['high']),
                    "medium": len(by_priority['medium']),
                    "low": len(by_priority['low'])
                },
                "by_upgrade_type": {
                    "patch": len(by_upgrade_type['patch']),
                    "minor": len(by_upgrade_type['minor']),
                    "major": len(by_upgrade_type['major'])
                },
                "auto_upgrade_eligible": len([r for r in recommendations if r.auto_upgrade_safe])
            },
            "recommendations": recommendations,
            "policies": self.upgrade_policies
        }

        return report

    def save_report(self, report: Dict[str, Any]) -> None:
        """Save report to file."""
        catalog_dir = Path("catalog")
        catalog_dir.mkdir(exist_ok=True)

        # Save detailed report
        report_file = catalog_dir / "spec-version-report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Saved spec version report to {report_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check for specification version updates")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode (don't create PRs)")
    parser.add_argument("--auto-upgrade", action="store_true", help="Automatically create upgrade PRs where safe")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file (default: auto-detect)")
    parser.add_argument("--specs-repo", type=str, default="254carbon/254carbon-specs", help="Specs repository")
    parser.add_argument("--upgrade-policies", type=str, help="Path to upgrade policies file")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        checker = SpecVersionChecker(
            catalog_file=args.catalog_file,
            specs_repo=args.specs_repo,
            upgrade_policies=args.upgrade_policies,
            dry_run=args.dry_run
        )

        report = checker.generate_report()
        checker.save_report(report)

        # Generate PRs if requested
        if args.auto_upgrade and not args.dry_run:
            pr_results = checker.generate_upgrade_prs(report['recommendations'], dry_run=False)
            logger.info(f"Generated {pr_results['generated_prs']} upgrade PRs")
        elif args.dry_run:
            pr_results = checker.generate_upgrade_prs(report['recommendations'], dry_run=True)

        logger.info("Spec version check completed successfully")

    except Exception as e:
        logger.error(f"Spec version check failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
