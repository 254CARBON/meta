#!/usr/bin/env python3
"""
254Carbon Meta Repository - Manifest Diff Utility

Compares service manifests across commits and catalog snapshots.

Usage:
    python scripts/diff_manifests.py --service gateway --from-commit abc123 --to-commit def456
    python scripts/diff_manifests.py --catalog-snapshots --days 7
"""

import os
import sys
import json
import yaml
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/manifest-diffs.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ManifestChange:
    """Represents a change in a manifest field."""
    service_name: str
    field_path: str
    old_value: Any
    new_value: Any
    change_type: str  # 'added', 'removed', 'modified', 'moved'
    severity: str  # 'low', 'medium', 'high'


@dataclass
class ManifestDiff:
    """Complete diff between two manifest versions."""
    service_name: str
    from_commit: str
    to_commit: str
    changes: List[ManifestChange]
    summary: Dict[str, int]  # Count by change type
    compatibility_impact: str  # 'none', 'minor', 'major', 'breaking'


class ManifestDiffer:
    """Compares service manifests across versions."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
        self.manifests_dir = self.repo_path / "manifests" / "collected"

    def get_manifest_at_commit(self, service_name: str, commit_sha: str) -> Optional[Dict[str, Any]]:
        """Get manifest content at a specific commit."""
        try:
            # Use git show to get file at commit
            cmd = [
                "git", "show",
                f"{commit_sha}:manifests/collected/{service_name}.yaml"
            ]

            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                logger.warning(f"Manifest not found for {service_name} at {commit_sha}")
                return None

            return yaml.safe_load(result.stdout)

        except Exception as e:
            logger.error(f"Failed to get manifest for {service_name} at {commit_sha}: {e}")
            return None

    def compare_manifests(self, service_name: str, from_commit: str, to_commit: str) -> ManifestDiff:
        """Compare two versions of a service manifest."""
        logger.info(f"Comparing {service_name} from {from_commit[:8]} to {to_commit[:8]}")

        # Get manifests at both commits
        from_manifest = self.get_manifest_at_commit(service_name, from_commit)
        to_manifest = self.get_manifest_at_commit(service_name, to_commit)

        if not from_manifest and not to_manifest:
            raise ValueError(f"No manifests found for {service_name} at either commit")

        if not from_manifest:
            # Service was added
            changes = self._analyze_manifest_addition(service_name, to_manifest)
            return ManifestDiff(
                service_name=service_name,
                from_commit=from_commit,
                to_commit=to_commit,
                changes=changes,
                summary=self._summarize_changes(changes),
                compatibility_impact="major"  # Adding a service is a major change
            )

        if not to_manifest:
            # Service was removed
            changes = self._analyze_manifest_removal(service_name, from_manifest)
            return ManifestDiff(
                service_name=service_name,
                from_commit=from_commit,
                to_commit=to_commit,
                changes=changes,
                summary=self._summarize_changes(changes),
                compatibility_impact="breaking"  # Removing a service is breaking
            )

        # Compare existing manifests
        changes = self._compare_manifest_fields(service_name, from_manifest, to_manifest)

        return ManifestDiff(
            service_name=service_name,
            from_commit=from_commit,
            to_commit=to_commit,
            changes=changes,
            summary=self._summarize_changes(changes),
            compatibility_impact=self._assess_compatibility_impact(changes)
        )

    def _compare_manifest_fields(self, service_name: str, from_manifest: Dict[str, Any],
                               to_manifest: Dict[str, Any]) -> List[ManifestChange]:
        """Compare fields between two manifest versions."""
        changes = []

        # Get all unique field paths from both manifests
        all_fields = set(from_manifest.keys()) | set(to_manifest.keys())

        for field_path in all_fields:
            from_value = from_manifest.get(field_path)
            to_value = to_manifest.get(field_path)

            if from_value != to_value:
                if field_path not in from_manifest:
                    # Field was added
                    change = ManifestChange(
                        service_name=service_name,
                        field_path=field_path,
                        old_value=None,
                        new_value=to_value,
                        change_type="added",
                        severity=self._assess_field_severity(field_path)
                    )
                elif field_path not in to_manifest:
                    # Field was removed
                    change = ManifestChange(
                        service_name=service_name,
                        field_path=field_path,
                        old_value=from_value,
                        new_value=None,
                        change_type="removed",
                        severity=self._assess_field_severity(field_path)
                    )
                else:
                    # Field was modified
                    change = ManifestChange(
                        service_name=service_name,
                        field_path=field_path,
                        old_value=from_value,
                        new_value=to_value,
                        change_type="modified",
                        severity=self._assess_field_severity(field_path)
                    )

                changes.append(change)

        return changes

    def _analyze_manifest_addition(self, service_name: str, to_manifest: Dict[str, Any]) -> List[ManifestChange]:
        """Analyze addition of a new service."""
        changes = []

        # All fields are new
        for field_path, value in to_manifest.items():
            changes.append(ManifestChange(
                service_name=service_name,
                field_path=field_path,
                old_value=None,
                new_value=value,
                change_type="added",
                severity=self._assess_field_severity(field_path)
            ))

        return changes

    def _analyze_manifest_removal(self, service_name: str, from_manifest: Dict[str, Any]) -> List[ManifestChange]:
        """Analyze removal of a service."""
        changes = []

        # All fields are removed
        for field_path, value in from_manifest.items():
            changes.append(ManifestChange(
                service_name=service_name,
                field_path=field_path,
                old_value=value,
                new_value=None,
                change_type="removed",
                severity=self._assess_field_severity(field_path)
            ))

        return changes

    def _assess_field_severity(self, field_path: str) -> str:
        """Assess severity of changes to a field."""
        # Critical fields that affect compatibility
        critical_fields = ['name', 'domain', 'version', 'api_contracts', 'dependencies']
        high_impact_fields = ['events_in', 'events_out', 'runtime', 'maturity']

        if field_path in critical_fields:
            return 'high'
        elif field_path in high_impact_fields:
            return 'medium'
        else:
            return 'low'

    def _summarize_changes(self, changes: List[ManifestChange]) -> Dict[str, int]:
        """Summarize changes by type."""
        summary = {'added': 0, 'removed': 0, 'modified': 0}

        for change in changes:
            summary[change.change_type] += 1

        return summary

    def _assess_compatibility_impact(self, changes: List[ManifestChange]) -> str:
        """Assess overall compatibility impact."""
        high_severity_changes = [c for c in changes if c.severity == 'high']

        if any(c.change_type == 'removed' for c in high_severity_changes):
            return 'breaking'
        elif any(c.change_type == 'modified' for c in high_severity_changes):
            return 'major'
        elif high_severity_changes:
            return 'minor'
        else:
            return 'none'

    def compare_catalog_snapshots(self, days: int = 7) -> Dict[str, ManifestDiff]:
        """Compare catalog snapshots over time."""
        logger.info(f"Comparing catalog snapshots from last {days} days")

        # Find historical snapshots
        historical_dir = self.repo_path / "analysis" / "historical" / "quality"
        if not historical_dir.exists():
            logger.warning(f"Historical directory not found: {historical_dir}")
            return {}

        # Get recent snapshot files
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        snapshot_files = []

        for snapshot_file in historical_dir.glob("quality_*.json"):
            try:
                # Parse timestamp from filename (quality_YYYYMMDD_HHMMSS.json)
                filename = snapshot_file.stem  # Remove .json extension
                timestamp_str = filename.replace("quality_", "")

                # Parse timestamp
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                if timestamp >= cutoff_date:
                    snapshot_files.append((timestamp, snapshot_file))
            except (ValueError, AttributeError):
                continue

        if len(snapshot_files) < 2:
            logger.warning("Not enough historical snapshots for comparison")
            return {}

        # Sort by timestamp and compare consecutive snapshots
        snapshot_files.sort(key=lambda x: x[0])

        diffs = {}
        for i in range(len(snapshot_files) - 1):
            from_timestamp, from_file = snapshot_files[i]
            to_timestamp, to_file = snapshot_files[i + 1]

            # Load snapshots
            with open(from_file) as f:
                from_data = json.load(f)
            with open(to_file) as f:
                to_data = json.load(f)

            # Compare each service
            from_services = from_data.get('services', {})
            to_services = to_data.get('services', {})

            all_services = set(from_services.keys()) | set(to_services.keys())

            for service_name in all_services:
                from_manifest = from_services.get(service_name, {})
                to_manifest = to_services.get(service_name, {})

                if from_manifest != to_manifest:
                    diff = ManifestDiff(
                        service_name=service_name,
                        from_commit=f"snapshot_{from_timestamp.strftime('%Y%m%d_%H%M%S')}",
                        to_commit=f"snapshot_{to_timestamp.strftime('%Y%m%d_%H%M%S')}",
                        changes=[],  # Would need to implement snapshot comparison
                        summary={'modified': 1, 'added': 0, 'removed': 0},
                        compatibility_impact='minor'
                    )
                    diffs[service_name] = diff

        logger.info(f"Found changes in {len(diffs)} services across {len(snapshot_files)} snapshots")
        return diffs

    def generate_change_report(self, diffs: Dict[str, ManifestDiff]) -> Dict[str, Any]:
        """Generate comprehensive change report."""
        # Group changes by type
        changes_by_type = {'added': [], 'removed': [], 'modified': []}
        changes_by_severity = {'low': [], 'medium': [], 'high': []}

        for diff in diffs.values():
            for change in diff.changes:
                changes_by_type[change.change_type].append(change)
                changes_by_severity[change.severity].append(change)

        # Generate insights
        insights = self._generate_change_insights(diffs)

        report = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'services_changed': len(diffs),
                'total_changes': sum(len(diff.changes) for diff in diffs.values())
            },
            'summary': {
                'changes_by_type': {
                    'added': len(changes_by_type['added']),
                    'removed': len(changes_by_type['removed']),
                    'modified': len(changes_by_type['modified'])
                },
                'changes_by_severity': {
                    'low': len(changes_by_severity['low']),
                    'medium': len(changes_by_severity['medium']),
                    'high': len(changes_by_severity['high'])
                }
            },
            'service_diffs': {
                name: {
                    'changes_count': len(diff.changes),
                    'compatibility_impact': diff.compatibility_impact,
                    'summary': diff.summary
                }
                for name, diff in diffs.items()
            },
            'insights': insights,
            'recommendations': self._generate_change_recommendations(diffs)
        }

        return report

    def _generate_change_insights(self, diffs: Dict[str, ManifestDiff]) -> List[str]:
        """Generate insights from manifest changes."""
        insights = []

        # Count breaking changes
        breaking_changes = [d for d in diffs.values() if d.compatibility_impact == 'breaking']
        if breaking_changes:
            insights.append(f"🚨 {len(breaking_changes)} services have breaking changes")

        # Count major changes
        major_changes = [d for d in diffs.values() if d.compatibility_impact == 'major']
        if major_changes:
            insights.append(f"⚠️ {len(major_changes)} services have major changes")

        # Analyze change patterns
        all_changes = []
        for diff in diffs.values():
            all_changes.extend(diff.changes)

        # Most changed fields
        field_changes = {}
        for change in all_changes:
            field = change.field_path
            field_changes[field] = field_changes.get(field, 0) + 1

        if field_changes:
            most_changed = max(field_changes.items(), key=lambda x: x[1])
            insights.append(f"📊 Most changed field: {most_changed[0]} ({most_changed[1]} changes)")

        return insights

    def _generate_change_recommendations(self, diffs: Dict[str, ManifestDiff]) -> List[str]:
        """Generate recommendations based on changes."""
        recommendations = []

        breaking_changes = [d for d in diffs.values() if d.compatibility_impact == 'breaking']
        if breaking_changes:
            recommendations.append("🚨 Review breaking changes before deployment")

        major_changes = [d for d in diffs.values() if d.compatibility_impact == 'major']
        if major_changes:
            recommendations.append("⚠️ Major changes require thorough testing")

        # Check for version bumps
        version_changes = [
            d for d in diffs.values()
            if any(c.field_path == 'version' for c in d.changes)
        ]
        if version_changes:
            recommendations.append(f"📦 {len(version_changes)} services have version changes")

        if not recommendations:
            recommendations.append("✅ No significant changes detected")

        return recommendations


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Compare service manifests across versions")
    parser.add_argument("--service", type=str, help="Specific service to compare")
    parser.add_argument("--from-commit", type=str, help="Starting commit SHA")
    parser.add_argument("--to-commit", type=str, help="Ending commit SHA")
    parser.add_argument("--catalog-snapshots", action="store_true", help="Compare catalog snapshots instead of commits")
    parser.add_argument("--days", type=int, default=7, help="Days to look back for snapshots (default: 7)")
    parser.add_argument("--output-file", type=str, help="Output file for diff report")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        differ = ManifestDiffer()

        if args.catalog_snapshots:
            # Compare catalog snapshots
            diffs = differ.compare_catalog_snapshots(args.days)
            report = differ.generate_change_report(diffs)
        elif args.service and args.from_commit and args.to_commit:
            # Compare specific service between commits
            diff = differ.compare_manifests(args.service, args.from_commit, args.to_commit)
            report = {
                'metadata': {
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'comparison_type': 'single_service'
                },
                'service_diffs': {args.service: diff}
            }
        else:
            parser.print_help()
            sys.exit(1)

        # Save or print report
        if args.output_file:
            with open(args.output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Diff report saved to {args.output_file}")
        else:
            # Print formatted report
            print("\n🔍 Manifest Diff Report:")
            print(f"  Generated: {report['metadata']['generated_at']}")

            if 'summary' in report:
                summary = report['summary']
                print(f"  Services Changed: {len(report['service_diffs'])}")
                print(f"  Total Changes: {summary['changes_by_type']['added']} added, {summary['changes_by_type']['removed']} removed, {summary['changes_by_type']['modified']} modified")

                print("\n📊 Changes by Severity:")
                print(f"  High Impact: {summary['changes_by_severity']['high']}")
                print(f"  Medium Impact: {summary['changes_by_severity']['medium']}")
                print(f"  Low Impact: {summary['changes_by_severity']['low']}")

            if 'insights' in report and report['insights']:
                print("\n🎯 Key Insights:")
                for insight in report['insights'][:3]:
                    print(f"  {insight}")

            if 'recommendations' in report and report['recommendations']:
                print("\n💡 Recommendations:")
                for rec in report['recommendations'][:3]:
                    print(f"  {rec}")

    except Exception as e:
        logger.error(f"Manifest diff operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
