#!/usr/bin/env python3
"""
254Carbon Meta Repository - Upgrade PR Monitoring

Monitors the status of upgrade pull requests.

Usage:
    python scripts/monitor_upgrade_prs.py [--days 7] [--status open|closed|merged]
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
        logging.FileHandler('catalog/upgrade-monitoring.log')
    ]
)
logger = logging.getLogger(__name__)


class GitHubAPI:
    """GitHub API client for PR monitoring."""

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

    def get_prs_by_label(self, label: str, days: int = 7) -> List[Dict[str, Any]]:
        """Get PRs with specific label from last N days."""
        since_date = datetime.now(timezone.utc) - timedelta(days=days)

        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls"
        params = {
            "labels": label,
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": 50
        }

        response = self.session.get(url, params=params)
        response.raise_for_status()

        prs = response.json()

        # Filter to PRs updated in the last N days
        recent_prs = []
        for pr in prs:
            updated_at = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))
            if updated_at >= since_date:
                recent_prs.append(pr)

        return recent_prs

    def get_pr_status(self, pr_number: int) -> Dict[str, Any]:
        """Get detailed status of a PR."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls/{pr_number}"

        response = self.session.get(url)
        response.raise_for_status()

        pr_data = response.json()

        # Get checks/status
        checks_url = pr_data.get('statuses_url', '').replace('{/sha}', f"/{pr_data['head']['sha']}")
        if checks_url.startswith('https://'):
            checks_response = self.session.get(checks_url)
            checks_response.raise_for_status()
            pr_data['status_checks'] = checks_response.json()
        else:
            pr_data['status_checks'] = []

        return pr_data


