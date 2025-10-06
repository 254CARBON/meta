#!/usr/bin/env python3
"""
254Carbon Meta Repository - Quality Change Comments

Posts quality change comments on recent PRs.

Usage:
    python scripts/comment_quality_changes.py [--days 7] [--dry-run]
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
        logging.FileHandler('catalog/quality-comments.log')
    ]
)
logger = logging.getLogger(__name__)


class GitHubAPI:
    """GitHub API client for PR comments."""

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

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)

    def get_recent_prs(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get PRs from the last N days."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls"

        since_date = datetime.now(timezone.utc) - timedelta(days=days)

        params = {
            "state": "closed",  # Only closed PRs (merged or closed)
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

    def get_pr_comments(self, pr_number: int) -> List[Dict[str, Any]]:
        """Get comments on a PR."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/issues/{pr_number}/comments"

        response = self.session.get(url)
        response.raise_for_status()

        return response.json()

    def post_pr_comment(self, pr_number: int, comment: str) -> None:
        """Post a comment on a PR."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/issues/{pr_number}/comments"

        payload = {
            "body": comment
        }

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        logger.info(f"Posted comment on PR #{pr_number}")

    def check_existing_comment(self, pr_number: int, comment_signature: str) -> bool:
        """Check if a comment with specific signature already exists."""
        comments = self.get_pr_comments(pr_number)

        for comment in comments:
            if comment_signature in comment.get('body', ''):
                return True

        return False


class QualityChangeDetector:
    """Detects quality changes and generates PR comments."""

    def __init__(self, github_token: str, dry_run: bool = False, days: int = 7):
        self.github = GitHubAPI(github_token)
        self.dry_run = dry_run
        self.days = days

        # Load quality data
        self.quality_data = self._load_quality_data()

    def _load_quality_data(self) -> Dict[str, Any]:
        """Load latest quality snapshot."""
        quality_file = Path("catalog/latest_quality_snapshot.json")

        if not quality_file.exists():
            logger.error("No quality data found. Run 'make quality' first.")
            return {}

        try:
            with open(quality_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load quality data: {e}")
            return {}

    def find_quality_changes(self) -> Dict[str, Dict[str, Any]]:
        """Find services with significant quality changes."""
        # This would require historical quality data to detect changes
        # For now, we'll identify services with concerning quality levels

        services = self.quality_data.get('services', {})
        changes = {}

        for service_name, service_data in services.items():
            score = service_data.get('score', 0)
            grade = service_data.get('grade', 'F')

            # Identify concerning quality levels
            if score < 60:
                changes[service_name] = {
                    'type': 'low_quality',
                    'severity': 'critical' if score < 50 else 'high',
                    'current_score': score,
                    'current_grade': grade,
                    'message': f"Service quality is concerning: {score:.1f}/100 (Grade: {grade})"
                }
            elif score > 85:
                changes[service_name] = {
                    'type': 'high_quality',
                    'severity': 'positive',
                    'current_score': score,
                    'current_grade': grade,
                    'message': f"Service quality is excellent: {score:.1f}/100 (Grade: {grade})"
                }

        return changes

    def generate_quality_comment(self, pr_data: Dict[str, Any], quality_changes: Dict[str, Dict[str, Any]]) -> str:
        """Generate quality comment for a PR."""
        pr_number = pr_data['number']
        pr_title = pr_data['title']
        pr_author = pr_data['user']['login']

        # Filter changes to services likely affected by this PR
        # This is a simplified heuristic - in reality would need better PR analysis
        affected_services = self._identify_affected_services(pr_data, quality_changes)

        if not affected_services:
            return None

        comment = f"""## 🔍 Quality Impact Analysis

**PR:** #{pr_number} - {pr_title}
**Author:** @{pr_author}

### 📊 Quality Status for Affected Services

