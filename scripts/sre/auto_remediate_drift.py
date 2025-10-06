#!/usr/bin/env python3
"""
254Carbon Meta Repository - Automated Drift Remediation

Automatically remediates drift issues by creating PRs, updating dependencies,
and resolving common drift problems without human intervention.

Usage:
    python scripts/sre/auto_remediate_drift.py --service gateway --risk-level low
    python scripts/sre/auto_remediate_drift.py --service auth-service --risk-level medium --require-approval
    python scripts/sre/auto_remediate_drift.py --all-services --risk-level low --dry-run

Features:
- Automated PR creation for drift fixes
- Risk-based remediation strategies
- Approval workflows for medium/high risk changes
- Integration with notification system
- Rollback capabilities
- Comprehensive logging and audit trails
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
import tempfile
import shutil

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
        logging.FileHandler('analysis/reports/auto-remediation.log')
    ]
)
logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk levels for automated remediation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RemediationAction(Enum):
    """Types of remediation actions."""
    UPDATE_DEPENDENCY = "update_dependency"
    UPDATE_LOCK_FILE = "update_lock_file"
    UPDATE_SERVICE_MANIFEST = "update_service_manifest"
    FIX_LINTING = "fix_linting"
    UPDATE_SECURITY = "update_security"
    ROLLBACK = "rollback"


@dataclass
class DriftIssue:
    """Represents a drift issue to be remediated."""
    service_name: str
    issue_type: str
    severity: str
    description: str
    current_version: str
    target_version: str
    risk_level: RiskLevel
    remediation_action: RemediationAction
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RemediationResult:
    """Result of remediation action."""
    success: bool
    action: RemediationAction
    service_name: str
    pr_url: Optional[str] = None
    error: Optional[str] = None
    rollback_available: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class AutomatedDriftRemediator:
    """Automated drift remediation engine."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the remediator."""
        self.config_path = config_path or 'config/remediation.yaml'
        self.config = self._load_config()
        self.notification_sender = NotificationSender()
        
        # Risk thresholds
        self.risk_thresholds = {
            RiskLevel.LOW: {
                'max_version_lag': 30,  # days
                'max_severity': 'medium',
                'auto_approve': True,
                'require_tests': False
            },
            RiskLevel.MEDIUM: {
                'max_version_lag': 90,  # days
                'max_severity': 'high',
                'auto_approve': False,
                'require_tests': True
            },
            RiskLevel.HIGH: {
                'max_version_lag': 365,  # days
                'max_severity': 'critical',
                'auto_approve': False,
                'require_tests': True
            }
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """Load remediation configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Remediation config not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            logger.error(f"Error parsing remediation config: {e}")
            return {}
    
    def remediate_service(self, service_name: str, risk_level: RiskLevel, 
                         require_approval: bool = False, dry_run: bool = False) -> List[RemediationResult]:
        """Remediate drift issues for a specific service."""
        logger.info(f"Starting automated remediation for service: {service_name}")
        
        try:
            # Detect drift issues
            drift_issues = self._detect_drift_issues(service_name)
            if not drift_issues:
                logger.info(f"No drift issues found for service: {service_name}")
                return []
            
            # Filter by risk level
            eligible_issues = self._filter_by_risk_level(drift_issues, risk_level)
            if not eligible_issues:
                logger.info(f"No eligible drift issues for risk level: {risk_level.value}")
                return []
            
            # Remediate issues
            results = []
            for issue in eligible_issues:
                if dry_run:
                    logger.info(f"DRY RUN: Would remediate {issue.issue_type} for {service_name}")
                    results.append(RemediationResult(
                        success=True,
                        action=issue.remediation_action,
                        service_name=service_name,
                        metadata={'dry_run': True, 'issue': issue.__dict__}
                    ))
                else:
                    result = self._remediate_issue(issue, require_approval)
                    results.append(result)
            
            # Send notifications
            self._send_remediation_notifications(service_name, results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error remediating service {service_name}: {e}")
            return [RemediationResult(
                success=False,
                action=RemediationAction.UPDATE_DEPENDENCY,
                service_name=service_name,
                error=str(e)
            )]
    
    def remediate_all_services(self, risk_level: RiskLevel, dry_run: bool = False) -> Dict[str, List[RemediationResult]]:
        """Remediate drift issues for all services."""
        logger.info("Starting automated remediation for all services")
        
        # Get all services
        services = self._get_all_services()
        if not services:
            logger.warning("No services found for remediation")
            return {}
        
        # Remediate each service
        all_results = {}
        for service_name in services:
            try:
                results = self.remediate_service(service_name, risk_level, dry_run=dry_run)
                all_results[service_name] = results
            except Exception as e:
                logger.error(f"Error remediating service {service_name}: {e}")
                all_results[service_name] = [RemediationResult(
                    success=False,
                    action=RemediationAction.UPDATE_DEPENDENCY,
                    service_name=service_name,
                    error=str(e)
                )]
        
        # Send summary notification
        self._send_summary_notification(all_results)
        
        return all_results
    
    def _detect_drift_issues(self, service_name: str) -> List[DriftIssue]:
        """Detect drift issues for a service."""
        issues = []
        
        try:
            # Load drift data
            drift_file = Path('analysis/reports/drift/latest_drift_report.json')
            if not drift_file.exists():
                logger.warning("No drift report found")
                return issues
            
            with open(drift_file, 'r') as f:
                drift_data = json.load(f)
            
            service_data = drift_data.get('services', {}).get(service_name, {})
            if not service_data:
                logger.warning(f"No drift data found for service: {service_name}")
                return issues
            
            # Process drift issues
            for issue_data in service_data.get('issues', []):
                issue = self._create_drift_issue(service_name, issue_data)
                if issue:
                    issues.append(issue)
            
        except Exception as e:
            logger.error(f"Error detecting drift issues for {service_name}: {e}")
        
        return issues
    
    def _create_drift_issue(self, service_name: str, issue_data: Dict[str, Any]) -> Optional[DriftIssue]:
        """Create a DriftIssue from issue data."""
        try:
            issue_type = issue_data.get('type', 'unknown')
            severity = issue_data.get('severity', 'medium')
            description = issue_data.get('description', '')
            current_version = issue_data.get('current_version', '')
            target_version = issue_data.get('target_version', '')
            
            # Determine risk level
            risk_level = self._determine_risk_level(issue_type, severity, current_version, target_version)
            
            # Determine remediation action
            remediation_action = self._determine_remediation_action(issue_type, severity)
            
            return DriftIssue(
                service_name=service_name,
                issue_type=issue_type,
                severity=severity,
                description=description,
                current_version=current_version,
                target_version=target_version,
                risk_level=risk_level,
                remediation_action=remediation_action,
                metadata=issue_data
            )
            
        except Exception as e:
            logger.error(f"Error creating drift issue: {e}")
            return None
    
    def _determine_risk_level(self, issue_type: str, severity: str, 
                             current_version: str, target_version: str) -> RiskLevel:
        """Determine risk level for a drift issue."""
        # High risk indicators
        if severity == 'critical' or issue_type == 'security_vulnerability':
            return RiskLevel.HIGH
        
        # Medium risk indicators
        if severity == 'high' or issue_type in ['major_version_lag', 'breaking_change']:
            return RiskLevel.MEDIUM
        
        # Low risk indicators
        if severity in ['low', 'medium'] or issue_type in ['minor_version_lag', 'patch_version_lag']:
            return RiskLevel.LOW
        
        return RiskLevel.MEDIUM
    
    def _determine_remediation_action(self, issue_type: str, severity: str) -> RemediationAction:
        """Determine remediation action for a drift issue."""
        if issue_type == 'missing_lock_file':
            return RemediationAction.UPDATE_LOCK_FILE
        elif issue_type == 'security_vulnerability':
            return RemediationAction.UPDATE_SECURITY
        elif issue_type in ['major_version_lag', 'minor_version_lag', 'patch_version_lag']:
            return RemediationAction.UPDATE_DEPENDENCY
        elif issue_type == 'linting_failure':
            return RemediationAction.FIX_LINTING
        elif issue_type == 'service_manifest_outdated':
            return RemediationAction.UPDATE_SERVICE_MANIFEST
        else:
            return RemediationAction.UPDATE_DEPENDENCY
    
    def _filter_by_risk_level(self, issues: List[DriftIssue], risk_level: RiskLevel) -> List[DriftIssue]:
        """Filter issues by risk level."""
        filtered = []
        
        for issue in issues:
            if issue.risk_level == risk_level:
                filtered.append(issue)
            elif risk_level == RiskLevel.LOW and issue.risk_level in [RiskLevel.LOW]:
                filtered.append(issue)
            elif risk_level == RiskLevel.MEDIUM and issue.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]:
                filtered.append(issue)
            elif risk_level == RiskLevel.HIGH:
                filtered.append(issue)
        
        return filtered
    
    def _remediate_issue(self, issue: DriftIssue, require_approval: bool = False) -> RemediationResult:
        """Remediate a specific drift issue."""
        logger.info(f"Remediating {issue.issue_type} for {issue.service_name}")
        
        try:
            if issue.remediation_action == RemediationAction.UPDATE_DEPENDENCY:
                return self._update_dependency(issue, require_approval)
            elif issue.remediation_action == RemediationAction.UPDATE_LOCK_FILE:
                return self._update_lock_file(issue, require_approval)
            elif issue.remediation_action == RemediationAction.UPDATE_SERVICE_MANIFEST:
                return self._update_service_manifest(issue, require_approval)
            elif issue.remediation_action == RemediationAction.FIX_LINTING:
                return self._fix_linting(issue, require_approval)
            elif issue.remediation_action == RemediationAction.UPDATE_SECURITY:
                return self._update_security(issue, require_approval)
            else:
                return RemediationResult(
                    success=False,
                    action=issue.remediation_action,
                    service_name=issue.service_name,
                    error=f"Unknown remediation action: {issue.remediation_action}"
                )
                
        except Exception as e:
            logger.error(f"Error remediating issue {issue.issue_type}: {e}")
            return RemediationResult(
                success=False,
                action=issue.remediation_action,
                service_name=issue.service_name,
                error=str(e)
            )
    
    def _update_dependency(self, issue: DriftIssue, require_approval: bool = False) -> RemediationResult:
        """Update a dependency to resolve drift."""
        try:
            # Create a temporary directory for the service
            with tempfile.TemporaryDirectory() as temp_dir:
                # Clone the service repository
                repo_url = f"https://github.com/254carbon/{issue.service_name}.git"
                subprocess.run(['git', 'clone', repo_url, temp_dir], check=True)
                
                # Update the dependency
                if issue.metadata.get('package_manager') == 'npm':
                    subprocess.run(['npm', 'update', issue.metadata.get('package_name')], 
                                 cwd=temp_dir, check=True)
                elif issue.metadata.get('package_manager') == 'pip':
                    subprocess.run(['pip', 'install', '--upgrade', issue.metadata.get('package_name')], 
                                 cwd=temp_dir, check=True)
                elif issue.metadata.get('package_manager') == 'go':
                    subprocess.run(['go', 'get', '-u', issue.metadata.get('package_name')], 
                                 cwd=temp_dir, check=True)
                
                # Create a PR
                pr_url = self._create_pr(temp_dir, issue, require_approval)
                
                return RemediationResult(
                    success=True,
                    action=RemediationAction.UPDATE_DEPENDENCY,
                    service_name=issue.service_name,
                    pr_url=pr_url,
                    rollback_available=True
                )
                
        except Exception as e:
            logger.error(f"Error updating dependency: {e}")
            return RemediationResult(
                success=False,
                action=RemediationAction.UPDATE_DEPENDENCY,
                service_name=issue.service_name,
                error=str(e)
            )
    
    def _update_lock_file(self, issue: DriftIssue, require_approval: bool = False) -> RemediationResult:
        """Update lock file to resolve drift."""
        try:
            # Create a temporary directory for the service
            with tempfile.TemporaryDirectory() as temp_dir:
                # Clone the service repository
                repo_url = f"https://github.com/254carbon/{issue.service_name}.git"
                subprocess.run(['git', 'clone', repo_url, temp_dir], check=True)
                
                # Generate new lock file
                if issue.metadata.get('package_manager') == 'npm':
                    subprocess.run(['npm', 'install'], cwd=temp_dir, check=True)
                elif issue.metadata.get('package_manager') == 'pip':
                    subprocess.run(['pip', 'freeze'], cwd=temp_dir, check=True)
                elif issue.metadata.get('package_manager') == 'go':
                    subprocess.run(['go', 'mod', 'tidy'], cwd=temp_dir, check=True)
                
                # Create a PR
                pr_url = self._create_pr(temp_dir, issue, require_approval)
                
                return RemediationResult(
                    success=True,
                    action=RemediationAction.UPDATE_LOCK_FILE,
                    service_name=issue.service_name,
                    pr_url=pr_url,
                    rollback_available=True
                )
                
        except Exception as e:
            logger.error(f"Error updating lock file: {e}")
            return RemediationResult(
                success=False,
                action=RemediationAction.UPDATE_LOCK_FILE,
                service_name=issue.service_name,
                error=str(e)
            )
    
    def _update_service_manifest(self, issue: DriftIssue, require_approval: bool = False) -> RemediationResult:
        """Update service manifest to resolve drift."""
        try:
            # Load current service manifest
            manifest_file = Path(f"catalog/service-index.yaml")
            if not manifest_file.exists():
                return RemediationResult(
                    success=False,
                    action=RemediationAction.UPDATE_SERVICE_MANIFEST,
                    service_name=issue.service_name,
                    error="Service manifest not found"
                )
            
            with open(manifest_file, 'r') as f:
                manifest_data = yaml.safe_load(f)
            
            # Update the service manifest
            service_data = manifest_data.get('services', {}).get(issue.service_name, {})
            if service_data:
                # Update version information
                service_data['version'] = issue.target_version
                service_data['last_update'] = datetime.now(timezone.utc).isoformat()
                
                # Save updated manifest
                with open(manifest_file, 'w') as f:
                    yaml.dump(manifest_data, f, default_flow_style=False)
                
                return RemediationResult(
                    success=True,
                    action=RemediationAction.UPDATE_SERVICE_MANIFEST,
                    service_name=issue.service_name,
                    rollback_available=True
                )
            else:
                return RemediationResult(
                    success=False,
                    action=RemediationAction.UPDATE_SERVICE_MANIFEST,
                    service_name=issue.service_name,
                    error="Service not found in manifest"
                )
                
        except Exception as e:
            logger.error(f"Error updating service manifest: {e}")
            return RemediationResult(
                success=False,
                action=RemediationAction.UPDATE_SERVICE_MANIFEST,
                service_name=issue.service_name,
                error=str(e)
            )
    
    def _fix_linting(self, issue: DriftIssue, require_approval: bool = False) -> RemediationResult:
        """Fix linting issues to resolve drift."""
        try:
            # Create a temporary directory for the service
            with tempfile.TemporaryDirectory() as temp_dir:
                # Clone the service repository
                repo_url = f"https://github.com/254carbon/{issue.service_name}.git"
                subprocess.run(['git', 'clone', repo_url, temp_dir], check=True)
                
                # Fix linting issues
                if issue.metadata.get('language') == 'python':
                    subprocess.run(['python', '-m', 'black', '.'], cwd=temp_dir, check=True)
                    subprocess.run(['python', '-m', 'flake8', '--fix'], cwd=temp_dir, check=True)
                elif issue.metadata.get('language') == 'javascript':
                    subprocess.run(['npm', 'run', 'lint:fix'], cwd=temp_dir, check=True)
                elif issue.metadata.get('language') == 'go':
                    subprocess.run(['go', 'fmt', './...'], cwd=temp_dir, check=True)
                
                # Create a PR
                pr_url = self._create_pr(temp_dir, issue, require_approval)
                
                return RemediationResult(
                    success=True,
                    action=RemediationAction.FIX_LINTING,
                    service_name=issue.service_name,
                    pr_url=pr_url,
                    rollback_available=True
                )
                
        except Exception as e:
            logger.error(f"Error fixing linting: {e}")
            return RemediationResult(
                success=False,
                action=RemediationAction.FIX_LINTING,
                service_name=issue.service_name,
                error=str(e)
            )
    
    def _update_security(self, issue: DriftIssue, require_approval: bool = False) -> RemediationResult:
        """Update security vulnerabilities to resolve drift."""
        try:
            # Create a temporary directory for the service
            with tempfile.TemporaryDirectory() as temp_dir:
                # Clone the service repository
                repo_url = f"https://github.com/254carbon/{issue.service_name}.git"
                subprocess.run(['git', 'clone', repo_url, temp_dir], check=True)
                
                # Update security vulnerabilities
                if issue.metadata.get('package_manager') == 'npm':
                    subprocess.run(['npm', 'audit', 'fix'], cwd=temp_dir, check=True)
                elif issue.metadata.get('package_manager') == 'pip':
                    subprocess.run(['pip', 'install', '--upgrade', issue.metadata.get('package_name')], 
                                 cwd=temp_dir, check=True)
                elif issue.metadata.get('package_manager') == 'go':
                    subprocess.run(['go', 'get', '-u', issue.metadata.get('package_name')], 
                                 cwd=temp_dir, check=True)
                
                # Create a PR
                pr_url = self._create_pr(temp_dir, issue, require_approval)
                
                return RemediationResult(
                    success=True,
                    action=RemediationAction.UPDATE_SECURITY,
                    service_name=issue.service_name,
                    pr_url=pr_url,
                    rollback_available=True
                )
                
        except Exception as e:
            logger.error(f"Error updating security: {e}")
            return RemediationResult(
                success=False,
                action=RemediationAction.UPDATE_SECURITY,
                service_name=issue.service_name,
                error=str(e)
            )
    
    def _create_pr(self, temp_dir: str, issue: DriftIssue, require_approval: bool = False) -> Optional[str]:
        """Create a pull request for the remediation."""
        try:
            # Create a new branch
            branch_name = f"auto-remediate-{issue.issue_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            subprocess.run(['git', 'checkout', '-b', branch_name], cwd=temp_dir, check=True)
            
            # Commit changes
            subprocess.run(['git', 'add', '.'], cwd=temp_dir, check=True)
            subprocess.run(['git', 'commit', '-m', f'Auto-remediate {issue.issue_type}: {issue.description}'], 
                         cwd=temp_dir, check=True)
            
            # Push branch
            subprocess.run(['git', 'push', 'origin', branch_name], cwd=temp_dir, check=True)
            
            # Create PR using GitHub API
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                logger.warning("GitHub token not found, cannot create PR")
                return None
            
            pr_data = {
                'title': f'Auto-remediate {issue.issue_type}',
                'body': f'Automated remediation for {issue.issue_type}:\n\n{issue.description}\n\n'
                       f'Current version: {issue.current_version}\n'
                       f'Target version: {issue.target_version}\n\n'
                       f'Risk level: {issue.risk_level.value}\n'
                       f'Requires approval: {require_approval}',
                'head': branch_name,
                'base': 'main'
            }
            
            if require_approval:
                pr_data['labels'] = ['auto-remediation', 'requires-approval']
            else:
                pr_data['labels'] = ['auto-remediation', 'auto-merge']
            
            response = requests.post(
                f'https://api.github.com/repos/254carbon/{issue.service_name}/pulls',
                headers={'Authorization': f'token {github_token}'},
                json=pr_data
            )
            
            if response.status_code == 201:
                pr_info = response.json()
                return pr_info['html_url']
            else:
                logger.error(f"Failed to create PR: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating PR: {e}")
            return None
    
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
    
    def _send_remediation_notifications(self, service_name: str, results: List[RemediationResult]):
        """Send notifications about remediation results."""
        try:
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            if successful:
                message = NotificationMessage(
                    title=f"Automated Drift Remediation Completed - {service_name}",
                    content=f"Successfully remediated {len(successful)} drift issues for {service_name}",
                    severity=NotificationSeverity.MEDIUM,
                    channel=NotificationChannel.SLACK,
                    metadata={
                        'service_name': service_name,
                        'successful_count': len(successful),
                        'failed_count': len(failed),
                        'event_type': 'drift_remediation'
                    }
                )
                self.notification_sender.send_notification(message)
            
            if failed:
                message = NotificationMessage(
                    title=f"Automated Drift Remediation Failed - {service_name}",
                    content=f"Failed to remediate {len(failed)} drift issues for {service_name}",
                    severity=NotificationSeverity.HIGH,
                    channel=NotificationChannel.SLACK,
                    metadata={
                        'service_name': service_name,
                        'failed_count': len(failed),
                        'errors': [r.error for r in failed],
                        'event_type': 'drift_remediation_failure'
                    }
                )
                self.notification_sender.send_notification(message)
                
        except Exception as e:
            logger.error(f"Error sending notifications: {e}")
    
    def _send_summary_notification(self, all_results: Dict[str, List[RemediationResult]]):
        """Send summary notification for all remediation results."""
        try:
            total_services = len(all_results)
            successful_services = len([s for s, results in all_results.items() 
                                     if any(r.success for r in results)])
            failed_services = total_services - successful_services
            
            message = NotificationMessage(
                title="Automated Drift Remediation Summary",
                content=f"Completed automated drift remediation for {total_services} services. "
                       f"Successful: {successful_services}, Failed: {failed_services}",
                severity=NotificationSeverity.MEDIUM,
                channel=NotificationChannel.SLACK,
                metadata={
                    'total_services': total_services,
                    'successful_services': successful_services,
                    'failed_services': failed_services,
                    'event_type': 'drift_remediation_summary'
                }
            )
            self.notification_sender.send_notification(message)
            
        except Exception as e:
            logger.error(f"Error sending summary notification: {e}")


def main():
    """Main entry point for automated drift remediation."""
    parser = argparse.ArgumentParser(description='Automated drift remediation')
    parser.add_argument('--service', help='Service name to remediate')
    parser.add_argument('--all-services', action='store_true', help='Remediate all services')
    parser.add_argument('--risk-level', choices=['low', 'medium', 'high'], default='low',
                       help='Risk level for remediation')
    parser.add_argument('--require-approval', action='store_true',
                       help='Require approval for medium/high risk changes')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode')
    parser.add_argument('--config', default='config/remediation.yaml',
                       help='Remediation config file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    if not args.service and not args.all_services:
        parser.error("Must specify --service or --all-services")
    
    # Initialize remediator
    remediator = AutomatedDriftRemediator(args.config)
    
    try:
        if args.service:
            # Remediate single service
            results = remediator.remediate_service(
                args.service, 
                RiskLevel(args.risk_level),
                args.require_approval,
                args.dry_run
            )
            
            print(f"\nRemediation Results for {args.service}:")
            for result in results:
                status = "SUCCESS" if result.success else "FAILED"
                print(f"  {result.action.value}: {status}")
                if result.pr_url:
                    print(f"    PR: {result.pr_url}")
                if result.error:
                    print(f"    Error: {result.error}")
        
        else:
            # Remediate all services
            all_results = remediator.remediate_all_services(
                RiskLevel(args.risk_level),
                args.dry_run
            )
            
            print(f"\nRemediation Summary:")
            print(f"Total services: {len(all_results)}")
            
            successful_services = 0
            failed_services = 0
            
            for service_name, results in all_results.items():
                successful = any(r.success for r in results)
                if successful:
                    successful_services += 1
                else:
                    failed_services += 1
                
                print(f"  {service_name}: {'SUCCESS' if successful else 'FAILED'}")
            
            print(f"\nSuccessful: {successful_services}")
            print(f"Failed: {failed_services}")
        
    except Exception as e:
        logger.error(f"Automated remediation failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
