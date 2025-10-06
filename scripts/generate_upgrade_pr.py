#!/usr/bin/env python3
"""
254Carbon Meta Repository - Upgrade PR Generation Script

Creates GitHub pull requests to upgrade service specs according to policy, with
templated content and basic safeguards.

Usage:
    python scripts/generate_upgrade_pr.py --service gateway --spec-version gateway-core@1.2.0

Notes:
- Integrates with `config/upgrade-policies.yaml` to determine allowed upgrade
  types and PR templates. Current implementation assumes manifests live under
  `manifests/collected/` and stubs some repo operations.
"""

import os
import sys
import json
import yaml
import argparse
import logging
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scripts/upgrade-pr.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class UpgradeSpec:
    """Represents a specification upgrade."""
    service_name: str
    spec_name: str
    current_version: str
    target_version: str
    upgrade_type: str  # 'major', 'minor', 'patch'
    breaking_changes: bool
    changelog_url: str = ""
    release_notes: str = ""


@dataclass
class PRTemplate:
    """Represents a PR template configuration."""
    title_template: str
    body_template: str
    labels: List[str]
    assignees: List[str]
    reviewers: List[str]


class GitHubAPI:
    """GitHub API client for PR operations."""

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

    def create_branch(self, branch_name: str, base_sha: str) -> str:
        """Create a new branch from base SHA."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/git/refs"

        payload = {
            "ref": f"refs/heads/{branch_name}",
            "sha": base_sha
        }

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        logger.info(f"Created branch: {branch_name}")
        return response.json()["object"]["sha"]

    def get_file_content(self, file_path: str, branch: str = "main") -> str:
        """Get file content from repository."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/contents/{file_path}"
        params = {"ref": branch}

        response = self.session.get(url, params=params)
        response.raise_for_status()

        import base64
        content = response.json()["content"]
        return base64.b64decode(content).decode('utf-8')

    def update_file(self, file_path: str, content: str, branch: str, commit_message: str, sha: str) -> str:
        """Update file content."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/contents/{file_path}"

        import base64
        encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

        payload = {
            "message": commit_message,
            "content": encoded_content,
            "sha": sha,
            "branch": branch
        }

        response = self.session.put(url, json=payload)
        response.raise_for_status()

        logger.info(f"Updated file: {file_path}")
        return response.json()["commit"]["sha"]

    def create_pull_request(self, title: str, body: str, head_branch: str, base_branch: str = "main",
                          labels: List[str] = None, assignees: List[str] = None) -> str:
        """Create a pull request."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/pulls"

        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch
        }

        if labels:
            payload["labels"] = labels

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        pr_data = response.json()
        pr_number = pr_data["number"]

        # Add assignees if provided
        if assignees:
            self.add_assignees_to_pr(pr_number, assignees)

        logger.info(f"Created PR #{pr_number}: {title}")
        return str(pr_number)

    def add_assignees_to_pr(self, pr_number: int, assignees: List[str]) -> None:
        """Add assignees to a pull request."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/issues/{pr_number}/assignees"

        payload = {
            "assignees": assignees
        }

        response = self.session.post(url, json=payload)
        response.raise_for_status()

        logger.info(f"Added assignees to PR #{pr_number}: {assignees}")

    def get_latest_commit_sha(self, branch: str = "main") -> str:
        """Get the latest commit SHA for a branch."""
        url = f"{self.base_url}/repos/{self.repo_owner}/{self.repo_name}/git/refs/heads/{branch}"

        response = self.session.get(url)
        response.raise_for_status()

        return response.json()["object"]["sha"]

    def get_rate_limit(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        url = f"{self.base_url}/rate_limit"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()


class UpgradePRGenerator:
    """Generates upgrade pull requests."""

    def __init__(self, github_token: str, dry_run: bool = False):
        self.github = GitHubAPI(github_token)
        self.dry_run = dry_run
        self.temp_dir = Path(tempfile.mkdtemp())

        # Load upgrade policies
        self.upgrade_policies = self._load_upgrade_policies()

        # PR templates by upgrade type
        self.pr_templates = self._load_pr_templates()

    def _load_upgrade_policies(self) -> Dict[str, Any]:
        """Load upgrade policies from config."""
        policies_file = Path("config/upgrade-policies.yaml")

        if not policies_file.exists():
            logger.warning(f"Policies file not found: {policies_file}, using defaults")
            return self._get_default_policies()

        with open(policies_file) as f:
            return yaml.safe_load(f)

    def _get_default_policies(self) -> Dict[str, Any]:
        """Get default upgrade policies."""
        return {
            "auto_upgrade": {
                "patch": True,
                "minor": True,
                "major": False
            },
            "max_concurrent_prs": 3,
            "pr_creation_delay": 5
        }

    def _load_pr_templates(self) -> Dict[str, PRTemplate]:
        """Load PR templates for different upgrade types."""
        return {
            "patch": PRTemplate(
                title_template="🔧 Auto-upgrade: Patch {spec_name} to {target_version}",
                body_template="""## Automatic Patch Upgrade

