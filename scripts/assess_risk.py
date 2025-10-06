#!/usr/bin/env python3
"""
254Carbon Meta Repository - Risk Assessment Engine

Assesses risk levels for services and proposed changes using multiple signals
(maturity, quality, dependencies, drift, coupling, historical hints).

Usage:
    python scripts/assess_risk.py --service gateway [--change-type spec_upgrade]

Model overview:
- Computes normalized risk factors per dimension (0.0–1.0), then aggregates
  via weighted sum into a composite risk score → discrete RiskLevel.
- Optionally adjusts overall change risk based on change type and scope.

Outputs:
- Emits a JSON report with service risk, change risk (if requested), and
  recommendations on mitigation, approvals, and next steps.
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
from enum import Enum


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/risk-assessment.log')
    ]
)
logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ServiceRiskFactors:
    """Risk factors for a service."""
    service_name: str
    maturity_risk: float
    quality_risk: float
    dependency_risk: float
    drift_risk: float
    domain_risk: float
    coupling_risk: float
    historical_risk: float


@dataclass
class ChangeRiskAssessment:
    """Risk assessment for a proposed change."""
    service_name: str
    change_type: str
    change_scope: str
    impact_radius: int
    risk_factors: Dict[str, float]
    composite_risk_score: float
    risk_level: RiskLevel
    mitigation_strategies: List[str]
    required_approvals: List[str]


class RiskAssessor:
    """Assesses risk levels for services and changes."""

    def __init__(self, catalog_file: str = None, drift_file: str = None, quality_file: str = None):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.drift_file = drift_file or "catalog/latest_drift_report.json"
        self.quality_file = quality_file or "catalog/latest_quality_snapshot.json"

        # Load data sources
        self.catalog = self._load_catalog()
        self.drift_data = self._load_drift_data()
        self.quality_data = self._load_quality_data()

        # Risk configuration
        self.risk_weights = self._get_risk_weights()

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

    def _get_risk_weights(self) -> Dict[str, float]:
        """Get risk assessment weights."""
        return {
            'maturity': 0.15,
            'quality': 0.25,
            'dependency': 0.20,
            'drift': 0.15,
            'domain': 0.10,
            'coupling': 0.10,
            'historical': 0.05
        }

    def assess_service_risk(self, service_name: str) -> ServiceRiskFactors:
        """Assess risk factors for a specific service."""
        logger.info(f"Assessing risk for service: {service_name}")

        # Find service in catalog
        service = next((s for s in self.catalog.get('services', []) if s['name'] == service_name), None)
        if not service:
            raise ValueError(f"Service not found: {service_name}")

        # Calculate individual risk factors
        maturity_risk = self._assess_maturity_risk(service)
        quality_risk = self._assess_quality_risk(service)
        dependency_risk = self._assess_dependency_risk(service)
        drift_risk = self._assess_drift_risk(service)
        domain_risk = self._assess_domain_risk(service)
        coupling_risk = self._assess_coupling_risk(service)
        historical_risk = self._assess_historical_risk(service)

        return ServiceRiskFactors(
            service_name=service_name,
            maturity_risk=maturity_risk,
            quality_risk=quality_risk,
            dependency_risk=dependency_risk,
            drift_risk=drift_risk,
            domain_risk=domain_risk,
            coupling_risk=coupling_risk,
            historical_risk=historical_risk
        )

    def _assess_maturity_risk(self, service: Dict[str, Any]) -> float:
        """Assess risk based on service maturity."""
        maturity_levels = {
            'experimental': 0.8,
            'beta': 0.5,
            'stable': 0.2,
            'deprecated': 0.9
        }

        maturity = service.get('maturity', 'unknown')
        return maturity_levels.get(maturity, 0.5)

    def _assess_quality_risk(self, service: Dict[str, Any]) -> float:
        """Assess risk based on quality metrics."""
        quality_score = service.get('quality', {}).get('score', 50)

        # Invert quality score (lower quality = higher risk)
        # 100 = 0.0 risk, 0 = 1.0 risk
        return max(0.0, (100 - quality_score) / 100)

    def _assess_dependency_risk(self, service: Dict[str, Any]) -> float:
        """Assess risk based on dependencies."""
        dependencies = service.get('dependencies', {})
        internal_deps = len(dependencies.get('internal', []))
        external_deps = len(dependencies.get('external', []))

        # Risk increases with number of dependencies
        total_deps = internal_deps + external_deps

        if total_deps == 0:
            return 0.1  # Some risk even with no dependencies
        elif total_deps <= 3:
            return 0.3
        elif total_deps <= 6:
            return 0.6
        else:
            return 0.9

    def _assess_drift_risk(self, service: Dict[str, Any]) -> float:
        """Assess risk based on drift issues."""
        service_name = service['name']

        # Count drift issues for this service
        drift_issues = [
            issue for issue in self.drift_data.get('issues', [])
            if issue.get('service') == service_name
        ]

        # Risk based on issue count and severity
        high_severity = len([i for i in drift_issues if i.get('severity') in ['high', 'error']])
        total_issues = len(drift_issues)

        if total_issues == 0:
            return 0.1
        elif high_severity > 0:
            return 0.9
        elif total_issues >= 3:
            return 0.7
        else:
            return 0.4

    def _assess_domain_risk(self, service: Dict[str, Any]) -> float:
        """Assess risk based on domain sensitivity."""
        domain_risk_levels = {
            'access': 0.8,      # High security sensitivity
            'data-processing': 0.7,  # Data integrity critical
            'ml': 0.6,          # Algorithm sensitivity
            'shared': 0.5,      # Shared utilities
            'infrastructure': 0.4   # Infrastructure components
        }

        domain = service.get('domain', 'unknown')
        return domain_risk_levels.get(domain, 0.5)

    def _assess_coupling_risk(self, service: Dict[str, Any]) -> float:
        """Assess risk based on service coupling."""
        service_name = service['name']

        # Find services that depend on this service (fan-in)
        dependent_services = [
            s for s in self.catalog.get('services', [])
            if service_name in s.get('dependencies', {}).get('internal', [])
        ]

        fan_in = len(dependent_services)
        fan_out = len(service.get('dependencies', {}).get('internal', []))

        # High coupling risk if many services depend on this one
        if fan_in > 5:
            return 0.8
        elif fan_in > 2:
            return 0.6
        elif fan_out > 5:
            return 0.7
        else:
            return 0.3

    def _assess_historical_risk(self, service: Dict[str, Any]) -> float:
        """Assess risk based on historical failure patterns."""
        # Placeholder - in real implementation would check:
        # - Recent deployment failures
        # - Error rates from observability
        # - Past incident frequency

        # For now, base on staleness
        last_update = service.get('last_update')
        if last_update:
            try:
                update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                days_old = (datetime.now(timezone.utc) - update_time).days

                if days_old > 180:
                    return 0.8  # Very stale
                elif days_old > 90:
                    return 0.6  # Stale
                elif days_old > 30:
                    return 0.4  # Moderately old
                else:
                    return 0.2  # Recently updated
            except (ValueError, AttributeError):
                return 0.5
        else:
            return 0.7  # No update info

    def compute_service_risk_score(self, service_name: str) -> float:
        """Compute composite risk score for a service."""
        risk_factors = self.assess_service_risk(service_name)

        # Calculate weighted risk score
        total_risk = 0.0
        for factor_name, weight in self.risk_weights.items():
            factor_value = getattr(risk_factors, f"{factor_name}_risk")
            total_risk += factor_value * weight

        return min(100.0, total_risk * 100)

    def get_service_risk_level(self, service_name: str) -> RiskLevel:
        """Get risk level for a service."""
        risk_score = self.compute_service_risk_score(service_name)

        if risk_score >= 80:
            return RiskLevel.CRITICAL
        elif risk_score >= 60:
            return RiskLevel.HIGH
        elif risk_score >= 40:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def assess_change_risk(self, service_name: str, change_type: str, change_scope: str = "minor") -> ChangeRiskAssessment:
        """Assess risk for a proposed change."""
        logger.info(f"Assessing change risk for {service_name}: {change_type}")

        # Get base service risk
        service_risk_score = self.compute_service_risk_score(service_name)
        service_risk_level = self.get_service_risk_level(service_name)

        # Assess change-specific risks
        change_risk_factors = self._assess_change_specific_risks(service_name, change_type, change_scope)

        # Calculate impact radius
        impact_radius = self._calculate_impact_radius(service_name, change_type)

        # Compute composite risk
        base_risk = service_risk_score / 100  # Normalize to 0-1

        # Change type multiplier
        change_multipliers = {
            'spec_upgrade_patch': 0.3,
            'spec_upgrade_minor': 0.6,
            'spec_upgrade_major': 1.0,
            'dependency_add': 0.7,
            'dependency_remove': 0.8,
            'api_contract_change': 0.9,
            'event_schema_change': 0.8,
            'configuration_change': 0.4,
            'documentation_update': 0.2
        }

        change_multiplier = change_multipliers.get(change_type, 0.5)
        scope_multiplier = 1.0 if change_scope == "major" else 0.7 if change_scope == "medium" else 0.5

        composite_risk = (base_risk + (change_multiplier * scope_multiplier)) / 2
        composite_risk_score = min(100.0, composite_risk * 100)

        # Determine risk level
        if composite_risk_score >= 80:
            risk_level = RiskLevel.CRITICAL
        elif composite_risk_score >= 60:
            risk_level = RiskLevel.HIGH
        elif composite_risk_score >= 40:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        # Generate mitigation strategies
        mitigation_strategies = self._generate_mitigation_strategies(service_name, change_type, risk_level)

        # Determine required approvals
        required_approvals = self._determine_required_approvals(service_name, change_type, risk_level)

        return ChangeRiskAssessment(
            service_name=service_name,
            change_type=change_type,
            change_scope=change_scope,
            impact_radius=impact_radius,
            risk_factors=change_risk_factors,
            composite_risk_score=composite_risk_score,
            risk_level=risk_level,
            mitigation_strategies=mitigation_strategies,
            required_approvals=required_approvals
        )

    def _assess_change_specific_risks(self, service_name: str, change_type: str, change_scope: str) -> Dict[str, float]:
        """Assess change-specific risk factors."""
        factors = {
            'breaking_compatibility': 0.0,
            'dependency_impact': 0.0,
            'test_complexity': 0.0,
            'rollback_complexity': 0.0
        }

        if 'major' in change_type or change_scope == 'major':
            factors['breaking_compatibility'] = 0.9
            factors['test_complexity'] = 0.8
            factors['rollback_complexity'] = 0.7

        if 'dependency' in change_type:
            factors['dependency_impact'] = 0.8

        if 'api' in change_type or 'event' in change_type:
            factors['breaking_compatibility'] = 0.7
            factors['test_complexity'] = 0.9

        return factors

    def _calculate_impact_radius(self, service_name: str, change_type: str) -> int:
        """Calculate how many services would be impacted by the change."""
        # Find all services that depend on this service
        impacted = 0

        for service in self.catalog.get('services', []):
            if service_name in service.get('dependencies', {}).get('internal', []):
                impacted += 1

        # Add transitive dependencies (simplified)
        if 'api' in change_type or 'event' in change_type:
            impacted += 2  # Assume 2 additional services affected by contract changes

        return impacted

    def _generate_mitigation_strategies(self, service_name: str, change_type: str, risk_level: RiskLevel) -> List[str]:
        """Generate mitigation strategies for the change."""
        strategies = [
            "Run comprehensive test suite before deployment",
            "Have rollback plan ready",
            "Monitor service health closely post-deployment"
        ]

        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            strategies.extend([
                "Conduct peer review before implementation",
                "Create detailed implementation plan",
                "Schedule change during low-traffic period"
            ])

        if 'breaking' in change_type.lower():
            strategies.extend([
                "Communicate changes to dependent service owners",
                "Update API documentation",
                "Consider backward compatibility options"
            ])

        if 'dependency' in change_type:
            strategies.extend([
                "Verify all dependent services still build",
                "Check for version conflicts",
                "Update dependency documentation"
            ])

        return strategies

    def _determine_required_approvals(self, service_name: str, change_type: str, risk_level: RiskLevel) -> List[str]:
        """Determine who needs to approve the change."""
        approvals = []

        # Base approvals
        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            approvals.append("platform-team")

        if 'security' in change_type.lower() or 'auth' in change_type.lower():
            approvals.append("security-team")

        if 'api' in change_type.lower() or 'event' in change_type.lower():
            approvals.append("api-team")

        # Service-specific approvals
        service = next((s for s in self.catalog.get('services', []) if s['name'] == service_name), None)
        if service and service.get('domain') == 'access':
            approvals.append("access-team")

        if service and service.get('domain') == 'data-processing':
            approvals.append("data-team")

        return list(set(approvals))  # Remove duplicates

    def generate_risk_report(self, service_name: str, change_type: str = None, change_scope: str = "minor") -> Dict[str, Any]:
        """Generate comprehensive risk report."""
        logger.info(f"Generating risk report for {service_name}")

        # Assess service risk
        service_risk_factors = self.assess_service_risk(service_name)
        service_risk_score = self.compute_service_risk_score(service_name)
        service_risk_level = self.get_service_risk_level(service_name)

        # Assess change risk if specified
        change_assessment = None
        if change_type:
            change_assessment = self.assess_change_risk(service_name, change_type, change_scope)

        # Build report
        report = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'service_name': service_name,
                'assessment_type': 'change' if change_type else 'service'
            },
            'service_risk': {
                'composite_score': service_risk_score,
                'risk_level': service_risk_level.value,
                'risk_factors': asdict(service_risk_factors)
            },
            'recommendations': self._generate_risk_recommendations(service_risk_factors, service_risk_level)
        }

        if change_assessment:
            report['change_risk'] = asdict(change_assessment)
            report['overall_risk'] = {
                'composite_score': change_assessment.composite_risk_score,
                'risk_level': change_assessment.risk_level.value,
                'recommendation': self._get_overall_risk_recommendation(change_assessment.risk_level)
            }

        return report

    def _generate_risk_recommendations(self, risk_factors: ServiceRiskFactors, risk_level: RiskLevel) -> List[str]:
        """Generate risk mitigation recommendations."""
        recommendations = []

        # Quality-based recommendations
        if risk_factors.quality_risk > 0.7:
            recommendations.append("🔴 Critical: Improve service quality before making changes")

        if risk_factors.dependency_risk > 0.7:
            recommendations.append("🔶 High: Consider reducing service dependencies")

        if risk_factors.drift_risk > 0.6:
            recommendations.append("🟡 Medium: Address drift issues to reduce risk")

        if risk_factors.maturity_risk > 0.6:
            recommendations.append("🟠 Medium: Consider promoting service maturity level")

        # General recommendations based on risk level
        if risk_level == RiskLevel.CRITICAL:
            recommendations.append("🚨 Critical Risk: All changes require senior architect approval")
        elif risk_level == RiskLevel.HIGH:
            recommendations.append("⚠️ High Risk: Changes require technical lead approval")
        elif risk_level == RiskLevel.MEDIUM:
            recommendations.append("🟡 Medium Risk: Changes require peer review")
        else:
            recommendations.append("🟢 Low Risk: Standard development practices apply")

        return recommendations

    def _get_overall_risk_recommendation(self, risk_level: RiskLevel) -> str:
        """Get overall risk recommendation."""
        recommendations = {
            RiskLevel.CRITICAL: "🚫 DO NOT PROCEED - Critical risk level requires immediate attention",
            RiskLevel.HIGH: "⚠️ PROCEED WITH CAUTION - High risk requires careful planning and approval",
            RiskLevel.MEDIUM: "✅ PROCEED - Medium risk acceptable with standard procedures",
            RiskLevel.LOW: "✅ PROCEED - Low risk, standard development practices apply"
        }

        return recommendations.get(risk_level, "Unknown risk level")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Assess risk levels for services and changes")
    parser.add_argument("--service", required=True, help="Service name to assess")
    parser.add_argument("--change-type", help="Type of change being assessed")
    parser.add_argument("--change-scope", choices=["minor", "medium", "major"], default="minor",
                       help="Scope of change (default: minor)")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file")
    parser.add_argument("--drift-file", type=str, help="Path to drift report file")
    parser.add_argument("--quality-file", type=str, help="Path to quality snapshot file")
    parser.add_argument("--output-file", help="Output file for risk report")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        assessor = RiskAssessor(args.catalog_file, args.drift_file, args.quality_file)
        report = assessor.generate_risk_report(args.service, args.change_type, args.change_scope)

        # Save or print report
        if args.output_file:
            with open(args.output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Risk report saved to {args.output_file}")
        else:
            print(json.dumps(report, indent=2))

        # Print summary
        service_risk = report['service_risk']
        print("\n📊 Risk Assessment Summary:")
        print(f"  Service: {args.service}")
        print(f"  Risk Score: {service_risk['composite_score']:.1f}/100")
        print(f"  Risk Level: {service_risk['risk_level'].upper()}")

        if args.change_type:
            change_risk = report.get('change_risk', {})
            print(f"  Change Risk: {change_risk.get('composite_risk_score', 0):.1f}/100")
            print(f"  Impact Radius: {change_risk.get('impact_radius', 0)} services")
            print(f"  Recommendation: {report.get('overall_risk', {}).get('recommendation', 'Unknown')}")

        print("\n🎯 Recommendations:")
        for rec in report.get('recommendations', []):
            print(f"  {rec}")

    except Exception as e:
        logger.error(f"Risk assessment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