class UpgradePRMonitor:
    """Monitors upgrade PR status and progress."""

    def __init__(self, github_token: str, days: int = 7, status_filter: str = None):
        self.github = GitHubAPI(github_token)
        self.days = days
        self.status_filter = status_filter

        # Upgrade-related labels to monitor
        self.upgrade_labels = ["auto-upgrade", "spec-upgrade", "dependency-upgrade"]

    def find_upgrade_prs(self) -> List[Dict[str, Any]]:
        """Find all upgrade-related PRs."""
        all_prs = []

        for label in self.upgrade_labels:
            try:
                prs = self.github.get_prs_by_label(label, self.days)
                all_prs.extend(prs)
            except Exception as e:
                logger.warning(f"Failed to get PRs for label {label}: {e}")

        # Remove duplicates (PRs might have multiple upgrade labels)
        seen = set()
        unique_prs = []
        for pr in all_prs:
            pr_id = pr['number']
            if pr_id not in seen:
                unique_prs.append(pr)
                seen.add(pr_id)

        return unique_prs

    def analyze_pr_status(self, pr: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze the status of an upgrade PR."""
        pr_number = pr['number']
        status = pr.get('state', 'unknown')

        # Get detailed status
        try:
            detailed_pr = self.github.get_pr_status(pr_number)
            status_checks = detailed_pr.get('status_checks', [])

            # Analyze CI/CD status
            ci_status = "unknown"
            if status_checks:
                # Check if all required checks passed
                required_checks = ['test', 'build', 'lint']
                check_results = {}

                for check in status_checks:
                    check_name = check.get('context', '').lower()
                    check_state = check.get('state', 'pending')

                    for req_check in required_checks:
                        if req_check in check_name:
                            check_results[req_check] = check_state

                # Determine overall CI status
                if all(state == 'success' for state in check_results.values()):
                    ci_status = "passing"
                elif any(state == 'failure' for state in check_results.values()):
                    ci_status = "failing"
                elif any(state == 'pending' for state in check_results.values()):
                    ci_status = "pending"
                else:
                    ci_status = "unknown"

        except Exception as e:
            logger.warning(f"Failed to get detailed status for PR #{pr_number}: {e}")
            ci_status = "unknown"

        # Analyze PR metadata
        labels = [label['name'] for label in pr.get('labels', [])]
        created_at = datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00'))
        updated_at = datetime.fromisoformat(pr['updated_at'].replace('Z', '+00:00'))

        # Determine age category
        age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
        if age_hours < 24:
            age_category = "fresh"
        elif age_hours < 72:
            age_category = "recent"
        else:
            age_category = "stale"

        return {
            'pr_number': pr_number,
            'title': pr['title'],
            'status': status,
            'ci_status': ci_status,
            'labels': labels,
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
            'age_hours': round(age_hours, 1),
            'age_category': age_category,
            'author': pr['user']['login'],
            'mergeable': pr.get('mergeable', False),
            'draft': pr.get('draft', False)
        }

    def generate_monitoring_report(self) -> Dict[str, Any]:
        """Generate comprehensive upgrade PR monitoring report."""
        logger.info("Monitoring upgrade PRs...")

        # Find upgrade PRs
        upgrade_prs = self.find_upgrade_prs()

        if not upgrade_prs:
            logger.info("No upgrade PRs found")
            return {"error": "No upgrade PRs found"}

        # Analyze each PR
        pr_analyses = []
        for pr in upgrade_prs:
            try:
                analysis = self.analyze_pr_status(pr)
                pr_analyses.append(analysis)
            except Exception as e:
                logger.error(f"Failed to analyze PR #{pr['number']}: {e}")

        # Generate summary statistics
        total_prs = len(pr_analyses)
        open_prs = len([p for p in pr_analyses if p['status'] == 'open'])
        merged_prs = len([p for p in pr_analyses if p['status'] == 'closed' and p.get('merged', False)])
        failed_prs = len([p for p in pr_analyses if p['status'] == 'closed' and not p.get('merged', False)])

        # CI/CD status breakdown
        ci_passing = len([p for p in pr_analyses if p['ci_status'] == 'passing'])
        ci_failing = len([p for p in pr_analyses if p['ci_status'] == 'failing'])
        ci_pending = len([p for p in pr_analyses if p['ci_status'] == 'pending'])

        # Age distribution
        fresh_prs = len([p for p in pr_analyses if p['age_category'] == 'fresh'])
        recent_prs = len([p for p in pr_analyses if p['age_category'] == 'recent'])
        stale_prs = len([p for p in pr_analyses if p['age_category'] == 'stale'])

        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "monitoring_period_days": self.days,
                "total_upgrade_prs": total_prs
            },
            "summary": {
                "open_prs": open_prs,
                "merged_prs": merged_prs,
                "failed_prs": failed_prs,
                "ci_passing": ci_passing,
                "ci_failing": ci_failing,
                "ci_pending": ci_pending,
                "fresh_prs": fresh_prs,
                "recent_prs": recent_prs,
                "stale_prs": stale_prs
            },
            "pr_details": pr_analyses,
            "recommendations": self._generate_monitoring_recommendations(pr_analyses)
        }

        return report

    def _generate_monitoring_recommendations(self, pr_analyses: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations based on PR monitoring."""
        recommendations = []

        # Check for stale PRs
        stale_prs = [p for p in pr_analyses if p['age_category'] == 'stale' and p['status'] == 'open']
        if stale_prs:
            recommendations.append(f"📅 {len(stale_prs)} stale PRs need attention")

        # Check for failing CI
        failing_prs = [p for p in pr_analyses if p['ci_status'] == 'failing']
        if failing_prs:
            recommendations.append(f"❌ {len(failing_prs)} PRs have failing CI checks")

        # Check for pending PRs
        pending_prs = [p for p in pr_analyses if p['ci_status'] == 'pending' and p['age_hours'] > 24]
        if pending_prs:
            recommendations.append(f"⏳ {len(pending_prs)} PRs have been pending CI for over 24 hours")

        # Check for mergeable PRs ready for auto-merge
        ready_for_merge = [
            p for p in pr_analyses
            if p['status'] == 'open' and p['ci_status'] == 'passing' and p['mergeable'] and not p['draft']
        ]
        if ready_for_merge:
            recommendations.append(f"✅ {len(ready_for_merge)} PRs are ready for merge")

        if not recommendations:
            recommendations.append("✅ All upgrade PRs are healthy")

        return recommendations


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Monitor upgrade pull request status")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")
    parser.add_argument("--status", choices=["open", "closed", "all"], default="all",
                       help="PR status filter (default: all)")
    parser.add_argument("--github-token", help="GitHub token (default: GITHUB_TOKEN env var)")
    parser.add_argument("--output-file", type=str, help="Output file for monitoring report")
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
        monitor = UpgradePRMonitor(github_token, args.days, args.status)
        report = monitor.generate_monitoring_report()

        if args.output_file:
            with open(args.output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Monitoring report saved to {args.output_file}")
        else:
            # Print formatted report
            print("\n📊 Upgrade PR Monitoring Report:")
            print(f"  Period: {args.days} days")
            print(f"  Total PRs: {report['metadata']['total_upgrade_prs']}")

            summary = report['summary']
            print(f"  Open: {summary['open_prs']}")
            print(f"  Merged: {summary['merged_prs']}")
            print(f"  Failed: {summary['failed_prs']}")
            print(f"  CI Passing: {summary['ci_passing']}")
            print(f"  CI Failing: {summary['ci_failing']}")
            print(f"  CI Pending: {summary['ci_pending']}")

            print("\n⏰ Age Distribution:")
            print(f"  Fresh (<24h): {summary['fresh_prs']}")
            print(f"  Recent (24-72h): {summary['recent_prs']}")
            print(f"  Stale (>72h): {summary['stale_prs']}")

            if report['recommendations']:
                print("\n💡 Recommendations:")
                for rec in report['recommendations']:
                    print(f"  {rec}")

    except Exception as e:
        logger.error(f"Upgrade PR monitoring failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
