#!/usr/bin/env python3
"""
254Carbon Meta Repository - Upgrade Eligibility Checker

Pre-checks upgrade readiness for services and specifications.

Usage:
    python scripts/check_upgrade_eligibility.py [--service gateway] [--spec-version gateway-core@1.2.0]
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
from dataclasses import dataclass, asdict


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/upgrade-eligibility.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class UpgradeCheck:
    """Represents an upgrade eligibility check."""
    check_name: str
    status: str  # 'pass', 'fail', 'warning'
    message: str
    severity: str  # 'low', 'medium', 'high'


@dataclass
class UpgradeEligibility:
    """Complete upgrade eligibility assessment."""
    service_name: str
    spec_name: str
    current_version: str
    target_version: str
    upgrade_type: str
    checks: List[UpgradeCheck]
    overall_eligible: bool
    risk_level: str
    recommendations: List[str]


class UpgradeEligibilityChecker:
    """Checks if services are eligible for upgrades."""

    def __init__(self, catalog_file: str = None, quality_file: str = None, drift_file: str = None):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.quality_file = quality_file or "catalog/latest_quality_snapshot.json"
        self.drift_file = drift_file or "catalog/latest_drift_report.json"

        # Load data sources
        self.catalog = self._load_catalog()
        self.quality_data = self._load_quality_data()
        self.drift_data = self._load_drift_data()
        self.upgrade_policies = self._load_upgrade_policies()

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

    def _load_upgrade_policies(self) -> Dict[str, Any]:
        """Load upgrade policies."""
        policies_file = Path("config/upgrade-policies.yaml")

        if not policies_file.exists():
            logger.warning(f"Policies file not found: {policies_file}")
            return self._get_default_policies()

        with open(policies_file) as f:
            return yaml.safe_load(f)

    def _get_default_policies(self) -> Dict[str, Any]:
        """Get default upgrade policies."""
        return {
            'auto_upgrade': {
                'patch': True,
                'minor': True,
                'major': False
            },
            'require_review': {
                'patch': False,
                'minor': False,
                'major': True
            }
        }

    def check_service_eligibility(self, service_name: str) -> List[UpgradeEligibility]:
        """Check upgrade eligibility for a specific service."""
        logger.info(f"Checking upgrade eligibility for service: {service_name}")

        service = next((s for s in self.catalog.get('services', []) if s['name'] == service_name), None)
        if not service:
            raise ValueError(f"Service not found: {service_name}")

        # Find API contracts for this service
        api_contracts = service.get('api_contracts', [])
        eligibilities = []

        for contract in api_contracts:
            if '@' in contract:
                spec_name, current_version = contract.split('@', 1)

                # Check if upgrade is available (simplified - would check spec registry)
                target_version = self._get_latest_version(spec_name, current_version)

                if target_version and target_version != current_version:
                    eligibility = self._check_spec_upgrade_eligibility(
                        service_name, spec_name, current_version, target_version
                    )
                    eligibilities.append(eligibility)

        return eligibilities

    def _get_latest_version(self, spec_name: str, current_version: str) -> Optional[str]:
        """Get latest version for a spec (placeholder implementation)."""
        # In a real implementation, this would query a spec registry
        # For now, we'll simulate version checking

        # Simple simulation - assume patch/minor upgrades are available
        version_parts = current_version.split('.')
        if len(version_parts) == 3:
            major, minor, patch = version_parts

            # Simulate available upgrades
            if int(patch) < 5:  # Assume patch upgrades available
                return f"{major}.{minor}.{int(patch) + 1}"
            elif int(minor) < 3:  # Assume minor upgrades available
                return f"{major}.{int(minor) + 1}.0"

        return None

    def _check_spec_upgrade_eligibility(self, service_name: str, spec_name: str,
                                      current_version: str, target_version: str) -> UpgradeEligibility:
        """Check eligibility for a specific spec upgrade."""
        checks = []

        # Check 1: Upgrade policy compliance
        upgrade_type = self._determine_upgrade_type(current_version, target_version)
        policy_check = self._check_upgrade_policy(upgrade_type)
        checks.append(policy_check)

        # Check 2: Service quality
        quality_check = self._check_service_quality(service_name)
        checks.append(quality_check)

        # Check 3: Dependency compatibility
        dep_check = self._check_dependency_compatibility(service_name, spec_name)
        checks.append(dep_check)

        # Check 4: Risk assessment
        risk_check = self._check_upgrade_risk(service_name, upgrade_type)
        checks.append(risk_check)

        # Determine overall eligibility
        overall_eligible = all(check.status == 'pass' for check in checks)
        risk_level = self._calculate_risk_level(checks)

        # Generate recommendations
        recommendations = self._generate_upgrade_recommendations(checks, upgrade_type)

        return UpgradeEligibility(
            service_name=service_name,
            spec_name=spec_name,
            current_version=current_version,
            target_version=target_version,
            upgrade_type=upgrade_type,
            checks=checks,
            overall_eligible=overall_eligible,
            risk_level=risk_level,
            recommendations=recommendations
        )

    def _determine_upgrade_type(self, current_version: str, target_version: str) -> str:
        """Determine upgrade type (major, minor, patch)."""
        current_parts = [int(x) for x in current_version.split('.')]
        target_parts = [int(x) for x in target_version.split('.')]

        if target_parts[0] > current_parts[0]:
            return 'major'
        elif target_parts[1] > current_parts[1]:
            return 'minor'
        elif target_parts[2] > current_parts[2]:
            return 'patch'
        else:
            return 'patch'  # Same or lower version

    def _check_upgrade_policy(self, upgrade_type: str) -> UpgradeCheck:
        """Check if upgrade complies with policies."""
        policies = self.upgrade_policies.get('auto_upgrade', {})

        if upgrade_type == 'major':
            allowed = policies.get('major', False)
        elif upgrade_type == 'minor':
            allowed = policies.get('minor', True)
        elif upgrade_type == 'patch':
            allowed = policies.get('patch', True)
        else:
            allowed = False

        if allowed:
            return UpgradeCheck(
                check_name="upgrade_policy",
                status="pass",
                message=f"{upgrade_type.title()} upgrades are allowed by policy",
                severity="low"
            )
        else:
            return UpgradeCheck(
                check_name="upgrade_policy",
                status="fail",
                message=f"{upgrade_type.title()} upgrades are not allowed by current policy",
                severity="high"
            )

    def _check_service_quality(self, service_name: str) -> UpgradeCheck:
        """Check if service quality allows upgrades."""
        quality_data = self.quality_data.get('services', {}).get(service_name, {})
        score = quality_data.get('score', 50)

        # Require minimum quality for upgrades
        if score >= 80:
            return UpgradeCheck(
                check_name="service_quality",
                status="pass",
                message=f"Service quality is good ({score:.1f}/100)",
                severity="low"
            )
        elif score >= 70:
            return UpgradeCheck(
                check_name="service_quality",
                status="warning",
                message=f"Service quality is acceptable ({score:.1f}/100) - monitor closely",
                severity="medium"
            )
        else:
            return UpgradeCheck(
                check_name="service_quality",
                status="fail",
                message=f"Service quality is poor ({score:.1f}/100) - improve before upgrading",
                severity="high"
            )

    def _check_dependency_compatibility(self, service_name: str, spec_name: str) -> UpgradeCheck:
        """Check if upgrade maintains dependency compatibility."""
        # Check if other services depend on this service's APIs
        dependent_services = []

        for service in self.catalog.get('services', []):
            if service_name in service.get('dependencies', {}).get('internal', []):
                dependent_services.append(service['name'])

        if not dependent_services:
            return UpgradeCheck(
                check_name="dependency_compatibility",
                status="pass",
                message="No dependent services found",
                severity="low"
            )
        else:
            return UpgradeCheck(
                check_name="dependency_compatibility",
                status="warning",
                message=f"{len(dependent_services)} services depend on this service - test compatibility",
                severity="medium"
            )

    def _check_upgrade_risk(self, service_name: str, upgrade_type: str) -> UpgradeCheck:
        """Check upgrade risk level."""
        service = next((s for s in self.catalog.get('services', []) if s['name'] == service_name), None)
        if not service:
            return UpgradeCheck(
                check_name="upgrade_risk",
                status="warning",
                message="Service not found in catalog",
                severity="medium"
            )

        # Risk factors
        maturity = service.get('maturity', 'unknown')
        domain = service.get('domain', 'unknown')

        # High-risk combinations
        if maturity == 'experimental' and upgrade_type == 'major':
            return UpgradeCheck(
                check_name="upgrade_risk",
                status="fail",
                message="Experimental service major upgrade - very high risk",
                severity="high"
            )
        elif domain == 'access' and upgrade_type == 'major':
            return UpgradeCheck(
                check_name="upgrade_risk",
                status="warning",
                message="Access domain major upgrade - requires security review",
                severity="high"
            )
        else:
            return UpgradeCheck(
                check_name="upgrade_risk",
                status="pass",
                message=f"{upgrade_type.title()} upgrade risk is acceptable for {maturity} service",
                severity="low"
            )

    def _calculate_risk_level(self, checks: List[UpgradeCheck]) -> str:
        """Calculate overall risk level for upgrade."""
        high_risk_count = len([c for c in checks if c.severity == 'high'])
        medium_risk_count = len([c for c in checks if c.severity == 'medium'])

        if high_risk_count > 0:
            return 'high'
        elif medium_risk_count > 1:
            return 'medium'
        else:
            return 'low'

    def _generate_upgrade_recommendations(self, checks: List[UpgradeCheck], upgrade_type: str) -> List[str]:
        """Generate upgrade recommendations."""
        recommendations = []

        failed_checks = [c for c in checks if c.status == 'fail']
        warning_checks = [c for c in checks if c.status == 'warning']

        if failed_checks:
            recommendations.append("🚫 Upgrade not recommended - address failed checks first")

        if warning_checks:
            recommendations.append("⚠️ Proceed with caution - review warning checks")

        if upgrade_type == 'major':
            recommendations.append("🔍 Major upgrade - conduct thorough testing and review")

        if any(c.check_name == 'dependency_compatibility' and c.status == 'warning' for c in checks):
            recommendations.append("🔗 Test dependent services for compatibility")

        if any(c.check_name == 'service_quality' and c.status == 'warning' for c in checks):
            recommendations.append("📈 Consider improving service quality before upgrading")

        if not recommendations:
            recommendations.append("✅ Upgrade appears safe to proceed")

        return recommendations

    def generate_eligibility_report(self, service_name: str = None) -> Dict[str, Any]:
        """Generate comprehensive eligibility report."""
        logger.info("Generating upgrade eligibility report...")

        if service_name:
            # Check specific service
            eligibilities = self.check_service_eligibility(service_name)
            services_to_check = [service_name]
        else:
            # Check all services
            services_to_check = [s['name'] for s in self.catalog.get('services', [])]
            eligibilities = []

            for svc_name in services_to_check:
                try:
                    svc_eligibilities = self.check_service_eligibility(svc_name)
                    eligibilities.extend(svc_eligibilities)
                except Exception as e:
                    logger.warning(f"Failed to check eligibility for {svc_name}: {e}")

        # Summarize results
        eligible_upgrades = [e for e in eligibilities if e.overall_eligible]
        risky_upgrades = [e for e in eligibilities if not e.overall_eligible]

        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "services_checked": len(services_to_check),
                "total_eligibility_checks": len(eligibilities)
            },
            "summary": {
                "eligible_upgrades": len(eligible_upgrades),
                "risky_upgrades": len(risky_upgrades),
                "high_risk_upgrades": len([e for e in eligibilities if e.risk_level == 'high']),
                "services_with_upgrades": len(set(e.service_name for e in eligibilities))
            },
            "eligibility_details": [asdict(e) for e in eligibilities],
            "recommendations": self._generate_overall_recommendations(eligible_upgrades, risky_upgrades)
        }

        return report

    def _generate_overall_recommendations(self, eligible: List[UpgradeEligibility],
                                       risky: List[UpgradeEligibility]) -> List[str]:
        """Generate overall upgrade recommendations."""
        recommendations = []

        if eligible:
            recommendations.append(f"✅ {len(eligible)} upgrades are ready to proceed")

        if risky:
            recommendations.append(f"⚠️ {len(risky)} upgrades need attention before proceeding")

        # Group by risk level
        high_risk = [e for e in eligible + risky if e.risk_level == 'high']
        if high_risk:
            recommendations.append(f"🔴 {len(high_risk)} high-risk upgrades identified")

        return recommendations


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Check upgrade eligibility for services")
    parser.add_argument("--service", type=str, help="Specific service to check (default: all services)")
    parser.add_argument("--spec-version", type=str, help="Specific spec upgrade to check (format: spec@version)")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file")
    parser.add_argument("--output-format", choices=["json", "table"], default="table",
                       help="Output format (default: table)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        checker = UpgradeEligibilityChecker(args.catalog_file)
        report = checker.generate_eligibility_report(args.service)

        if args.output_format == "json":
            print(json.dumps(report, indent=2))
        else:
            # Print formatted table
            print("\n📋 Upgrade Eligibility Report:")
            print(f"  Services Checked: {report['metadata']['services_checked']}")
            print(f"  Total Checks: {report['metadata']['total_eligibility_checks']}")

            summary = report['summary']
            print(f"  Eligible Upgrades: {summary['eligible_upgrades']}")
            print(f"  Risky Upgrades: {summary['risky_upgrades']}")
            print(f"  High Risk: {summary['high_risk_upgrades']}")

            if report['eligibility_details']:
                print("\n🔍 Detailed Results:")
                print("  Service       | Spec          | Version    | Type  | Status | Risk")
                print("  --------------|---------------|------------|-------|--------|-----")

                for eligibility in report['eligibility_details'][:10]:  # Top 10
                    status_icon = "✅" if eligibility['overall_eligible'] else "❌"
                    risk_icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(eligibility['risk_level'], "⚪")

                    print(f"  {eligibility['service_name']:<13} | {eligibility['spec_name']:<13} | {eligibility['target_version']:<10} | {eligibility['upgrade_type']:<5} | {status_icon:<6} | {risk_icon}")

            if report['recommendations']:
                print("\n💡 Recommendations:")
                for rec in report['recommendations']:
                    print(f"  {rec}")

    except Exception as e:
        logger.error(f"Upgrade eligibility check failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
