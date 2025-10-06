#!/usr/bin/env python3
"""
254Carbon Meta Repository - Quality Metrics Computation Script

Computes composite per-service quality scores using configurable weights and
thresholds, and summarizes platform-wide quality signals.

Usage:
    python scripts/compute_quality.py [--catalog-file FILE] [--thresholds-file FILE]

Scope and design:
- Extracts quality/security hints from catalog entries and applies weights from
  `config/thresholds.yaml` (with sensible defaults if missing).
- Penalizes drift, staleness, and policy failures; rewards signed images and
  fresh deployments (heuristics by maturity).
- Produces a snapshot JSON with per-service metrics, grades, distribution, and
  concise insights for dashboards and CLI summaries.

Outputs:
- Writes `catalog/quality-snapshot.json` and updates `catalog/latest_quality_snapshot.json`.
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/quality-computation.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Represents computed quality metrics for a service."""
    service_name: str
    coverage: float
    lint_pass: bool
    critical_vulns: int
    high_vulns: int
    policy_failures: int
    policy_warnings: int
    build_success_rate: float
    signed_images: bool
    sbom_present: bool
    deployment_freshness_days: int
    drift_issues: int
    maturity: str

    def compute_score(self, thresholds: Dict[str, Any]) -> int:
        """Compute composite quality score (0-100)."""
        # Base score
        score = thresholds.get('base_score', 50)

        # Coverage component
        coverage_weight = thresholds.get('weights', {}).get('coverage', 0.25)
        coverage_target = thresholds.get('coverage', {}).get('target', 0.75)
        if self.coverage > 0:
            coverage_score = min(100, (self.coverage / coverage_target) * 100 * coverage_weight * 4)
            score += coverage_score

        # Security component
        security_weight = thresholds.get('weights', {}).get('security', 0.35)
        vuln_penalty = (self.critical_vulns * 20) + (self.high_vulns * 10)
        security_score = max(0, 100 - vuln_penalty)
        score += (security_score * security_weight)

        # Policy component
        policy_weight = thresholds.get('weights', {}).get('policy', 0.15)
        policy_bonus = thresholds.get('policy', {}).get('full_compliance_bonus', 15)
        if self.policy_failures == 0:
            score += policy_bonus * policy_weight
        else:
            policy_penalty = self.policy_failures * 5
            score -= policy_penalty * policy_weight

        # Stability component
        stability_weight = thresholds.get('weights', {}).get('stability', 0.10)
        freshness_bonus = thresholds.get('stability', {}).get('deployment_frequency_bonus', 5)
        staleness_penalty = thresholds.get('stability', {}).get('staleness_penalty', 10)

        if self.deployment_freshness_days <= 7:
            score += freshness_bonus * stability_weight
        elif self.deployment_freshness_days > 30:
            score -= staleness_penalty * stability_weight

        # Drift penalty
        drift_weight = thresholds.get('weights', {}).get('drift', 0.15)
        drift_penalty_per_issue = thresholds.get('drift', {}).get('penalty_per_issue', 5)
        drift_penalty = min(self.drift_issues * drift_penalty_per_issue, 20)  # Cap at 20 points
        score -= drift_penalty * drift_weight

        # Apply maturity multiplier
        maturity_multipliers = thresholds.get('maturity_multipliers', {})
        maturity_mult = maturity_multipliers.get(self.maturity, {}).get('coverage_weight', 1.0)
        score = score * maturity_mult

        return max(0, min(100, int(score)))

    def get_grade(self, score: int) -> str:
        """Convert score to letter grade."""
        grade_thresholds = {
            'A': 90,
            'B': 80,
            'C': 70,
            'D': 60,
            'F': 0
        }

        for grade, threshold in grade_thresholds.items():
            if score >= threshold:
                return grade

        return 'F'

    def get_status(self, score: int, thresholds: Dict[str, Any]) -> str:
        """Determine quality status."""
        min_score = thresholds.get('quality', {}).get('min_score', 70)
        fail_under = thresholds.get('quality', {}).get('fail_under', 60)

        if score < fail_under:
            return 'failing'
        elif score < min_score:
            return 'warning'
        else:
            return 'passing'


