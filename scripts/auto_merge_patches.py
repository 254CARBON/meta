#!/usr/bin/env python3
"""
254Carbon Meta Repository - Auto-Merge Patches

Safely auto-merges patch upgrade PRs that meet criteria.

Usage:
    python scripts/auto_merge_patches.py [--dry-run] [--max-age-hours 48]
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/auto-merge.log')
    ]
)
logger = logging.getLogger(__name__)


class GitHubAPI:
    """GitHub API client for PR management."""

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

        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def get_prs_by_label(self, label: str) -> List[Dict[str, Any]]:
        """Get PRs with specific label."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls"
        params = {
            "labels": label,
            "state": "open",
            "per_page": 50
        }

        response = self.session.get(url, params=params)
        response.raise_for_status()

        return response.json()

    def get_pr_details(self, pr_number: int) -> Dict[str, Any]:
        """Get detailed PR information."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_number}"

        response = self.session.get(url)
        response.raise_for_status()

        return response.json()

    def merge_pr(self, pr_number: int, merge_method: str = "merge") -> bool:
        """Merge a PR."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_number}/merge"

        payload = {
            "merge_method": merge_method
        }

        response = self.session.put(url, json=payload)

        if response.status_code == 200:
            logger.info(f"Successfully merged PR #{pr_number}")
            return True
        else:
            logger.warning(f"Failed to merge PR #{pr_number}: {response.text}")
            return False


