#!/usr/bin/env python3
"""
254Carbon Meta Repository - Quality Enforcer

Automatically enforces quality gates and blocks deployments below quality thresholds.
Provides quality scoring, gate validation, and automated quality improvement suggestions.

Usage:
    python scripts/sre/quality_enforcer.py --service gateway --enforce-gates
    python scripts/sre/quality_enforcer.py --all-services --threshold 80
    python scripts/sre/quality_enforcer.py --service auth-service --block-deployment

Features:
- Quality gate enforcement
- Deployment blocking for low-quality services
- Automated quality improvement suggestions
- Quality trend monitoring
- Integration with CI/CD pipelines
- Comprehensive quality reporting
"""

import os
import sys
import json
import yaml
import argparse
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import subprocess

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from scripts.utils import audit_logger, monitor_execution
from scripts.send_notifications import NotificationSender, NotificationMessage, NotificationSeverity, NotificationChannel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/quality-enforcement.log')
    ]
)
logger = logging.getLogger(__name__)


class QualityGate(Enum):
    """Quality gate types."""
    TEST_COVERAGE = "test_coverage"
    SECURITY_SCORE = "security_score"
    LINTING_PASS = "linting_pass"
    POLICY_COMPLIANCE = "policy_compliance"
    DRIFT_PENALTY = "drift_penalty"
    OVERALL_SCORE = "overall_score"


class EnforcementAction(Enum):
    """Quality enforcement actions."""
    BLOCK_DEPLOYMENT = "block_deployment"
    WARN_DEPLOYMENT = "warn_deployment"
    ALLOW_DEPLOYMENT = "allow_deployment"
    REQUIRE_APPROVAL = "require_approval"
    AUTO_FIX = "auto_fix"