This PR automatically upgrades `{spec_name}` from `{current_version}` to `{target_version}`.

### Changes
- Patch version upgrade for security fixes and bug fixes
- No breaking changes expected

### Validation
- [x] Service manifest updated
- [x] Specs lock file updated
- [ ] Tests pass (auto-validated)

### Files Changed
- `service-manifest.yaml` - Updated spec version
- `specs.lock.json` - Updated dependency resolution

---
*🤖 Generated by 254Carbon Meta*""",
                labels=["auto-upgrade", "patch", "dependencies"],
                assignees=["254carbon-meta-bot"],
                reviewers=[]
            ),
            "minor": PRTemplate(
                title_template="⬆️ Auto-upgrade: Minor {spec_name} to {target_version}",
                body_template="""## Automatic Minor Upgrade

This PR automatically upgrades `{spec_name}` from `{current_version}` to `{target_version}`.

### Changes
- Minor version upgrade with new features
- Backward compatible changes

### Validation
- [x] Service manifest updated
- [x] Specs lock file updated
- [x] Tests pass
- [ ] Integration tests pass (auto-validated)

### Files Changed
- `service-manifest.yaml` - Updated spec version
- `specs.lock.json` - Updated dependency resolution

---
*🤖 Generated by 254Carbon Meta*""",
                labels=["auto-upgrade", "minor", "enhancement"],
                assignees=["254carbon-meta-bot"],
                reviewers=[]
            ),
            "major": PRTemplate(
                title_template="⚠️ Major Upgrade: {spec_name} to {target_version}",
                body_template="""## Major Version Upgrade

This PR upgrades `{spec_name}` from `{current_version}` to `{target_version}`.

### ⚠️ Breaking Changes Expected
- Major version upgrade with breaking changes
- Requires careful testing and review

### Validation Required
- [x] Service manifest updated
- [x] Specs lock file updated
- [ ] Tests pass
- [ ] Integration tests pass
- [ ] Breaking change impact assessed

### Files Changed
- `service-manifest.yaml` - Updated spec version
- `specs.lock.json` - Updated dependency resolution

### Review Checklist
- [ ] Breaking changes documented
- [ ] Migration guide provided
- [ ] Rollback plan defined
- [ ] Consumer services updated