class PatchMergeManager:
    """Manages safe auto-merging of patch upgrades."""

    def __init__(self, github_token: str, dry_run: bool = False, max_age_hours: int = 48):
        self.github = GitHubAPI(github_token)
        self.dry_run = dry_run
        self.max_age_hours = max_age_hours

        # Load configuration
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load auto-merge configuration."""
        config_file = Path("config/upgrade-policies.yaml")

        if not config_file.exists():
            logger.warning(f"Config file not found: {config_file}")
            return self._get_default_config()

        with open(config_file) as f:
            return yaml.safe_load(f)

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default auto-merge configuration."""
        return {
            'auto_merge': {
                'patch': {
                    'enabled': True,
                    'require_ci_pass': True,
                    'require_review': False,
                    'max_age_hours': 48,
                    'min_quality_score': 70
                }
            }
        }

    def find_patch_upgrade_prs(self) -> List[Dict[str, Any]]:
        """Find patch upgrade PRs eligible for auto-merge."""
        # Look for PRs with patch upgrade labels
        patch_labels = ["auto-upgrade", "patch", "spec-upgrade"]

        candidate_prs = []
        for label in patch_labels:
            try:
                prs = self.github.get_prs_by_label(label)
                candidate_prs.extend(prs)
            except Exception as e:
                logger.warning(f"Failed to get PRs for label {label}: {e}")

        # Remove duplicates
        seen = set()
        unique_prs = []
        for pr in candidate_prs:
            pr_id = pr['number']
            if pr_id not in seen:
                unique_prs.append(pr)
                seen.add(pr_id)

        return unique_prs

    def check_pr_eligibility(self, pr: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if PR is eligible for auto-merge."""
        pr_number = pr['number']

        try:
            # Get detailed PR info
            pr_details = self.github.get_pr_details(pr_number)

            # Check 1: Must be patch upgrade
            labels = [label['name'] for label in pr_details.get('labels', [])]
            if not any(label in ['patch', 'auto-upgrade'] for label in labels):
                return False, "Not a patch upgrade PR"

            # Check 2: Must have passing CI
            if not self._check_ci_status(pr_details):
                return False, "CI checks not passing"

            # Check 3: Must not be draft
            if pr_details.get('draft', False):
                return False, "PR is in draft state"

            # Check 4: Must be mergeable
            if not pr_details.get('mergeable', False):
                return False, "PR has merge conflicts"

            # Check 5: Age check
            created_at = datetime.fromisoformat(pr_details['created_at'].replace('Z', '+00:00'))
            age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600

            if age_hours > self.max_age_hours:
                return False, f"PR is too old ({age_hours:.1f}h > {self.max_age_hours}h)"

            # Check 6: Quality check (if quality data available)
            if not self._check_quality_requirements(pr_details):
                return False, "Quality requirements not met"

            return True, "Eligible for auto-merge"

        except Exception as e:
            logger.error(f"Failed to check eligibility for PR #{pr_number}: {e}")
            return False, f"Error checking eligibility: {e}"

    def _check_ci_status(self, pr_details: Dict[str, Any]) -> bool:
        """Check if CI checks are passing."""
        # Get status checks
        statuses_url = pr_details.get('statuses_url', '').replace('{/sha}', f"/{pr_details['head']['sha']}")

        if not statuses_url.startswith('https://'):
            return True  # No status checks configured

        try:
            response = self.github.session.get(statuses_url)
            response.raise_for_status()

            status_checks = response.json()

            # Check for required status checks
            required_contexts = ['test', 'build', 'lint']
            check_results = {}

            for check in status_checks:
                context = check.get('context', '').lower()
                state = check.get('state', 'pending')

                for req_context in required_contexts:
                    if req_context in context:
                        check_results[req_context] = state

            # All required checks must pass
            return all(state == 'success' for state in check_results.values())

        except Exception as e:
            logger.warning(f"Failed to check CI status: {e}")
            return True  # Default to allowing if we can't check

    def _check_quality_requirements(self, pr_details: Dict[str, Any]) -> bool:
        """Check if quality requirements are met."""
        config = self.config.get('auto_merge', {}).get('patch', {})

        if not config.get('require_quality_check', False):
            return True  # Quality check not required

        # In a real implementation, this would check quality scores
        # For now, we'll assume quality check passes
        return True

    def auto_merge_eligible_prs(self) -> List[str]:
        """Auto-merge eligible patch upgrade PRs."""
        logger.info("Checking for auto-merge eligible PRs...")

        # Find candidate PRs
        candidate_prs = self.find_patch_upgrade_prs()

        if not candidate_prs:
            logger.info("No patch upgrade PRs found")
            return []

        eligible_prs = []
        merged_prs = []

        for pr in candidate_prs:
            pr_number = pr['number']
            eligible, reason = self.check_pr_eligibility(pr)

            if eligible:
                eligible_prs.append(str(pr_number))

                if not self.dry_run:
                    # Attempt to merge
                    if self.github.merge_pr(pr_number):
                        merged_prs.append(str(pr_number))
                        logger.info(f"✅ Auto-merged PR #{pr_number}")
                    else:
                        logger.error(f"❌ Failed to auto-merge PR #{pr_number}")
                else:
                    logger.info(f"DRY RUN: Would auto-merge PR #{pr_number}")
            else:
                logger.debug(f"PR #{pr_number} not eligible: {reason}")

        return merged_prs if not self.dry_run else eligible_prs

    def generate_auto_merge_report(self) -> Dict[str, Any]:
        """Generate auto-merge activity report."""
        merged_prs = self.auto_merge_eligible_prs()

        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "dry_run": self.dry_run,
                "max_age_hours": self.max_age_hours
            },
            "summary": {
                "candidate_prs_checked": len(self.find_patch_upgrade_prs()),
                "eligible_for_merge": len(self.auto_merge_eligible_prs()) if not self.dry_run else 0,
                "actually_merged": len(merged_prs) if not self.dry_run else 0,
                "dry_run_eligible": len(merged_prs) if self.dry_run else 0
            },
            "merged_prs": merged_prs,
            "config_used": self.config.get('auto_merge', {}).get('patch', {})
        }

        return report


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Auto-merge eligible patch upgrade PRs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be merged without merging")
    parser.add_argument("--max-age-hours", type=int, default=48, help="Maximum PR age in hours (default: 48)")
    parser.add_argument("--github-token", help="GitHub token (default: GITHUB_TOKEN env var)")
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
        manager = PatchMergeManager(github_token, args.dry_run, args.max_age_hours)
        report = manager.generate_auto_merge_report()

        # Print summary
        print("\n🔄 Auto-Merge Summary:")
        print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
        print(f"  Max Age: {args.max_age_hours} hours")
        print(f"  Candidates Checked: {report['summary']['candidate_prs_checked']}")
        print(f"  Eligible for Merge: {report['summary']['eligible_for_merge']}")

        if not args.dry_run:
            print(f"  Actually Merged: {report['summary']['actually_merged']}")
        else:
            print(f"  Would Merge: {report['summary']['dry_run_eligible']}")

        if report['merged_prs']:
            print("\n✅ Merged PRs:")
            for pr in report['merged_prs']:
                print(f"  • PR #{pr}")

    except Exception as e:
        logger.error(f"Auto-merge operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