class QualityComputer:
    """Computes quality metrics and scores for all services."""

    def __init__(self, catalog_file: str = None, thresholds_file: str = None):
        self.catalog_path = self._find_catalog_file(catalog_file)
        self.thresholds_file = thresholds_file or "config/thresholds.yaml"

        # Load catalog and thresholds
        self.catalog = self._load_catalog()
        self.thresholds = self._load_thresholds()

        # Reports directory
        self.reports_dir = Path("catalog")

    def _find_catalog_file(self, catalog_file: str = None) -> Path:
        """Find catalog file."""
        if catalog_file:
            return Path(catalog_file)

        # Default locations
        yaml_path = Path("catalog/service-index.yaml")
        json_path = Path("catalog/service-index.json")

        if yaml_path.exists():
            return yaml_path
        elif json_path.exists():
            return json_path
        else:
            raise FileNotFoundError("No catalog file found. Run 'make build-catalog' first.")

    def _load_catalog(self) -> Dict[str, Any]:
        """Load catalog from file."""
        logger.info(f"Loading catalog from {self.catalog_path}")

        with open(self.catalog_path) as f:
            if self.catalog_path.suffix == '.yaml':
                return yaml.safe_load(f)
            else:
                return json.load(f)

    def _load_thresholds(self) -> Dict[str, Any]:
        """Load quality thresholds."""
        thresholds_path = Path(self.thresholds_file)

        if not thresholds_path.exists():
            logger.warning(f"Thresholds file not found: {thresholds_path}, using defaults")
            return self._get_default_thresholds()

        with open(thresholds_path) as f:
            return yaml.safe_load(f)

    def _get_default_thresholds(self) -> Dict[str, Any]:
        """Get default quality thresholds."""
        return {
            'base_score': 50,
            'weights': {
                'coverage': 0.25,
                'security': 0.35,
                'policy': 0.15,
                'stability': 0.10,
                'drift': 0.15
            },
            'quality': {
                'min_score': 70,
                'fail_under': 60
            },
            'maturity_multipliers': {
                'experimental': {'coverage_weight': 0.8},
                'beta': {'coverage_weight': 0.9},
                'stable': {'coverage_weight': 1.0},
                'deprecated': {'coverage_weight': 0.6}
            }
        }

    def _extract_service_metrics(self, service: Dict[str, Any]) -> QualityMetrics:
        """Extract quality metrics from service data."""
        # Get quality data from service
        quality_data = service.get('quality', {})

        # Get drift data (simplified - in real implementation would read from drift report)
        drift_issues = 0  # Placeholder

        # Calculate deployment freshness (days since last update)
        last_update = service.get('last_update')
        deployment_freshness_days = 30  # Default

        if last_update:
            try:
                update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                deployment_freshness_days = (now - update_time).days
            except (ValueError, AttributeError):
                pass

        return QualityMetrics(
            service_name=service['name'],
            coverage=quality_data.get('coverage', 0.0),
            lint_pass=quality_data.get('lint_pass', False),
            critical_vulns=quality_data.get('open_critical_vulns', 0),
            high_vulns=0,  # Would be populated from security scan data
            policy_failures=0,  # Would be populated from policy check results
            policy_warnings=0,  # Would be populated from policy check results
            build_success_rate=0.95,  # Would be populated from CI/CD data
            signed_images=service.get('security', {}).get('signed_images', False),
            sbom_present=False,  # Would be populated from SBOM data
            deployment_freshness_days=deployment_freshness_days,
            drift_issues=drift_issues,
            maturity=service.get('maturity', 'unknown')
        )

    def _load_drift_data(self) -> Dict[str, int]:
        """Load drift issue counts from drift report."""
        drift_file = self.reports_dir / "latest_drift_report.json"

        if not drift_file.exists():
            logger.warning(f"Drift report not found: {drift_file}")
            return {}

        try:
            with open(drift_file) as f:
                drift_report = json.load(f)

            # Count issues by service
            drift_counts = {}
            for issue in drift_report.get('issues', []):
                service = issue.get('service', 'unknown')
                drift_counts[service] = drift_counts.get(service, 0) + 1

            return drift_counts

        except Exception as e:
            logger.warning(f"Failed to load drift data: {e}")
            return {}

    def _compute_single_service_score(self, service_data: Dict[str, Any], drift_counts: Dict[str, int], thresholds: Dict[str, Any]) -> Dict[str, Any]:
        """Compute quality score for a single service (for parallel processing)."""
        service = service_data
        service_name = service['name']

        # Extract metrics
        metrics = self._extract_service_metrics(service)

        # Apply drift penalty
        metrics.drift_issues = drift_counts.get(service_name, 0)

        # Compute score
        score = metrics.compute_score(thresholds)
        grade = metrics.get_grade(score)
        status = metrics.get_status(score, thresholds)

        # Return service data
        return {
            'service_name': service_name,
            'score': score,
            'grade': grade,
            'status': status,
            'metrics': {
                'coverage': metrics.coverage,
                'lint_pass': metrics.lint_pass,
                'critical_vulns': metrics.critical_vulns,
                'high_vulns': metrics.high_vulns,
                'policy_failures': metrics.policy_failures,
                'policy_warnings': metrics.policy_warnings,
                'build_success_rate': metrics.build_success_rate,
                'signed_images': metrics.signed_images,
                'sbom_present': metrics.sbom_present,
                'deployment_freshness_days': metrics.deployment_freshness_days,
                'drift_issues': metrics.drift_issues
            },
            'maturity': metrics.maturity,
                'computed_at': datetime.now(timezone.utc).isoformat()
            }

        return result

    def compute_all_quality_scores_parallel(self) -> Dict[str, Any]:
        """Compute quality scores for all services using parallel processing."""
        logger.info("Computing quality scores for all services using parallel processing...")

        services_data = self.catalog.get('services', [])
        if not services_data:
            logger.warning("No services found in catalog")
            return {}

        # Load drift data for penalty calculation
        drift_counts = self._load_drift_data()

        logger.info(f"Processing {len(services_data)} services in parallel...")

        # Use ProcessPoolExecutor for parallel computation
        max_workers = min(len(services_data), 5)  # Limit to 5 processes

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all computation tasks
            future_to_service = {
                executor.submit(
                    self._compute_single_service_score,
                    service_data,
                    drift_counts,
                    self.thresholds
                ): service_data
                for service_data in services_data
            }

            # Process results as they complete
            service_scores = {}
            all_scores = []

            for future in as_completed(future_to_service):
                service_data = future_to_service[future]
                try:
                    result = future.result()
                    service_name = result['service_name']

                    # Reconstruct service data format
                    service_scores[service_name] = {
                        'score': result['score'],
                        'grade': result['grade'],
                        'status': result['status'],
                        'metrics': result['metrics'],
                        'maturity': result['maturity'],
                        'computed_at': result['computed_at']
                    }

                    all_scores.append(result['score'])

                except Exception as e:
                    service_name = service_data.get('name', 'unknown')
                    logger.error(f"Failed to compute quality for {service_name}: {e}")
                    # Continue with other services

        logger.info(f"Parallel computation complete: {len(service_scores)} services processed")

        # Calculate global statistics
        if all_scores:
            avg_score = sum(all_scores) / len(all_scores)
            median_score = sorted(all_scores)[len(all_scores) // 2]
            min_score = min(all_scores)
            max_score = max(all_scores)
        else:
            avg_score = median_score = min_score = max_score = 0

        # Identify services below threshold
        min_threshold = self.thresholds.get('quality', {}).get('min_score', 70)
        services_below_threshold = [
            name for name, data in service_scores.items()
            if data['score'] < min_threshold
        ]

        # Calculate grade distribution
        grade_distribution = {}
        for data in service_scores.values():
            grade = data['grade']
            grade_distribution[grade] = grade_distribution.get(grade, 0) + 1

        # Generate insights
        insights = self._generate_insights(service_scores, all_scores)

        # Build complete report
        quality_snapshot = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'catalog_timestamp': self.catalog.get('metadata', {}).get('generated_at'),
            'total_services': len(services),
            'services': service_scores,
            'global': {
                'avg_score': round(avg_score, 1),
                'median_score': median_score,
                'min_score': min_score,
                'max_score': max_score,
                'services_below_threshold': services_below_threshold,
                'grade_distribution': grade_distribution,
                'quality_distribution': {
                    'excellent': len([s for s in service_scores.values() if s['score'] >= 90]),
                    'good': len([s for s in service_scores.values() if 80 <= s['score'] < 90]),
                    'acceptable': len([s for s in service_scores.values() if 70 <= s['score'] < 80]),
                    'needs_improvement': len([s for s in service_scores.values() if 60 <= s['score'] < 70]),
                    'failing': len([s for s in service_scores.values() if s['score'] < 60])
                }
            },
            'insights': insights,
            'thresholds_applied': {
                'min_score': min_threshold,
                'fail_under': self.thresholds.get('quality', {}).get('fail_under', 60)
            }
        }

        logger.info(f"Quality computation complete: {len(service_scores)} services scored, avg: {avg_score:.1f}")
        return quality_snapshot

    def _generate_insights(self, service_scores: Dict[str, Any], all_scores: List[int]) -> List[str]:
        """Generate actionable insights from quality data."""
        insights = []

        # Overall platform health
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0

        if avg_score >= 85:
            insights.append("🏆 Platform quality is excellent with strong engineering practices")
        elif avg_score >= 75:
            insights.append("✅ Platform quality is good with solid foundation")
        elif avg_score >= 65:
            insights.append("⚠️ Platform quality needs improvement in several areas")
        else:
            insights.append("🚨 Platform quality requires immediate attention")

        # Failing services
        failing_services = [name for name, data in service_scores.items() if data['status'] == 'failing']
        if failing_services:
            insights.append(f"🔴 {len(failing_services)} services are failing quality standards: {', '.join(failing_services[:3])}")

        # Coverage issues
        low_coverage = [name for name, data in service_scores.items() if data['metrics']['coverage'] < 0.7]
        if low_coverage:
            insights.append(f"📊 {len(low_coverage)} services have low test coverage (< 70%)")

        # Security issues
        vuln_services = [name for name, data in service_scores.items() if data['metrics']['critical_vulns'] > 0]
        if vuln_services:
            insights.append(f"🔒 {len(vuln_services)} services have critical vulnerabilities")

        # Staleness
        stale_services = [name for name, data in service_scores.items() if data['metrics']['deployment_freshness_days'] > 90]
        if stale_services:
            insights.append(f"⏰ {len(stale_services)} services are stale (> 90 days since update)")

        # Drift issues
        drift_services = [name for name, data in service_scores.items() if data['metrics']['drift_issues'] > 0]
        if drift_services:
            insights.append(f"🔄 {len(drift_services)} services have drift issues requiring attention")

        return insights

    def save_quality_snapshot(self, quality_snapshot: Dict[str, Any]) -> None:
        """Save quality snapshot to file."""
        snapshot_file = self.reports_dir / "quality-snapshot.json"

        with open(snapshot_file, 'w') as f:
            json.dump(quality_snapshot, f, indent=2)

        logger.info(f"Saved quality snapshot to {snapshot_file}")

        # Also save latest for easy access
        latest_file = self.reports_dir / "latest_quality_snapshot.json"
        with open(latest_file, 'w') as f:
            json.dump(quality_snapshot, f, indent=2)

        logger.info(f"Updated latest quality snapshot: {latest_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Compute quality scores for all services")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file (default: auto-detect)")
    parser.add_argument("--thresholds-file", type=str, help="Path to thresholds file (default: config/thresholds.yaml)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        computer = QualityComputer(args.catalog_file, args.thresholds_file)
        quality_snapshot = computer.compute_all_quality_scores()
        computer.save_quality_snapshot(quality_snapshot)

        logger.info("Quality computation completed successfully")

        # Print summary
        global_stats = quality_snapshot.get('global', {})
        print("\n📊 Quality Summary:")
        print(f"  Average Score: {global_stats.get('avg_score', 0):.1f}/100")
        print(f"  Services Below Threshold: {len(global_stats.get('services_below_threshold', []))}")
        print(f"  Grade Distribution: {global_stats.get('grade_distribution', {})}")

        if quality_snapshot.get('insights'):
            print("\n🎯 Key Insights:")
            for insight in quality_snapshot['insights'][:3]:
                print(f"  {insight}")

    except Exception as e:
        logger.error(f"Quality computation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