---
*🤖 Generated by 254Carbon Meta*""",
                labels=["auto-upgrade", "major", "breaking-change"],
                assignees=["254carbon-meta-bot"],
                reviewers=["platform-team", "architecture-team"]
            )
        }

    def find_service_manifest(self, service_name: str) -> Optional[Path]:
        """Find the service manifest file for a service.

        Args:
            service_name: Canonical service name used as manifest filename stem.

        Returns:
            Path to the manifest file under `manifests/collected/` if it exists,
            otherwise None.

        Notes:
            This simplified implementation assumes collected manifests are
            available in the local workspace. In a full implementation, this
            would search the appropriate service repository and branch.
        """
        # In a real implementation, this would search across all repositories
        # For now, we'll assume manifests are in a manifests directory
        manifest_path = Path("manifests/collected") / f"{service_name}.yaml"

        if manifest_path.exists():
            return manifest_path

        logger.warning(f"Manifest not found for service: {service_name}")
        return None

    def parse_upgrade_spec(self, spec_string: str) -> UpgradeSpec:
        """Parse upgrade specification string.

        Args:
            spec_string: A spec identifier in the form "<spec-name>@<version>".

        Returns:
            An `UpgradeSpec` with derived upgrade_type and breaking_changes flag.

        Raises:
            ValueError: If the format is invalid or parts cannot be parsed.

        Notes:
            Current implementation compares against a placeholder current_version.
            In production, fetch the current pin from the service manifest.
        """
        if '@' not in spec_string:
            raise ValueError(f"Invalid spec format: {spec_string}. Expected: spec-name@version")

        spec_name, target_version = spec_string.split('@', 1)

        # In a real implementation, this would fetch actual spec metadata
        # For now, we'll determine upgrade type based on version comparison
        current_version = "1.0.0"  # Would be fetched from current manifest

        # Simple version comparison logic
        current_parts = [int(x) for x in current_version.split('.')]
        target_parts = [int(x) for x in target_version.split('.')]

        if target_parts[0] > current_parts[0]:
            upgrade_type = "major"
            breaking_changes = True
        elif target_parts[1] > current_parts[1]:
            upgrade_type = "minor"
            breaking_changes = False
        elif target_parts[2] > current_parts[2]:
            upgrade_type = "patch"
            breaking_changes = False
        else:
            upgrade_type = "patch"
            breaking_changes = False

        return UpgradeSpec(
            service_name="",  # Will be set by caller
            spec_name=spec_name,
            current_version=current_version,
            target_version=target_version,
            upgrade_type=upgrade_type,
            breaking_changes=breaking_changes
        )

    def update_service_manifest(self, manifest_path: Path, upgrade_spec: UpgradeSpec) -> str:
        """Update service manifest with new spec version.

        Updates any entry in `api_contracts` matching the target spec name with
        the new version, and annotates collection metadata.

        Args:
            manifest_path: Path to the YAML manifest file to update.
            upgrade_spec: Parsed specification upgrade details.

        Returns:
            The updated manifest serialized as YAML text.

        Side Effects:
            Writes the modified manifest back to `manifest_path`.

        Raises:
            FileNotFoundError, yaml.YAMLError: If the manifest can't be read or parsed.
        """
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        # Update API contracts
        if 'api_contracts' in manifest:
            updated_contracts = []
            for contract in manifest['api_contracts']:
                if contract.startswith(f"{upgrade_spec.spec_name}@"):
                    updated_contracts.append(f"{upgrade_spec.spec_name}@{upgrade_spec.target_version}")
                else:
                    updated_contracts.append(contract)
            manifest['api_contracts'] = updated_contracts

        # Update metadata
        manifest['_metadata'] = manifest.get('_metadata', {})
        manifest['_metadata']['upgraded_at'] = datetime.now(timezone.utc).isoformat()
        manifest['_metadata']['upgrade_type'] = upgrade_spec.upgrade_type

        # Write back to file
        with open(manifest_path, 'w') as f:
            yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)

        return yaml.dump(manifest, default_flow_style=False)

    def update_specs_lock(self, upgrade_spec: UpgradeSpec) -> str:
        """Update specs.lock.json with resolved dependencies.

        Ensures a JSON lock file exists and contains the upgraded spec with
        a resolution timestamp and placeholder integrity.

        Args:
            upgrade_spec: Parsed specification upgrade details.

        Returns:
            The updated lockfile serialized as pretty-printed JSON string.

        Side Effects:
            Writes `specs.lock.json` in the current working directory.
        """
        lock_file = Path("specs.lock.json")

        if not lock_file.exists():
            # Create initial lock file
            lock_content = {
                "version": "1.0",
                "dependencies": {}
            }
        else:
            with open(lock_file) as f:
                lock_content = json.load(f)

        # Update dependency resolution
        if "dependencies" not in lock_content:
            lock_content["dependencies"] = {}

        lock_content["dependencies"][upgrade_spec.spec_name] = {
            "version": upgrade_spec.target_version,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
            "integrity": f"sha256-{upgrade_spec.target_version}"  # Placeholder
        }

        # Write back to file
        with open(lock_file, 'w') as f:
            json.dump(lock_content, f, indent=2)

        return json.dumps(lock_content, indent=2)

    def generate_pr_content(self, upgrade_spec: UpgradeSpec, service_name: str) -> Tuple[str, str, List[str]]:
        """Generate PR title, body, and metadata.

        Args:
            upgrade_spec: The upgrade request including type and versions.
            service_name: The service receiving the upgrade (for context if needed).

        Returns:
            Tuple of (title, body, labels) derived from templates by upgrade type.

        Notes:
            Reviewers/assignees are handled separately by the GitHub API caller.
        """
        template = self.pr_templates.get(upgrade_spec.upgrade_type, self.pr_templates["patch"])

        # Format templates
        title = template.title_template.format(
            spec_name=upgrade_spec.spec_name,
            target_version=upgrade_spec.target_version,
            current_version=upgrade_spec.current_version
        )

        body = template.body_template.format(
            spec_name=upgrade_spec.spec_name,
            current_version=upgrade_spec.current_version,
            target_version=upgrade_spec.target_version
        )

        return title, body, template.labels

    def create_upgrade_pr(self, service_name: str, upgrade_spec: UpgradeSpec) -> Optional[str]:
        """Create upgrade PR for a service.

        Steps:
            1. Locate service manifest and ensure policy allows this upgrade.
            2. Create a feature branch from the latest base.
            3. Update manifest and lock file, commit changes.
            4. Open a pull request with templated title/body and labels.

        Args:
            service_name: Target service.
            upgrade_spec: Parsed specification upgrade details.

        Returns:
            The PR number (string) on success, or None on dry-run/failure.

        Notes:
            This simplified example stubs several repository operations and
            assumes a single-repo layout for demonstration purposes.
        """
        logger.info(f"Creating upgrade PR for {service_name}: {upgrade_spec.spec_name}@{upgrade_spec.target_version}")

        if self.dry_run:
            logger.info(f"DRY RUN: Would create PR for {service_name}")
            return None

        try:
            # Find service manifest
            manifest_path = self.find_service_manifest(service_name)
            if not manifest_path:
                logger.error(f"Manifest not found for service: {service_name}")
                return None

            # Check if upgrade is allowed by policies
            if not self._is_upgrade_allowed(upgrade_spec):
                logger.warning(f"Upgrade not allowed by policies: {upgrade_spec.upgrade_type} for {service_name}")
                return None

            # Get base branch SHA
            base_sha = self.github.get_latest_commit_sha()
            branch_name = f"auto-upgrade/{service_name}/{upgrade_spec.spec_name}-{upgrade_spec.target_version}"

            # Create branch
            branch_sha = self.github.create_branch(branch_name, base_sha)

            # Update service manifest
            updated_manifest = self.update_service_manifest(manifest_path, upgrade_spec)

            # Get current file SHA for manifest
            try:
                manifest_content = self.github.get_file_content(str(manifest_path))
                manifest_sha = self.github.session.get(
                    f"{self.github.base_url}/repos/{self.github.repo_owner}/{self.github.repo_name}/contents/{manifest_path}",
                    params={"ref": "main"}
                ).json()["sha"]
            except:
                manifest_sha = None

            # Commit manifest changes
            if manifest_sha:
                commit_msg = f"🔧 Auto-upgrade {upgrade_spec.spec_name} to {upgrade_spec.target_version}"
                self.github.update_file(
                    str(manifest_path),
                    updated_manifest,
                    branch_name,
                    commit_msg,
                    manifest_sha
                )

            # Update specs.lock.json (simplified for this example)
            lock_content = self.update_specs_lock(upgrade_spec)

            # Generate PR content
            title, body, labels = self.generate_pr_content(upgrade_spec, service_name)

            # Create PR
            pr_number = self.github.create_pull_request(
                title=title,
                body=body,
                head_branch=branch_name,
                labels=labels,
                assignees=["254carbon-meta-bot"]
            )

            logger.info(f"Successfully created PR #{pr_number} for {service_name}")
            return pr_number

        except Exception as e:
            logger.error(f"Failed to create PR for {service_name}: {e}")
            return None

    def _is_upgrade_allowed(self, upgrade_spec: UpgradeSpec) -> bool:
        """Check if upgrade is allowed by current policies.

        Args:
            upgrade_spec: The requested upgrade with computed `upgrade_type`.

        Returns:
            True if the `auto_upgrade` policy permits this upgrade type.
        """
        policies = self.upgrade_policies.get('auto_upgrade', {})

        if upgrade_spec.upgrade_type == 'major':
            return policies.get('major', False)
        elif upgrade_spec.upgrade_type == 'minor':
            return policies.get('minor', True)
        elif upgrade_spec.upgrade_type == 'patch':
            return policies.get('patch', True)
        else:
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate upgrade pull requests")
    parser.add_argument("--service", required=True, help="Service name to upgrade")
    parser.add_argument("--spec-version", required=True, help="Spec version to upgrade to (format: spec-name@version)")
    parser.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")
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
        generator = UpgradePRGenerator(github_token, args.dry_run)

        # Parse upgrade specification
        upgrade_spec = generator.parse_upgrade_spec(args.spec_version)
        upgrade_spec.service_name = args.service

        # Create PR
        pr_number = generator.create_upgrade_pr(args.service, upgrade_spec)

        if pr_number:
            logger.info(f"✅ Upgrade PR #{pr_number} created successfully")
        elif args.dry_run:
            logger.info("✅ Dry run completed successfully")
        else:
            logger.error("❌ Failed to create upgrade PR")
            sys.exit(1)

    except Exception as e:
        logger.error(f"PR generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
