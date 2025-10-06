#!/usr/bin/env python3
"""
254Carbon Meta Repository - Quality Issue Creation

Creates GitHub issues for services with failing quality metrics.

Usage:
    python scripts/create_quality_issues.py [--dry-run] [--threshold 70]
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
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
        logging.FileHandler('catalog/quality-issues.log')
    ]
)
logger = logging.getLogger(__name__)


class GitHubAPI:
    """GitHub API client for issue management."""

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

    def get_existing_issues(self, label: str = None) -> List[Dict[str, Any]]:
        """Get existing issues with optional label filter."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/issues"

        params = {
            "state": "open",
            "per_page": 100
        }

        if label:
            params["labels"] = label

        response = self.session.get(url, params=params)
        response.raise_for_status()

        return response.json()

    def create_issue(self, title: str, body: str, labels: List[str] = None,
                    assignee: str = None) -> Optional[str]:
        """Create a GitHub issue."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/issues"

        payload = {
            "title": title,
            "body": body
        }

        if labels:
            payload["labels"] = labels

        if assignee:
            payload["assignees"] = [assignee]

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        issue_data = response.json()
        logger.info(f"Created issue #{issue_data['number']}: {title}")
        return str(issue_data['number'])

    def update_issue(self, issue_number: int, title: str = None, body: str = None,
                   labels: List[str] = None, state: str = None) -> None:
        """Update an existing issue."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/issues/{issue_number}"

        payload = {}
        if title:
            payload["title"] = title
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if state:
            payload["state"] = state

        if payload:
            response = self.session.patch(url, json=payload)
            response.raise_for_status()
            logger.info(f"Updated issue #{issue_number}")