@dataclass
class QualityGateResult:
    """Result of quality gate check."""
    gate: QualityGate
    passed: bool
    current_value: float
    threshold: float
    message: str
    enforcement_action: EnforcementAction
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityEnforcementResult:
    """Result of quality enforcement for a service."""
    service_name: str
    overall_passed: bool
    overall_score: float
    gate_results: List[QualityGateResult]
    enforcement_action: EnforcementAction
    deployment_blocked: bool
    improvement_suggestions: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class QualityEnforcer:
    """Quality enforcement engine."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the quality enforcer."""
        self.config_path = config_path or 'config/quality-gates.yaml'
        self.config = self._load_config()
        self.notification_sender = NotificationSender()
        
        # Default quality thresholds
        self.default_thresholds = {
            QualityGate.TEST_COVERAGE: 75.0,
            QualityGate.SECURITY_SCORE: 90.0,
            QualityGate.LINTING_PASS: 100.0,
            QualityGate.POLICY_COMPLIANCE: 100.0,
            QualityGate.DRIFT_PENALTY: 0.0,
            QualityGate.OVERALL_SCORE: 80.0
        }
        
        # Enforcement actions based on score ranges
        self.enforcement_ranges = {
            (90, 100): EnforcementAction.ALLOW_DEPLOYMENT,
            (80, 89): EnforcementAction.WARN_DEPLOYMENT,
            (70, 79): EnforcementAction.REQUIRE_APPROVAL,
            (60, 69): EnforcementAction.BLOCK_DEPLOYMENT,
            (0, 59): EnforcementAction.BLOCK_DEPLOYMENT
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """Load quality gate configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Quality gate config not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing quality gate config: {e}")
            return {}
    
    def enforce_quality_gates(self, service_name: str, threshold: Optional[float] = None) -> QualityEnforcementResult:
        """Enforce quality gates for a specific service."""
        logger.info(f"Enforcing quality gates for service: {service_name}")
        
        try:
            # Get quality data for the service
            quality_data = self._get_service_quality_data(service_name)
            if not quality_data:
                return QualityEnforcementResult(
                    service_name=service_name,
                    overall_passed=False,
                    overall_score=0.0,
                    gate_results=[],
                    enforcement_action=EnforcementAction.BLOCK_DEPLOYMENT,
                    deployment_blocked=True,
                    improvement_suggestions=["No quality data available"]
                )
            
            # Check each quality gate
            gate_results = []
            for gate in QualityGate:
                result = self._check_quality_gate(service_name, gate, quality_data, threshold)
                gate_results.append(result)
            
            # Calculate overall score and enforcement action
            overall_score = quality_data.get('score', 0.0)
            overall_passed = all(result.passed for result in gate_results)
            enforcement_action = self._determine_enforcement_action(overall_score)
            deployment_blocked = enforcement_action in [EnforcementAction.BLOCK_DEPLOYMENT]
            
            # Generate improvement suggestions
            improvement_suggestions = self._generate_improvement_suggestions(gate_results, quality_data)
            
            result = QualityEnforcementResult(
                service_name=service_name,
                overall_passed=overall_passed,
                overall_score=overall_score,
                gate_results=gate_results,
                enforcement_action=enforcement_action,
                deployment_blocked=deployment_blocked,
                improvement_suggestions=improvement_suggestions,
                metadata=quality_data
            )
            
            # Send notifications if needed
            self._send_quality_notifications(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error enforcing quality gates for {service_name}: {e}")
            return QualityEnforcementResult(
                service_name=service_name,
                overall_passed=False,
                overall_score=0.0,
                gate_results=[],
                enforcement_action=EnforcementAction.BLOCK_DEPLOYMENT,
                deployment_blocked=True,
                improvement_suggestions=[f"Error: {str(e)}"]
            )
    
    def enforce_all_services(self, threshold: Optional[float] = None) -> Dict[str, QualityEnforcementResult]:
        """Enforce quality gates for all services."""
        logger.info("Enforcing quality gates for all services")
        
        # Get all services
        services = self._get_all_services()
        if not services:
            logger.warning("No services found for quality enforcement")
            return {}
        
        # Enforce quality gates for each service
        results = {}
        for service_name in services:
            try:
                result = self.enforce_quality_gates(service_name, threshold)
                results[service_name] = result
            except Exception as e:
                logger.error(f"Error enforcing quality gates for {service_name}: {e}")
                results[service_name] = QualityEnforcementResult(
                    service_name=service_name,
                    overall_passed=False,
                    overall_score=0.0,
                    gate_results=[],
                    enforcement_action=EnforcementAction.BLOCK_DEPLOYMENT,
                    deployment_blocked=True,
                    improvement_suggestions=[f"Error: {str(e)}"]
                )
        
        # Send summary notification
        self._send_summary_notification(results)
        
        return results
    
    def _get_service_quality_data(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get quality data for a specific service."""
        try:
            # Load quality data
            quality_file = Path('catalog/latest_quality_snapshot.json')
            if not quality_file.exists():
                logger.warning("No quality data found")
                return None
            
            with open(quality_file, 'r') as f:
                quality_data = json.load(f)
            
            service_data = quality_data.get('services', {}).get(service_name, {})
            return service_data if service_data else None
            
        except Exception as e:
            logger.error(f"Error getting quality data for {service_name}: {e}")
            return None
    
    def _check_quality_gate(self, service_name: str, gate: QualityGate, 
                           quality_data: Dict[str, Any], threshold: Optional[float] = None) -> QualityGateResult:
        """Check a specific quality gate."""
        try:
            # Get threshold for this gate
            gate_threshold = threshold or self.config.get('thresholds', {}).get(gate.value, self.default_thresholds[gate])
            
            # Get current value based on gate type
            if gate == QualityGate.TEST_COVERAGE:
                current_value = quality_data.get('coverage', 0.0) * 100
            elif gate == QualityGate.SECURITY_SCORE:
                current_value = quality_data.get('security_score', 0.0)
            elif gate == QualityGate.LINTING_PASS:
                current_value = 100.0 if quality_data.get('lint_pass', False) else 0.0
            elif gate == QualityGate.POLICY_COMPLIANCE:
                current_value = quality_data.get('policy_compliance', 0.0)
            elif gate == QualityGate.DRIFT_PENALTY:
                current_value = quality_data.get('drift_penalty', 0.0)
            elif gate == QualityGate.OVERALL_SCORE:
                current_value = quality_data.get('score', 0.0)
            else:
                current_value = 0.0
            
            # Determine if gate passed
            passed = current_value >= gate_threshold
            
            # Generate message
            if passed:
                message = f"{gate.value} gate passed: {current_value:.1f} >= {gate_threshold:.1f}"
            else:
                message = f"{gate.value} gate failed: {current_value:.1f} < {gate_threshold:.1f}"
            
            # Determine enforcement action
            enforcement_action = self._determine_gate_enforcement_action(gate, current_value, gate_threshold)
            
            return QualityGateResult(
                gate=gate,
                passed=passed,
                current_value=current_value,
                threshold=gate_threshold,
                message=message,
                enforcement_action=enforcement_action,
                metadata={'service_name': service_name}
            )
            
        except Exception as e:
            logger.error(f"Error checking quality gate {gate.value}: {e}")
            return QualityGateResult(
                gate=gate,
                passed=False,
                current_value=0.0,
                threshold=0.0,
                message=f"Error checking {gate.value}: {str(e)}",
                enforcement_action=EnforcementAction.BLOCK_DEPLOYMENT
            )
    
    def _determine_enforcement_action(self, overall_score: float) -> EnforcementAction:
        """Determine enforcement action based on overall score."""
        for (min_score, max_score), action in self.enforcement_ranges.items():
            if min_score <= overall_score <= max_score:
                return action
        
        return EnforcementAction.BLOCK_DEPLOYMENT
    
    def _determine_gate_enforcement_action(self, gate: QualityGate, current_value: float, threshold: float) -> EnforcementAction:
        """Determine enforcement action for a specific gate."""
        if current_value >= threshold:
            return EnforcementAction.ALLOW_DEPLOYMENT
        elif current_value >= threshold * 0.8:  # Within 20% of threshold
            return EnforcementAction.WARN_DEPLOYMENT
        elif current_value >= threshold * 0.6:  # Within 40% of threshold
            return EnforcementAction.REQUIRE_APPROVAL
        else:
            return EnforcementAction.BLOCK_DEPLOYMENT
    
    def _generate_improvement_suggestions(self, gate_results: List[QualityGateResult], 
                                        quality_data: Dict[str, Any]) -> List[str]:
        """Generate improvement suggestions based on gate results."""
        suggestions = []
        
        for result in gate_results:
            if not result.passed:
                if result.gate == QualityGate.TEST_COVERAGE:
                    suggestions.append(f"Increase test coverage from {result.current_value:.1f}% to {result.threshold:.1f}%")
                elif result.gate == QualityGate.SECURITY_SCORE:
                    suggestions.append(f"Fix security vulnerabilities to improve score from {result.current_value:.1f} to {result.threshold:.1f}")
                elif result.gate == QualityGate.LINTING_PASS:
                    suggestions.append("Fix linting issues to pass quality gates")
                elif result.gate == QualityGate.POLICY_COMPLIANCE:
                    suggestions.append("Address policy compliance violations")
                elif result.gate == QualityGate.DRIFT_PENALTY:
                    suggestions.append("Update dependencies to reduce drift penalty")
                elif result.gate == QualityGate.OVERALL_SCORE:
                    suggestions.append(f"Improve overall quality score from {result.current_value:.1f} to {result.threshold:.1f}")
        
        # Add general suggestions
        if quality_data.get('vuln_critical', 0) > 0:
            suggestions.append("Fix critical security vulnerabilities immediately")
        if quality_data.get('vuln_high', 0) > 0:
            suggestions.append("Address high-severity security vulnerabilities")
        if quality_data.get('coverage', 0) < 0.75:
            suggestions.append("Increase test coverage to at least 75%")
        if quality_data.get('lint_pass', False) == False:
            suggestions.append("Fix all linting issues")
        
        return suggestions
    
    def _get_all_services(self) -> List[str]:
        """Get list of all services."""
        try:
            catalog_file = Path('catalog/service-index.yaml')
            if not catalog_file.exists():
                return []
            
            with open(catalog_file, 'r') as f:
                catalog_data = yaml.safe_load(f)
            
            services = catalog_data.get('services', [])
            return [service.get('name') for service in services if service.get('name')]
            
        except Exception as e:
            logger.error(f"Error getting services: {e}")
            return []
    
    def _send_quality_notifications(self, result: QualityEnforcementResult):
        """Send notifications about quality enforcement results."""
        try:
            if result.deployment_blocked:
                # Send high-priority notification for blocked deployments
                message = NotificationMessage(
                    title=f"Deployment Blocked - {result.service_name}",
                    content=f"Deployment blocked due to quality gate failures. Score: {result.overall_score:.1f}",
                    severity=NotificationSeverity.HIGH,
                    channel=NotificationChannel.SLACK,
                    metadata={
                        'service_name': result.service_name,
                        'overall_score': result.overall_score,
                        'enforcement_action': result.enforcement_action.value,
                        'event_type': 'deployment_blocked'
                    }
                )
                self.notification_sender.send_notification(message)
                
                # Also send to PagerDuty for critical issues
                if result.overall_score < 60:
                    message = NotificationMessage(
                        title=f"CRITICAL: Quality Gate Failure - {result.service_name}",
                        content=f"Critical quality gate failure. Score: {result.overall_score:.1f}",
                        severity=NotificationSeverity.CRITICAL,
                        channel=NotificationChannel.PAGERDUTY,
                        metadata={
                            'service_name': result.service_name,
                            'overall_score': result.overall_score,
                            'event_type': 'critical_quality_failure'
                        }
                    )
                    self.notification_sender.send_notification(message)
            
            elif result.enforcement_action == EnforcementAction.WARN_DEPLOYMENT:
                # Send warning notification
                message = NotificationMessage(
                    title=f"Quality Warning - {result.service_name}",
                    content=f"Quality score below optimal threshold. Score: {result.overall_score:.1f}",
                    severity=NotificationSeverity.MEDIUM,
                    channel=NotificationChannel.SLACK,
                    metadata={
                        'service_name': result.service_name,
                        'overall_score': result.overall_score,
                        'event_type': 'quality_warning'
                    }
                )
                self.notification_sender.send_notification(message)
                
        except Exception as e:
            logger.error(f"Error sending quality notifications: {e}")
    
    def _send_summary_notification(self, results: Dict[str, QualityEnforcementResult]):
        """Send summary notification for all quality enforcement results."""
        try:
            total_services = len(results)
            passed_services = len([r for r in results.values() if r.overall_passed])
            blocked_services = len([r for r in results.values() if r.deployment_blocked])
            failed_services = total_services - passed_services
            
            # Calculate average score
            if results:
                average_score = sum(r.overall_score for r in results.values()) / len(results)
            else:
                average_score = 0.0
            
            message = NotificationMessage(
                title="Quality Gate Enforcement Summary",
                content=f"Quality gates enforced for {total_services} services. "
                       f"Passed: {passed_services}, Failed: {failed_services}, "
                       f"Blocked: {blocked_services}. Average score: {average_score:.1f}",
                severity=NotificationSeverity.MEDIUM,
                channel=NotificationChannel.SLACK,
                metadata={
                    'total_services': total_services,
                    'passed_services': passed_services,
                    'failed_services': failed_services,
                    'blocked_services': blocked_services,
                    'average_score': average_score,
                    'event_type': 'quality_enforcement_summary'
                }
            )
            self.notification_sender.send_notification(message)
            
        except Exception as e:
            logger.error(f"Error sending summary notification: {e}")
    
    def block_deployment(self, service_name: str) -> bool:
        """Block deployment for a service."""
        try:
            # Check if service should be blocked
            result = self.enforce_quality_gates(service_name)
            
            if result.deployment_blocked:
                logger.info(f"Deployment blocked for {service_name} due to quality gate failures")
                
                # Create deployment block record
                block_record = {
                    'service_name': service_name,
                    'blocked_at': datetime.now(timezone.utc).isoformat(),
                    'reason': 'Quality gate failure',
                    'score': result.overall_score,
                    'failed_gates': [r.gate.value for r in result.gate_results if not r.passed]
                }
                
                # Save block record
                block_file = Path('analysis/reports/deployment-blocks.json')
                block_file.parent.mkdir(parents=True, exist_ok=True)
                
                blocks = []
                if block_file.exists():
                    with open(block_file, 'r') as f:
                        blocks = json.load(f)
                
                blocks.append(block_record)
                
                with open(block_file, 'w') as f:
                    json.dump(blocks, f, indent=2)
                
                return True
            else:
                logger.info(f"Deployment allowed for {service_name}")
                return False
                
        except Exception as e:
            logger.error(f"Error blocking deployment for {service_name}: {e}")
            return False
    
    def get_improvement_suggestions(self, service_name: str) -> List[str]:
        """Get improvement suggestions for a service."""
        try:
            result = self.enforce_quality_gates(service_name)
            return result.improvement_suggestions
        except Exception as e:
            logger.error(f"Error getting improvement suggestions for {service_name}: {e}")
            return [f"Error: {str(e)}"]


def main():
    """Main entry point for quality enforcement."""
    parser = argparse.ArgumentParser(description='Quality gate enforcement')
    parser.add_argument('--service', help='Service name to enforce quality gates')
    parser.add_argument('--all-services', action='store_true', help='Enforce quality gates for all services')
    parser.add_argument('--threshold', type=float, help='Quality threshold (0-100)')
    parser.add_argument('--enforce-gates', action='store_true', help='Enforce quality gates')
    parser.add_argument('--block-deployment', action='store_true', help='Block deployment if quality gates fail')
    parser.add_argument('--improvement-suggestions', action='store_true', help='Get improvement suggestions')
    parser.add_argument('--config', default='config/quality-gates.yaml', help='Quality gate config file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    if not args.service and not args.all_services:
        parser.error("Must specify --service or --all-services")
    
    # Initialize quality enforcer
    enforcer = QualityEnforcer(args.config)
    
    try:
        if args.service:
            # Enforce quality gates for single service
            result = enforcer.enforce_quality_gates(args.service, args.threshold)
            
            print(f"\nQuality Gate Results for {args.service}:")
            print(f"Overall Score: {result.overall_score:.1f}")
            print(f"Overall Passed: {result.overall_passed}")
            print(f"Enforcement Action: {result.enforcement_action.value}")
            print(f"Deployment Blocked: {result.deployment_blocked}")
            
            print(f"\nGate Results:")
            for gate_result in result.gate_results:
                status = "PASS" if gate_result.passed else "FAIL"
                print(f"  {gate_result.gate.value}: {status} ({gate_result.current_value:.1f}/{gate_result.threshold:.1f})")
            
            if result.improvement_suggestions:
                print(f"\nImprovement Suggestions:")
                for suggestion in result.improvement_suggestions:
                    print(f"  - {suggestion}")
            
            if args.block_deployment:
                blocked = enforcer.block_deployment(args.service)
                print(f"\nDeployment Blocked: {blocked}")
            
            if args.improvement_suggestions:
                suggestions = enforcer.get_improvement_suggestions(args.service)
                print(f"\nImprovement Suggestions:")
                for suggestion in suggestions:
                    print(f"  - {suggestion}")
        
        else:
            # Enforce quality gates for all services
            results = enforcer.enforce_all_services(args.threshold)
            
            print(f"\nQuality Gate Summary:")
            print(f"Total services: {len(results)}")
            
            passed_services = 0
            blocked_services = 0
            total_score = 0
            
            for service_name, result in results.items():
                if result.overall_passed:
                    passed_services += 1
                if result.deployment_blocked:
                    blocked_services += 1
                total_score += result.overall_score
                
                print(f"  {service_name}: {result.overall_score:.1f} ({'PASS' if result.overall_passed else 'FAIL'})")
            
            if results:
                average_score = total_score / len(results)
                print(f"\nAverage Score: {average_score:.1f}")
                print(f"Passed Services: {passed_services}")
                print(f"Blocked Services: {blocked_services}")
        
    except Exception as e:
        logger.error(f"Quality enforcement failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