| Service | Current Score | Grade | Status |
|---------|---------------|-------|--------|
"""

        for service_name in affected_services[:5]:  # Limit to top 5
            change = quality_changes.get(service_name)
            if change:
                score = change['current_score']
                grade = change['current_grade']
                status_icon = {
                    'critical': '🔴',
                    'high': '🟠',
                    'positive': '🟢'
                }.get(change['severity'], '⚪')

                comment += f"| **{service_name}** | {score:.1f}/100 | {grade} | {status_icon} {change['severity'].title()} |\n"

        comment += "\n### 🎯 Recommendations\n\n"

        critical_services = [s for s in affected_services if quality_changes.get(s, {}).get('severity') == 'critical']
        if critical_services:
            comment += f"🚨 **Critical:** Please review quality for: {', '.join(critical_services[:3])}\n\n"

        high_services = [s for s in affected_services if quality_changes.get(s, {}).get('severity') == 'high']
        if high_services:
            comment += f"⚠️ **Attention:** Monitor quality for: {', '.join(high_services[:3])}\n\n"

        comment += """### 📈 Quality Monitoring

This PR may impact service quality metrics. The quality monitoring system will:
- Track quality scores for affected services
- Alert if quality degrades significantly
- Suggest improvements if quality falls below thresholds

If you have questions about quality metrics or need help improving them, please reach out to the platform team.

---
*🤖 Automated quality analysis by 254Carbon Meta*
"""

        return comment

    def _identify_affected_services(self, pr_data: Dict[str, Any], quality_changes: Dict[str, Dict[str, Any]]) -> List[str]:
        """Identify services likely affected by this PR (simplified heuristic)."""
        # This is a simplified implementation
        # In reality, would analyze PR files, commit messages, etc.

        affected = []

        # Check if PR title mentions specific services
        pr_title = pr_data['title'].lower()
        for service_name in quality_changes.keys():
            if service_name.lower() in pr_title:
                affected.append(service_name)

        # If no specific services mentioned, include services with concerning quality
        if not affected:
            concerning_services = [
                name for name, change in quality_changes.items()
                if change['severity'] in ['critical', 'high']
            ]
            affected.extend(concerning_services[:3])  # Limit to 3

        return affected

    def comment_recent_prs(self) -> List[str]:
        """Comment on recent PRs with quality information."""
        logger.info("Commenting on recent PRs with quality information...")

        # Get recent PRs
        recent_prs = self.github.get_recent_prs(self.days)
        commented_prs = []

        if not recent_prs:
            logger.info("No recent PRs found to comment on")
            return commented_prs

        # Find quality changes
        quality_changes = self.find_quality_changes()

        if not quality_changes:
            logger.info("No significant quality changes to report")
            return commented_prs

        for pr in recent_prs:
            pr_number = pr['number']

            # Check if we've already commented on this PR
            comment_signature = "254Carbon Meta"
            if self.github.check_existing_comment(pr_number, comment_signature):
                logger.debug(f"Already commented on PR #{pr_number}")
                continue

            # Generate comment
            comment = self.generate_quality_comment(pr, quality_changes)

            if comment:
                if self.dry_run:
                    logger.info(f"DRY RUN: Would comment on PR #{pr_number}")
                    commented_prs.append(f"dry-run-{pr_number}")
                else:
                    try:
                        self.github.post_pr_comment(pr_number, comment)
                        commented_prs.append(str(pr_number))
                    except Exception as e:
                        logger.error(f"Failed to comment on PR #{pr_number}: {e}")

        return commented_prs


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Post quality change comments on recent PRs")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be commented without posting")
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
        detector = QualityChangeDetector(github_token, args.dry_run, args.days)
        commented_prs = detector.comment_recent_prs()

        # Print summary
        print("\n💬 Quality Comments Summary:")
        print(f"  Days Analyzed: {args.days}")
        print(f"  PRs Commented: {len(commented_prs) if not args.dry_run else 0}")
        print(f"  Dry Run Comments: {len(commented_prs) if args.dry_run else 0}")

        if commented_prs:
            print("\n✅ Commented PRs:")
            for pr in commented_prs[:5]:
                print(f"  • PR #{pr}")

    except Exception as e:
        logger.error(f"Quality comment posting failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
