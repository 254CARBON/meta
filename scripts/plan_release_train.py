#!/usr/bin/env python3
"""
254Carbon Meta Repository - Release Train Planner

Plans and validates coordinated multi-service releases ("release trains") with
basic quality gates, compatibility checks, and communication scaffolding.

Usage:
    python scripts/plan_release_train.py --train Q4-curve-upgrade [--dry-run]

Lifecycle:
- Loads train definitions from `catalog/release-trains.yaml` and correlates to
  current catalog entries. Validates quality/security gates and simple spec
  alignment, then proposes an execution sequence and estimates duration.

Outputs:
- Persists a timestamped JSON plan under `analysis/reports/release-trains/` and
  a `*_latest_plan.json` for quick access.
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
from dataclasses import dataclass, field
from enum import Enum


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/release-train-planning.log')
    ]
)
logger = logging.getLogger(__name__)


class ReleaseStatus(Enum):
    """Release train status."""
    PLANNING = "planning"
    VALIDATED = "validated"
    STAGING = "staging"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QualityGate:
    """Represents a quality gate requirement."""
    name: str
    description: str
    required: bool
    current_value: Any
    threshold: Any
    status: str = "unknown"


@dataclass
class ReleaseParticipant:
    """Represents a service participating in a release train."""
    name: str
    repo: str
    current_version: str
    target_version: str
    domain: str
    maturity: str
    dependencies: List[str]
    quality_score: float
    critical_vulns: int
    status: str = "pending"


@dataclass
class ReleaseTrain:
    """Represents a release train."""
    name: str
    description: str
    target_version: str
    participants: List[ReleaseParticipant] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    quality_gates: List[QualityGate] = field(default_factory=list)
    status: ReleaseStatus = ReleaseStatus.PLANNING
    estimated_duration: timedelta = timedelta(hours=2)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ReleaseTrainPlanner:
    """Plans and validates release trains."""

    def __init__(self, train_name: str, dry_run: bool = False):
        self.train_name = train_name
        self.dry_run = dry_run

        # Load catalog and release train definitions
        self.catalog = self._load_catalog()
        self.release_trains = self._load_release_trains()

        # Find the specified train
        self.train = self._find_release_train(train_name)
        if not self.train:
            raise ValueError(f"Release train '{train_name}' not found")

    def _load_catalog(self) -> Dict[str, Any]:
        """Load service catalog."""
        catalog_path = Path("catalog/service-index.yaml")

        if not catalog_path.exists():
            raise FileNotFoundError("Catalog not found. Run 'make build-catalog' first.")

        with open(catalog_path) as f:
            return yaml.safe_load(f)

    def _load_release_trains(self) -> Dict[str, ReleaseTrain]:
        """Load release train definitions."""
        trains_file = Path("catalog/release-trains.yaml")

        if not trains_file.exists():
            logger.warning(f"Release trains file not found: {trains_file}")
            return {}

        with open(trains_file) as f:
            trains_data = yaml.safe_load(f)

        trains = {}
        for train_data in trains_data.get('trains', []):
            train = ReleaseTrain(
                name=train_data['name'],
                description=train_data.get('description', ''),
                target_version=train_data['target_version'],
                participants=self._build_participants(train_data.get('participants', [])),
                dependencies=train_data.get('dependencies', []),
                quality_gates=self._build_quality_gates(train_data.get('gates', [])),
                status=ReleaseStatus(train_data.get('status', 'planning'))
            )
            trains[train.name] = train

        return trains

    def _find_release_train(self, train_name: str) -> Optional[ReleaseTrain]:
        """Find release train by name."""
        return self.release_trains.get(train_name)

    def _build_participants(self, participant_names: List[str]) -> List[ReleaseParticipant]:
        """Build release participants from service names."""
        participants = []
        services = self.catalog.get('services', [])

        for name in participant_names:
            service = next((s for s in services if s['name'] == name), None)
            if service:
                participant = ReleaseParticipant(
                    name=service['name'],
                    repo=service['repo'],
                    current_version=service['version'],
                    target_version="",  # Would be determined from train target
                    domain=service['domain'],
                    maturity=service['maturity'],
                    dependencies=service.get('dependencies', {}).get('internal', []),
                    quality_score=service.get('quality', {}).get('score', 0),
                    critical_vulns=service.get('quality', {}).get('open_critical_vulns', 0)
                )
                participants.append(participant)
            else:
                logger.warning(f"Service not found in catalog: {name}")

        return participants

    def _build_quality_gates(self, gate_configs: List[Dict[str, Any]]) -> List[QualityGate]:
        """Build quality gates from configuration."""
        gates = []

        for gate_config in gate_configs:
            gate_name = gate_config.get('name', 'unknown')
            gate_type = gate_config.get('type', 'unknown')

            if gate_type == 'quality_score':
                gate = QualityGate(
                    name=gate_name,
                    description=gate_config.get('description', ''),
                    required=True,
                    current_value=0,  # Will be calculated
                    threshold=gate_config.get('threshold', 80)
                )
            elif gate_type == 'vulnerabilities':
                gate = QualityGate(
                    name=gate_name,
                    description=gate_config.get('description', ''),
                    required=True,
                    current_value=0,  # Will be calculated
                    threshold=gate_config.get('max_vulns', 0)
                )
            else:
                logger.warning(f"Unknown gate type: {gate_type}")
                continue

            gates.append(gate)

        return gates

    def validate_participant_compatibility(self) -> List[str]:
        """Validate that participants are compatible for joint release."""
        logger.info("Validating participant compatibility...")
        issues = []

        participants = self.train.participants

        # Check for conflicting dependencies
        for i, participant in enumerate(participants):
            for j, other in enumerate(participants):
                if i != j:
                    # Check if they depend on each other (would create cycle)
                    if participant.name in other.dependencies or other.name in participant.dependencies:
                        issues.append(
                            f"Dependency conflict: {participant.name} and {other.name} depend on each other"
                        )

        # Check for incompatible maturity levels
        maturities = [p.maturity for p in participants]
        if 'experimental' in maturities and 'stable' in maturities:
            issues.append(
                "Maturity mismatch: Experimental and stable services in same release train"
            )

        # Check for domain cohesion
        domains = set(p.domain for p in participants)
        if len(domains) > 2:
            issues.append(
                f"Domain sprawl: Participants span {len(domains)} domains, may lack cohesion"
            )

        return issues

    def check_quality_gates(self) -> Tuple[bool, List[str]]:
        """Check if all quality gates are satisfied."""
        logger.info("Checking quality gates...")
        issues = []
        all_passed = True

        for gate in self.train.quality_gates:
            if gate.name == 'quality_score':
                # Check average quality score
                avg_score = sum(p.quality_score for p in self.train.participants) / len(self.train.participants)
                gate.current_value = avg_score
                gate.status = "passed" if avg_score >= gate.threshold else "failed"

                if gate.status == "failed":
                    issues.append(f"Quality gate failed: Average score {avg_score:.1f} < {gate.threshold}")
                    all_passed = False

            elif gate.name == 'vulnerabilities':
                # Check total critical vulnerabilities
                total_vulns = sum(p.critical_vulns for p in self.train.participants)
                gate.current_value = total_vulns
                gate.status = "passed" if total_vulns <= gate.threshold else "failed"

                if gate.status == "failed":
                    issues.append(f"Security gate failed: {total_vulns} critical vulnerabilities > {gate.threshold}")
                    all_passed = False

        return all_passed, issues

    def verify_spec_alignment(self) -> List[str]:
        """Verify spec version alignment across participants."""
        logger.info("Verifying spec version alignment...")
        issues = []

        # In a real implementation, this would check that all participants
        # have compatible spec versions for their dependencies

        # For now, we'll do a basic check
        participants = self.train.participants

        for participant in participants:
            # Check if participant has API contracts that might need alignment
            api_contracts = self._get_service_api_contracts(participant.name)

            for contract in api_contracts:
                if '@' in contract:
                    spec_name, version = contract.split('@', 1)

                    # Check if other participants use the same spec
                    for other in participants:
                        if other.name != participant.name:
                            other_contracts = self._get_service_api_contracts(other.name)
                            for other_contract in other_contracts:
                                if other_contract.startswith(f"{spec_name}@"):
                                    other_version = other_contract.split('@', 1)[1]

                                    # Check version compatibility
                                    if not self._versions_compatible(version, other_version):
                                        issues.append(
                                            f"Spec version mismatch: {participant.name}@{version} vs {other.name}@{other_version}"
                                        )

        return issues

    def _get_service_api_contracts(self, service_name: str) -> List[str]:
        """Get API contracts for a service (placeholder)."""
        # In real implementation, this would read from service manifests
        return []

    def _versions_compatible(self, version1: str, version2: str) -> bool:
        """Check if two spec versions are compatible."""
        # Simple compatibility check - in reality would be more sophisticated
        return version1 == version2

    def calculate_release_sequence(self) -> List[ReleaseParticipant]:
        """Calculate the optimal release sequence."""
        logger.info("Calculating release sequence...")

        participants = self.train.participants.copy()

        # Sort by dependency order (topological sort)
        # For now, we'll use a simple heuristic
        sorted_participants = sorted(participants, key=lambda p: len(p.dependencies))

        # Group by domain for wave-based releases
        by_domain = {}
        for participant in sorted_participants:
            domain = participant.domain
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(participant)

        # Flatten back to sequence, prioritizing infrastructure dependencies
        sequence = []
        domain_priority = {'infrastructure': 0, 'shared': 1, 'access': 2, 'data-processing': 3, 'ml': 4}

        for domain in sorted(by_domain.keys(), key=lambda d: domain_priority.get(d, 999)):
            sequence.extend(by_domain[domain])

        return sequence

    def estimate_release_duration(self) -> timedelta:
        """Estimate total release duration."""
        # Base duration plus per-participant time
        base_duration = timedelta(minutes=30)  # Setup and validation
        per_participant = timedelta(minutes=15)  # Per service deployment

        total_duration = base_duration + (per_participant * len(self.train.participants))

        return total_duration

    def generate_release_plan(self) -> Dict[str, Any]:
        """Generate comprehensive release plan."""
        logger.info(f"Generating release plan for train: {self.train.name}")

        # Run validations
        compatibility_issues = self.validate_participant_compatibility()
        quality_passed, quality_issues = self.check_quality_gates()
        spec_issues = self.verify_spec_alignment()

        # Calculate sequence
        release_sequence = self.calculate_release_sequence()

        # Update train with calculated data
        self.train.estimated_duration = self.estimate_release_duration()

        # Build comprehensive plan
        plan = {
            'train': {
                'name': self.train.name,
                'description': self.train.description,
                'target_version': self.train.target_version,
                'status': self.train.status.value,
                'estimated_duration': str(self.train.estimated_duration),
                'created_at': self.train.created_at.isoformat(),
                'participants_count': len(self.train.participants)
            },
            'validation': {
                'overall_passed': quality_passed and not compatibility_issues and not spec_issues,
                'compatibility_issues': compatibility_issues,
                'quality_gates_passed': quality_passed,
                'quality_issues': quality_issues,
                'spec_alignment_passed': not spec_issues,
                'spec_issues': spec_issues
            },
            'participants': [
                {
                    'name': p.name,
                    'domain': p.domain,
                    'maturity': p.maturity,
                    'current_version': p.current_version,
                    'quality_score': p.quality_score,
                    'critical_vulns': p.critical_vulns,
                    'dependencies': p.dependencies,
                    'release_order': release_sequence.index(p) + 1
                }
                for p in self.train.participants
            ],
            'release_sequence': [
                {
                    'order': i + 1,
                    'service': p.name,
                    'estimated_start': (datetime.now(timezone.utc) + timedelta(minutes=i * 15)).isoformat(),
                    'estimated_duration': '15 minutes'
                }
                for i, p in enumerate(release_sequence)
            ],
            'quality_gates': [
                {
                    'name': g.name,
                    'description': g.description,
                    'required': g.required,
                    'current_value': g.current_value,
                    'threshold': g.threshold,
                    'status': g.status
                }
                for g in self.train.quality_gates
            ],
            'risk_assessment': self._assess_risks(),
            'rollback_plan': self._generate_rollback_plan(),
            'communication_plan': self._generate_communication_plan()
        }

        return plan

    def _assess_risks(self) -> Dict[str, Any]:
        """Assess risks for the release train."""
        risks = []

        # High-risk participants
        high_risk = [p for p in self.train.participants if p.maturity == 'experimental']
        if high_risk:
            risks.append({
                'level': 'medium',
                'description': f"{len(high_risk)} experimental services in release",
                'mitigation': 'Monitor closely during deployment'
            })

        # Quality concerns
        low_quality = [p for p in self.train.participants if p.quality_score < 70]
        if low_quality:
            risks.append({
                'level': 'high',
                'description': f"{len(low_quality)} services below quality threshold",
                'mitigation': 'Consider postponing until quality improves'
            })

        # Security concerns
        vuln_services = [p for p in self.train.participants if p.critical_vulns > 0]
        if vuln_services:
            risks.append({
                'level': 'high',
                'description': f"{len(vuln_services)} services have critical vulnerabilities",
                'mitigation': 'Security review required before proceeding'
            })

        return {
            'overall_risk': 'high' if any(r['level'] == 'high' for r in risks) else 'medium',
            'risks': risks
        }

    def _generate_rollback_plan(self) -> Dict[str, Any]:
        """Generate rollback plan."""
        return {
            'strategy': 'Sequential rollback of participants',
            'steps': [
                f"Rollback {p.name} to previous version" for p in self.train.participants
            ],
            'estimated_time': '30 minutes',
            'verification_steps': [
                'Verify all services return to previous state',
                'Confirm no data loss',
                'Validate dependent services still function'
            ]
        }

    def _generate_communication_plan(self) -> Dict[str, Any]:
        """Generate communication plan."""
        return {
            'stakeholders': [
                'Platform Team',
                'Service Owners',
                'Product Teams',
                'Operations Team'
            ],
            'notifications': [
                {
                    'event': 'Release Start',
                    'channels': ['Slack #releases', 'Email stakeholders'],
                    'message': f'Release train {self.train.name} starting'
                },
                {
                    'event': 'Release Complete',
                    'channels': ['Slack #releases', 'Email stakeholders'],
                    'message': f'Release train {self.train.name} completed successfully'
                },
                {
                    'event': 'Release Issues',
                    'channels': ['Slack #platform-alerts', 'PagerDuty'],
                    'message': f'Issues detected in release train {self.train.name}'
                }
            ]
        }

    def save_release_plan(self, plan: Dict[str, Any]) -> None:
        """Save release plan to file."""
        plans_dir = Path("analysis/reports/release-trains")
        plans_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plan_file = plans_dir / f"{self.train_name}_{timestamp}_plan.json"

        with open(plan_file, 'w') as f:
            json.dump(plan, f, indent=2)

        logger.info(f"Saved release plan to {plan_file}")

        # Update latest plan
        latest_file = plans_dir / f"{self.train_name}_latest_plan.json"
        with open(latest_file, 'w') as f:
            json.dump(plan, f, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Plan release train execution")
    parser.add_argument("--train", required=True, help="Release train name to plan")
    parser.add_argument("--dry-run", action="store_true", help="Validate plan without saving")
    parser.add_argument("--output-file", help="Output file for release plan")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        planner = ReleaseTrainPlanner(args.train, args.dry_run)
        plan = planner.generate_release_plan()

        if args.dry_run:
            logger.info("✅ Release plan validation completed (dry run)")
        else:
            if args.output_file:
                with open(args.output_file, 'w') as f:
                    json.dump(plan, f, indent=2)
            else:
                planner.save_release_plan(plan)

            logger.info("✅ Release plan generated successfully")

        # Print summary
        print("\n📋 Release Plan Summary:")
        print(f"  Train: {plan['train']['name']}")
        print(f"  Participants: {plan['train']['participants_count']}")
        print(f"  Status: {plan['validation']['overall_passed'] and '✅ Ready' or '❌ Issues Found'}")
        print(f"  Estimated Duration: {plan['train']['estimated_duration']}")

        if plan['validation']['compatibility_issues']:
            print(f"  Compatibility Issues: {len(plan['validation']['compatibility_issues'])}")

        if plan['validation']['quality_issues']:
            print(f"  Quality Issues: {len(plan['validation']['quality_issues'])}")

        if plan['validation']['spec_issues']:
            print(f"  Spec Issues: {len(plan['validation']['spec_issues'])}")

    except Exception as e:
        logger.error(f"Release planning failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
