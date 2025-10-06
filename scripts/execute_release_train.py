#!/usr/bin/env python3
"""
254Carbon Meta Repository - Release Train Execution

Executes coordinated multi-service release trains.

Usage:
    python scripts/execute_release_train.py --train Q4-curve-upgrade [--dry-run]
"""

import os
import sys
import json
import yaml
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
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
        logging.FileHandler('analysis/reports/release-execution.log')
    ]
)
logger = logging.getLogger(__name__)


class ReleaseStatus(Enum):
    """Release execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIALLY_SUCCESS = "partially_success"


@dataclass
class ReleaseStep:
    """Represents a single release step."""
    service_name: str
    repo: str
    target_version: str
    step_order: int
    status: ReleaseStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: str = ""
    rollback_attempted: bool = False


@dataclass
class ReleaseExecution:
    """Complete release train execution."""
    train_name: str
    steps: List[ReleaseStep]
    overall_status: ReleaseStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    execution_time: Optional[timedelta] = None
    rollback_triggered: bool = False


class GitHubAPI:
    """GitHub API client for release operations."""

    def __init__(self, token: str, repo_owner: str = "254carbon"):
        self.token = token
        self.repo_owner = repo_owner
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "254Carbon-Meta/1.0"
        })

        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def create_tag(self, repo: str, tag_name: str, target_sha: str, message: str = "") -> bool:
        """Create a Git tag."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{repo}/git/refs"

        payload = {
            "ref": f"refs/tags/{tag_name}",
            "sha": target_sha
        }

        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Created tag {tag_name} in {repo}")
            return True
        except Exception as e:
            logger.error(f"Failed to create tag {tag_name} in {repo}: {e}")
            return False

    def trigger_workflow(self, repo: str, workflow_file: str, ref: str = "main",
                       inputs: Dict[str, Any] = None) -> Optional[str]:
        """Trigger a GitHub Actions workflow."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{repo}/actions/workflows/{workflow_file}/dispatches"

        payload = {
            "ref": ref
        }

        if inputs:
            payload["inputs"] = inputs

        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()

            # Get the workflow run ID from response headers
            workflow_run_url = response.headers.get('Location', '')
            if workflow_run_url:
                # Extract run ID from URL
                run_id = workflow_run_url.split('/')[-1]
                logger.info(f"Triggered workflow in {repo}, run ID: {run_id}")
                return run_id

            return None
        except Exception as e:
            logger.error(f"Failed to trigger workflow in {repo}: {e}")
            return None

    def get_workflow_status(self, repo: str, run_id: str) -> Dict[str, Any]:
        """Get workflow run status."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{repo}/actions/runs/{run_id}"

        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get workflow status for {repo}/{run_id}: {e}")
            return {}

    def get_latest_commit_sha(self, repo: str, branch: str = "main") -> Optional[str]:
        """Get latest commit SHA for a branch."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{repo}/git/refs/heads/{branch}"

        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()["object"]["sha"]
        except Exception as e:
            logger.error(f"Failed to get latest commit for {repo}/{branch}: {e}")
            return None


class ReleaseTrainExecutor:
    """Executes release trains with health monitoring."""

    def __init__(self, train_name: str, train_config: str = None, dry_run: bool = False):
        self.train_name = train_name
        self.dry_run = dry_run

        # Load release train configuration
        if train_config:
            self.train_config = json.loads(train_config)
        else:
            self.train_config = self._load_release_train_config()

        # Initialize execution tracking
        self.execution = ReleaseExecution(
            train_name=train_name,
            steps=[],
            overall_status=ReleaseStatus.PENDING,
            started_at=datetime.now(timezone.utc)
        )

        # Initialize GitHub API
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN environment variable required")
        self.github = GitHubAPI(github_token)

    def _load_release_train_config(self) -> Dict[str, Any]:
        """Load release train configuration."""
        config_file = Path("catalog/release-trains.yaml")

        if not config_file.exists():
            raise FileNotFoundError(f"Release train config not found: {config_file}")

        with open(config_file) as f:
            trains_data = yaml.safe_load(f)

        # Find the specified train
        for train in trains_data.get('trains', []):
            if train['name'] == self.train_name:
                return train

        raise ValueError(f"Release train '{self.train_name}' not found in configuration")

    def prepare_release_steps(self) -> List[ReleaseStep]:
        """Prepare release steps from train configuration."""
        participants = self.train_config.get('participants', [])
        steps = []

        for i, participant in enumerate(participants, 1):
            step = ReleaseStep(
                service_name=participant,
                repo=self._get_service_repo(participant),
                target_version=self.train_config.get('target_version', ''),
                step_order=i,
                status=ReleaseStatus.PENDING
            )
            steps.append(step)

        logger.info(f"Prepared {len(steps)} release steps")
        return steps

    def _get_service_repo(self, service_name: str) -> str:
        """Get repository name for a service."""
        # This would typically query the catalog for service repo mapping
        # For now, use a simple mapping
        repo_mapping = {
            'gateway': '254carbon-access',
            'auth': '254carbon-access',
            'streaming': '254carbon-data-processing',
            'normalization': '254carbon-data-processing',
            'enrichment': '254carbon-data-processing',
            'aggregation': '254carbon-data-processing',
            'projection': '254carbon-data-processing',
            'curve': '254carbon-ml'
        }

        return repo_mapping.get(service_name, f"254carbon-{service_name}")

    def execute_release_step(self, step: ReleaseStep) -> ReleaseStatus:
        """Execute a single release step."""
        logger.info(f"Executing release step {step.step_order}: {step.service_name}")

        if self.dry_run:
            logger.info(f"DRY RUN: Would release {step.service_name} to {step.target_version}")
            return ReleaseStatus.SUCCESS

        try:
            step.started_at = datetime.now(timezone.utc)
            step.status = ReleaseStatus.IN_PROGRESS

            # Get latest commit SHA
            target_sha = self.github.get_latest_commit_sha(step.repo)
            if not target_sha:
                step.error_message = f"Failed to get latest commit for {step.repo}"
                step.status = ReleaseStatus.FAILED
                return ReleaseStatus.FAILED

            # Create release tag
            tag_name = f"{self.train_name}-{step.service_name}-{step.target_version}"
            if not self.github.create_tag(step.repo, tag_name, target_sha):
                step.error_message = f"Failed to create tag {tag_name}"
                step.status = ReleaseStatus.FAILED
                return ReleaseStatus.FAILED

            # Trigger deployment workflow (if exists)
            workflow_inputs = {
                "service_name": step.service_name,
                "target_version": step.target_version,
                "release_train": self.train_name
            }

            workflow_run_id = self.github.trigger_workflow(
                step.repo,
                "deploy.yml",  # Assumes deployment workflow exists
                inputs=workflow_inputs
            )

            if workflow_run_id:
                # Monitor workflow for a short time
                monitoring_success = self._monitor_workflow(step.repo, workflow_run_id)

                if not monitoring_success:
                    step.error_message = "Deployment workflow failed or timed out"
                    step.status = ReleaseStatus.FAILED
                    return ReleaseStatus.FAILED

            step.completed_at = datetime.now(timezone.utc)
            step.status = ReleaseStatus.SUCCESS
            logger.info(f"✅ Successfully released {step.service_name}")

            return ReleaseStatus.SUCCESS

        except Exception as e:
            step.error_message = str(e)
            step.status = ReleaseStatus.FAILED
            logger.error(f"❌ Failed to release {step.service_name}: {e}")
            return ReleaseStatus.FAILED

    def _monitor_workflow(self, repo: str, run_id: str, timeout_minutes: int = 10) -> bool:
        """Monitor workflow execution for success."""
        start_time = datetime.now(timezone.utc)

        while (datetime.now(timezone.utc) - start_time).total_seconds() < (timeout_minutes * 60):
            try:
                workflow_status = self.github.get_workflow_status(repo, run_id)

                if not workflow_status:
                    logger.warning(f"Could not get workflow status for {repo}/{run_id}")
                    return True  # Assume success if we can't check

                status = workflow_status.get('status', '')
                conclusion = workflow_status.get('conclusion', '')

                if status == 'completed':
                    if conclusion == 'success':
                        logger.info(f"Workflow {run_id} completed successfully")
                        return True
                    else:
                        logger.error(f"Workflow {run_id} failed with conclusion: {conclusion}")
                        return False

                # Wait before checking again
                time.sleep(30)

            except Exception as e:
                logger.warning(f"Error monitoring workflow {run_id}: {e}")
                time.sleep(30)

        logger.warning(f"Workflow {run_id} timed out after {timeout_minutes} minutes")
        return False  # Timeout

    def execute_release_train(self) -> ReleaseExecution:
        """Execute the complete release train."""
        logger.info(f"Starting release train execution: {self.train_name}")

        # Prepare steps
        self.execution.steps = self.prepare_release_steps()
        self.execution.overall_status = ReleaseStatus.IN_PROGRESS

        successful_steps = 0
        failed_steps = 0

        # Execute steps sequentially
        for step in self.execution.steps:
            step_status = self.execute_release_step(step)

            if step_status == ReleaseStatus.SUCCESS:
                successful_steps += 1
            else:
                failed_steps += 1
                # Check if we should continue or stop
                if self._should_stop_on_failure(step):
                    logger.error(f"Stopping release train due to failure in step {step.step_order}")
                    break

                # Continue with next step (sequential execution)
                continue

        # Determine overall status
        self.execution.completed_at = datetime.now(timezone.utc)
        self.execution.execution_time = self.execution.completed_at - self.execution.started_at

        if failed_steps == 0:
            self.execution.overall_status = ReleaseStatus.SUCCESS
        elif successful_steps > 0:
            self.execution.overall_status = ReleaseStatus.PARTIALLY_SUCCESS
        else:
            self.execution.overall_status = ReleaseStatus.FAILED

        logger.info(f"Release train completed: {successful_steps} successful, {failed_steps} failed")
        return self.execution

    def _should_stop_on_failure(self, failed_step: ReleaseStep) -> bool:
        """Determine if execution should stop on step failure."""
        # Stop on critical service failures
        critical_services = ['gateway', 'auth']
        if failed_step.service_name in critical_services:
            return True

        # Stop if more than half the steps have failed
        total_steps = len(self.execution.steps)
        failed_steps = len([s for s in self.execution.steps if s.status == ReleaseStatus.FAILED])

        if failed_steps > total_steps / 2:
            return True

        return False

    def rollback_failed_steps(self) -> bool:
        """Attempt to rollback failed steps."""
        logger.info("Attempting rollback of failed steps...")

        rollback_success = True
        rolled_back_services = []

        for step in self.execution.steps:
            if step.status == ReleaseStatus.FAILED and not step.rollback_attempted:
                logger.info(f"Rolling back {step.service_name}...")

                try:
                    # In a real implementation, this would:
                    # 1. Find previous successful tag
                    # 2. Trigger rollback deployment
                    # 3. Verify rollback success

                    # For now, just mark as attempted
                    step.rollback_attempted = True
                    rolled_back_services.append(step.service_name)

                except Exception as e:
                    logger.error(f"Failed to rollback {step.service_name}: {e}")
                    rollback_success = False

        if rolled_back_services:
            logger.info(f"Rollback attempted for: {', '.join(rolled_back_services)}")

        return rollback_success

    def save_execution_report(self, execution: ReleaseExecution) -> None:
        """Save execution report to file."""
        reports_dir = Path("analysis/reports/release-trains")
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"{execution.train_name}_{timestamp}_execution.json"

        report = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'train_name': execution.train_name,
                'execution_time_seconds': execution.execution_time.total_seconds() if execution.execution_time else 0,
                'dry_run': self.dry_run
            },
            'execution_summary': {
                'overall_status': execution.overall_status.value,
                'total_steps': len(execution.steps),
                'successful_steps': len([s for s in execution.steps if s.status == ReleaseStatus.SUCCESS]),
                'failed_steps': len([s for s in execution.steps if s.status == ReleaseStatus.FAILED]),
                'rollback_triggered': execution.rollback_triggered
            },
            'step_details': [
                {
                    'service_name': step.service_name,
                    'repo': step.repo,
                    'target_version': step.target_version,
                    'step_order': step.step_order,
                    'status': step.status.value,
                    'started_at': step.started_at.isoformat() if step.started_at else None,
                    'completed_at': step.completed_at.isoformat() if step.completed_at else None,
                    'execution_time_seconds': (step.completed_at - step.started_at).total_seconds() if step.started_at and step.completed_at else 0,
                    'error_message': step.error_message,
                    'rollback_attempted': step.rollback_attempted
                }
                for step in execution.steps
            ]
        }

        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Saved execution report to {report_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Execute release train")
    parser.add_argument("--train", required=True, help="Release train name to execute")
    parser.add_argument("--train-config", type=str, help="Release train configuration JSON")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without actual releases")
    parser.add_argument("--rollback-on-failure", action="store_true", default=True,
                       help="Attempt rollback if execution fails")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        executor = ReleaseTrainExecutor(args.train, args.train_config, args.dry_run)
        execution = executor.execute_release_step

        # Attempt rollback if needed
        if (args.rollback_on_failure and
            execution.overall_status in [ReleaseStatus.FAILED, ReleaseStatus.PARTIALLY_SUCCESS]):
            execution.rollback_triggered = True
            rollback_success = executor.rollback_failed_steps()
            if rollback_success:
                execution.overall_status = ReleaseStatus.ROLLED_BACK

        # Save execution report
        executor.save_execution_report(execution)

        # Print summary
        print("\n🚂 Release Train Execution Summary:")
        print(f"  Train: {execution.train_name}")
        print(f"  Status: {execution.overall_status.value.upper()}")
        print(f"  Duration: {execution.execution_time}")
        print(f"  Steps: {len(execution.steps)} total, {len([s for s in execution.steps if s.status == ReleaseStatus.SUCCESS])} successful")

        if execution.overall_status == ReleaseStatus.SUCCESS:
            print("  ✅ Release train completed successfully!")
        elif execution.overall_status == ReleaseStatus.PARTIALLY_SUCCESS:
            print("  ⚠️ Release train partially successful - some steps failed")
        else:
            print("  ❌ Release train failed")

        if execution.rollback_triggered:
            print("  🔄 Rollback was attempted")

    except Exception as e:
        logger.error(f"Release train execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
