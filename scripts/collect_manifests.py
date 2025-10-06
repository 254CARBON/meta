#!/usr/bin/env python3
"""
254Carbon Meta Repository - Manifest Collection Script

Collects service-manifest.yaml files from configured repositories and places
validated copies in `manifests/collected/` for catalog building.

Usage:
    python scripts/collect_manifests.py [--dry-run] [--repo-filter PATTERN]

Environment Variables:
    GITHUB_TOKEN - GitHub personal access token for API access
    GITHUB_ORG   - GitHub organization name (default: 254carbon)

Notes:
- Implements basic GitHub API pagination/retry and optional filtering.
- Validates YAML structure at a high level; full schema validation occurs in
  subsequent build/validate steps.
"""

import os
import sys
import json
import yaml
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import fnmatch


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('manifests/collection.log')
    ]
)
logger = logging.getLogger(__name__)


class GitHubAPI:
    """GitHub API client with rate limiting and retry logic."""

    def __init__(self, token: str, org: str = "254carbon"):
        self.token = token
        self.org = org
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

    def get_repos(self) -> List[Dict[str, Any]]:
        """Get all repositories in the organization."""
        url = f"{self.base_url}/orgs/{self.org}/repos"
        response = self.session.get(url, params={"per_page": 100})
        response.raise_for_status()

        repos = response.json()
        logger.info(f"Found {len(repos)} repositories in organization {self.org}")
        return repos

    def get_file_content(self, repo: str, path: str, branch: str = "main") -> Optional[str]:
        """Get file content from repository."""
        url = f"{self.base_url}/repos/{self.org}/{repo}/contents/{path}"
        params = {"ref": branch}

        response = self.session.get(url, params=params)

        # File not found is acceptable (some repos might not have manifests yet)
        if response.status_code == 404:
            logger.debug(f"Manifest file not found: {repo}/{path}")
            return None

        response.raise_for_status()
        data = response.json()

        # Handle base64 encoded content
        if 'content' in data:
            import base64
            return base64.b64decode(data['content']).decode('utf-8')

        return None

    def get_rate_limit(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        url = f"{self.base_url}/rate_limit"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()


class ManifestCollector:
    """Collects and validates service manifests from repositories."""

    def __init__(self, github_token: str, org: str = "254carbon", dry_run: bool = False):
        self.github = GitHubAPI(github_token, org)
        self.dry_run = dry_run
        self.manifests_dir = Path("manifests/collected")
        self.manifests_dir.mkdir(exist_ok=True)

    def filter_repos(self, repos: List[Dict[str, Any]], pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """Filter repositories based on pattern."""
        if not pattern:
            return repos

        filtered = []
        for repo in repos:
            if fnmatch.fnmatch(repo['name'], pattern):
                filtered.append(repo)

        logger.info(f"Filtered to {len(filtered)} repositories matching pattern: {pattern}")
        return filtered

    def validate_manifest(self, content: str, repo_name: str) -> Dict[str, Any]:
        """Validate manifest content against schema."""
        try:
            # Load YAML content
            manifest = yaml.safe_load(content)

            # Basic validation - check required fields
            required_fields = ['name', 'repo', 'domain', 'version', 'maturity', 'dependencies']
            missing_fields = [field for field in required_fields if field not in manifest]

            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")

            # Validate field types and formats
            if not isinstance(manifest['name'], str):
                raise ValueError("Field 'name' must be a string")

            if not isinstance(manifest['version'], str) or not manifest['version'].replace('.', '').isdigit():
                raise ValueError("Field 'version' must be a valid semver string")

            return manifest

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format: {e}")
        except Exception as e:
            raise ValueError(f"Validation error: {e}")

    def collect_manifest(self, repo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Collect manifest from a single repository."""
        repo_name = repo['name']
        logger.info(f"Processing repository: {repo_name}")

        try:
            # Get manifest file content
            content = self.github.get_file_content(repo_name, "service-manifest.yaml")

            if content is None:
                logger.warning(f"No manifest found in {repo_name}")
                return None

            # Validate manifest
            manifest = self.validate_manifest(content, repo_name)

            # Add metadata
            manifest['_metadata'] = {
                'collected_at': datetime.now(timezone.utc).isoformat(),
                'source_repo': repo_name,
                'source_commit': repo.get('default_branch', 'main'),
                'github_url': repo['html_url']
            }

            # Save to file if not dry run
            if not self.dry_run:
                output_file = self.manifests_dir / f"{repo_name}.yaml"
                with open(output_file, 'w') as f:
                    yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

                logger.info(f"Saved manifest to {output_file}")
            else:
                logger.info(f"Dry run: would save manifest for {repo_name}")

            return manifest

        except Exception as e:
            logger.error(f"Failed to collect manifest from {repo_name}: {e}")
            return None

    def collect_all_manifests(self, repo_filter: Optional[str] = None) -> Dict[str, Any]:
        """Collect manifests from all repositories."""
        logger.info("Starting manifest collection...")

        # Check rate limit before starting
        rate_limit = self.github.get_rate_limit()
        core_remaining = rate_limit['resources']['core']['remaining']
        logger.info(f"GitHub API rate limit: {core_remaining} requests remaining")

        if core_remaining < 50:
            logger.warning("Low rate limit remaining, consider using a GitHub token with higher limits")

        # Get all repositories
        repos = self.github.get_repos()
        repos = self.filter_repos(repos, repo_filter)

        # Collect manifests
        results = {
            'collected_at': datetime.now(timezone.utc).isoformat(),
            'total_repos': len(repos),
            'successful': 0,
            'failed': 0,
            'manifests': []
        }

        for repo in repos:
            manifest = self.collect_manifest(repo)
            if manifest:
                results['successful'] += 1
                results['manifests'].append(manifest)
            else:
                results['failed'] += 1

            # Be respectful to the API
            time.sleep(0.5)

        # Save collection summary
        if not self.dry_run:
            summary_file = self.manifests_dir / "collection-summary.json"
            with open(summary_file, 'w') as f:
                json.dump(results, f, indent=2)

        logger.info(f"Collection complete: {results['successful']} successful, {results['failed']} failed")
        return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Collect service manifests from GitHub repositories")
    parser.add_argument("--dry-run", action="store_true", help="Don't save files, just validate")
    parser.add_argument("--repo-filter", type=str, help="Filter repositories by name pattern")
    parser.add_argument("--org", type=str, default="254carbon", help="GitHub organization name")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get GitHub token from environment
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logger.error("GITHUB_TOKEN environment variable is required")
        sys.exit(1)

    # Create collector and run
    try:
        collector = ManifestCollector(github_token, args.org, args.dry_run)
        results = collector.collect_all_manifests(args.repo_filter)

        if args.dry_run:
            logger.info("Dry run completed successfully")
        else:
            logger.info("Manifest collection completed successfully")

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