class QualityIssueManager:
    """Manages quality-related GitHub issues."""

    def __init__(self, github_token: str, dry_run: bool = False, threshold: float = 70.0):
        self.github = GitHubAPI(github_token)
        self.dry_run = dry_run
        self.threshold = threshold

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

    def find_failing_services(self) -> List[Dict[str, Any]]:
        """Find services below quality threshold."""
        failing_services = []

        services = self.quality_data.get('services', {})

        for service_name, service_data in services.items():
            score = service_data.get('score', 0)

            if score < self.threshold:
                failing_services.append({
                    'name': service_name,
                    'score': score,
                    'grade': service_data.get('grade', 'F'),
                    'status': service_data.get('status', 'unknown'),
                    'metrics': service_data.get('metrics', {})
                })

        # Sort by score (lowest first)
        failing_services.sort(key=lambda x: x['score'])
        return failing_services

    def check_existing_issue(self, service_name: str) -> Optional[int]:
        """Check if there's already an open issue for this service."""
        existing_issues = self.github.get_existing_issues("quality-improvement")

        for issue in existing_issues:
            # Check if issue title mentions this service
            title = issue.get('title', '').lower()
            if service_name.lower() in title and issue.get('state') == 'open':
                return issue.get('number')

        return None

    def generate_issue_title(self, service: Dict[str, Any]) -> str:
        """Generate issue title for a failing service."""
        score = service['score']
        grade = service['grade']

        if score < 50:
            return f"🚨 Critical: Improve {service['name']} quality (Score: {score:.1f}/100, Grade: {grade})"
        elif score < 60:
            return f"🔴 Urgent: Improve {service['name']} quality (Score: {score:.1f}/100, Grade: {grade})"
        else:
            return f"🟡 Improve {service['name']} quality (Score: {score:.1f}/100, Grade: {grade})"

    def generate_issue_body(self, service: Dict[str, Any]) -> str:
        """Generate issue body for a failing service."""
        name = service['name']
        score = service['score']
        grade = service['grade']
        metrics = service.get('metrics', {})

        body = f"""## 🔍 Quality Issue: {name}

**Current Status:** Score {score:.1f}/100 (Grade: {grade})

### 📊 Quality Metrics
- **Test Coverage:** {metrics.get('coverage', 0):.1%} (Target: 80%+)
- **Lint Compliance:** {'✅ Passing' if metrics.get('lint_pass', False) else '❌ Failing'}
- **Critical Vulnerabilities:** {metrics.get('critical_vulns', 0)}
- **High Vulnerabilities:** {metrics.get('high_vulns', 0)}
- **Build Success Rate:** {metrics.get('build_success_rate', 0):.1%}

### 🎯 Immediate Actions Required

1. **Review Quality Metrics** - Analyze why this service is below threshold
2. **Improve Test Coverage** - Add missing test cases
3. **Fix Security Issues** - Address any critical vulnerabilities
4. **Code Quality** - Resolve lint failures
5. **Update Dependencies** - Check for outdated dependencies

### 📋 Recommended Priority

**Priority:** {'🔴 Critical' if score < 50 else '🟠 High' if score < 60 else '🟡 Medium'}

**Estimated Effort:** {'High (2-3 weeks)' if score < 50 else 'Medium (1-2 weeks)' if score < 60 else 'Low (1 week)'}

### 🔗 Related Information

- **Service Repository:** [Link to service repo]
- **Quality Dashboard:** [Link to quality dashboard]
- **Recent Changes:** Check recent commits for potential issues

### 📞 Escalation

If this issue persists for more than 2 weeks, please:
1. Tag the platform team lead
2. Schedule a quality review meeting
3. Consider temporary quality gate exemption if justified

---
*🤖 Auto-generated by 254Carbon Meta Quality Monitoring*
*Created: {datetime.now(timezone.utc).isoformat()}*
"""

        return body

    def create_quality_issues(self) -> List[str]:
        """Create issues for failing services."""
        logger.info("Creating quality improvement issues...")

        failing_services = self.find_failing_services()
        created_issues = []

        if not failing_services:
            logger.info("✅ No services below quality threshold")
            return created_issues

        logger.info(f"Found {len(failing_services)} services below threshold {self.threshold}")

        for service in failing_services:
            service_name = service['name']

            # Check if issue already exists
            existing_issue = self.check_existing_issue(service_name)

            if existing_issue:
                logger.info(f"Issue already exists for {service_name} (#{existing_issue})")
                continue

            # Generate issue content
            title = self.generate_issue_title(service)
            body = self.generate_issue_body(service)
            labels = ["quality-improvement", "automation"]

            # Add priority label based on score
            if service['score'] < 50:
                labels.append("priority-critical")
            elif service['score'] < 60:
                labels.append("priority-high")
            else:
                labels.append("priority-medium")

            if self.dry_run:
                logger.info(f"DRY RUN: Would create issue: {title}")
                created_issues.append(f"dry-run-{service_name}")
            else:
                try:
                    issue_number = self.github.create_issue(
                        title=title,
                        body=body,
                        labels=labels,
                        assignee="254carbon-meta-bot"
                    )

                    if issue_number:
                        created_issues.append(issue_number)
                        logger.info(f"✅ Created issue #{issue_number} for {service_name}")

                except Exception as e:
                    logger.error(f"Failed to create issue for {service_name}: {e}")

        return created_issues

    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate summary report of quality issue management."""
        failing_services = self.find_failing_services()
        created_issues = self.create_quality_issues()

        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "threshold_used": self.threshold,
                "dry_run": self.dry_run
            },
            "summary": {
                "services_below_threshold": len(failing_services),
                "issues_created": len(created_issues) if not self.dry_run else 0,
                "dry_run_issues": len(created_issues) if self.dry_run else 0
            },
            "failing_services": [
                {
                    "name": s["name"],
                    "score": s["score"],
                    "grade": s["grade"],
                    "existing_issue": self.check_existing_issue(s["name"]) is not None
                }
                for s in failing_services
            ],
            "created_issues": created_issues if not self.dry_run else [f"would-create-{s['name']}" for s in failing_services]
        }

        return report


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Create GitHub issues for services with failing quality")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without creating issues")
    parser.add_argument("--threshold", type=float, default=70.0, help="Quality threshold (default: 70.0)")
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
        manager = QualityIssueManager(github_token, args.dry_run, args.threshold)
        report = manager.generate_summary_report()

        # Print summary
        print("\n📋 Quality Issue Management Summary:")
        print(f"  Services Below Threshold: {report['summary']['services_below_threshold']}")
        print(f"  Issues Created: {report['summary']['issues_created']}")
        print(f"  Dry Run Issues: {report['summary']['dry_run_issues']}")

        if report['failing_services']:
            print("\n🔍 Failing Services:")
            for service in report['failing_services'][:5]:
                existing = " (existing issue)" if service['existing_issue'] else ""
                print(f"  • {service['name']}: {service['score']:.1f}/100{existing}")

        if report['created_issues']:
            print("\n✅ Created Issues:")
            for issue in report['created_issues'][:5]:
                print(f"  • Issue #{issue}")

    except Exception as e:
        logger.error(f"Quality issue creation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
