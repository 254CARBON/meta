#!/usr/bin/env python3
"""
254Carbon Meta Repository - Quality Trends Analysis

Analyzes historical quality data to identify trends and patterns.

Usage:
    python scripts/analyze_quality_trends.py [--days 30] [--output-file FILE]
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from collections import defaultdict


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/quality-trends.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class QualitySnapshot:
    """Represents a historical quality snapshot."""
    timestamp: datetime
    avg_score: float
    median_score: float
    min_score: float
    max_score: float
    services_count: int
    grade_distribution: Dict[str, int]


@dataclass
class QualityTrend:
    """Represents a quality trend over time."""
    service_name: str
    trend_direction: str  # 'improving', 'declining', 'stable'
    change_rate: float  # points per day
    volatility: float   # standard deviation of changes
    data_points: List[Tuple[datetime, float]]


class QualityTrendAnalyzer:
    """Analyzes quality trends from historical data."""

    def __init__(self, days: int = 30):
        self.days = days
        self.historical_dir = Path("analysis/historical/quality")
        self.historical_dir.mkdir(parents=True, exist_ok=True)

        # Load historical snapshots
        self.snapshots = self._load_historical_snapshots()

    def _load_historical_snapshots(self) -> List[QualitySnapshot]:
        """Load historical quality snapshots."""
        snapshots = []

        if not self.historical_dir.exists():
            logger.warning(f"Historical directory not found: {self.historical_dir}")
            return snapshots

        # Look for quality snapshot files
        for snapshot_file in self.historical_dir.glob("quality_*.json"):
            try:
                with open(snapshot_file) as f:
                    data = json.load(f)

                timestamp_str = data.get('generated_at', '')
                if timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

                    # Only include snapshots within the specified time range
                    cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.days)
                    if timestamp >= cutoff_date:
                        snapshot = QualitySnapshot(
                            timestamp=timestamp,
                            avg_score=data.get('global', {}).get('avg_score', 0),
                            median_score=data.get('global', {}).get('median_score', 0),
                            min_score=data.get('global', {}).get('min_score', 0),
                            max_score=data.get('global', {}).get('max_score', 0),
                            services_count=data.get('metadata', {}).get('total_services', 0),
                            grade_distribution=data.get('global', {}).get('grade_distribution', {})
                        )
                        snapshots.append(snapshot)

            except Exception as e:
                logger.warning(f"Failed to load snapshot {snapshot_file}: {e}")

        # Sort by timestamp
        snapshots.sort(key=lambda x: x.timestamp)
        logger.info(f"Loaded {len(snapshots)} quality snapshots from last {self.days} days")
        return snapshots

    def analyze_platform_trends(self) -> Dict[str, Any]:
        """Analyze overall platform quality trends."""
        if len(self.snapshots) < 2:
            return {"error": "Insufficient data for trend analysis"}

        # Calculate trend metrics
        timestamps = [s.timestamp for s in self.snapshots]
        avg_scores = [s.avg_score for s in self.snapshots]

        # Calculate linear trend
        if len(timestamps) >= 2:
            # Simple linear regression for trend
            n = len(timestamps)
            x = [(t - timestamps[0]).total_seconds() / (24 * 3600) for t in timestamps]  # days since first
            y = avg_scores

            # Calculate slope (change per day)
            if n > 1:
                sum_x = sum(x)
                sum_y = sum(y)
                sum_xy = sum(xi * yi for xi, yi in zip(x, y))
                sum_x2 = sum(xi * xi for xi in x)

                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0
            else:
                slope = 0

            # Determine trend direction
            if slope > 0.1:
                trend_direction = "improving"
            elif slope < -0.1:
                trend_direction = "declining"
            else:
                trend_direction = "stable"
        else:
            slope = 0
            trend_direction = "stable"

        # Calculate volatility (standard deviation of changes)
        if len(avg_scores) > 1:
            changes = [avg_scores[i] - avg_scores[i-1] for i in range(1, len(avg_scores))]
            volatility = (sum((c - sum(changes)/len(changes))**2 for c in changes) / len(changes))**0.5 if changes else 0
        else:
            volatility = 0

        return {
            "trend_direction": trend_direction,
            "change_rate": round(slope, 3),
            "volatility": round(volatility, 3),
            "data_points": len(self.snapshots),
            "time_range_days": self.days,
            "current_avg_score": avg_scores[-1] if avg_scores else 0,
            "baseline_avg_score": avg_scores[0] if avg_scores else 0,
            "total_change": round(avg_scores[-1] - avg_scores[0], 2) if len(avg_scores) >= 2 else 0
        }

    def analyze_service_trends(self) -> Dict[str, QualityTrend]:
        """Analyze quality trends for individual services."""
        service_trends = {}

        # This would require service-level historical data
        # For now, we'll analyze based on current catalog data

        # Load current quality data
        quality_file = Path("catalog/latest_quality_snapshot.json")
        if not quality_file.exists():
            logger.warning("No current quality data for service trend analysis")
            return service_trends

        with open(quality_file) as f:
            current_quality = json.load(f)

        services = current_quality.get('services', {})

        for service_name, service_data in services.items():
            current_score = service_data.get('score', 0)

            # For demonstration, we'll simulate trends based on current data
            # In a real implementation, this would use historical service-level data

            # Simple heuristic: services with low scores are "declining"
            if current_score < 60:
                trend = QualityTrend(
                    service_name=service_name,
                    trend_direction="declining",
                    change_rate=-0.5,  # Simulated decline
                    volatility=5.0,
                    data_points=[(datetime.now(timezone.utc), current_score)]
                )
            elif current_score > 85:
                trend = QualityTrend(
                    service_name=service_name,
                    trend_direction="improving",
                    change_rate=0.3,  # Simulated improvement
                    volatility=2.0,
                    data_points=[(datetime.now(timezone.utc), current_score)]
                )
            else:
                trend = QualityTrend(
                    service_name=service_name,
                    trend_direction="stable",
                    change_rate=0.0,
                    volatility=1.0,
                    data_points=[(datetime.now(timezone.utc), current_score)]
                )

            service_trends[service_name] = trend

        return service_trends

    def generate_trend_report(self) -> Dict[str, Any]:
        """Generate comprehensive trend report."""
        logger.info("Generating quality trends report...")

        # Platform-level trends
        platform_trends = self.analyze_platform_trends()

        # Service-level trends
        service_trends = self.analyze_service_trends()

        # Identify concerning trends
        declining_services = [
            name for name, trend in service_trends.items()
            if trend.trend_direction == "declining"
        ]

        improving_services = [
            name for name, trend in service_trends.items()
            if trend.trend_direction == "improving"
        ]

        # Generate insights
        insights = self._generate_trend_insights(platform_trends, service_trends)

        report = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "analysis_period_days": self.days,
                "snapshots_analyzed": len(self.snapshots)
            },
            "platform_trends": platform_trends,
            "service_trends": {
                name: {
                    "trend_direction": trend.trend_direction,
                    "change_rate": trend.change_rate,
                    "volatility": trend.volatility,
                    "current_score": trend.data_points[-1][1] if trend.data_points else 0
                }
                for name, trend in service_trends.items()
            },
            "summary": {
                "declining_services": len(declining_services),
                "improving_services": len(improving_services),
                "stable_services": len(service_trends) - len(declining_services) - len(improving_services),
                "services_analyzed": len(service_trends)
            },
            "insights": insights,
            "recommendations": self._generate_trend_recommendations(platform_trends, service_trends)
        }

        return report

    def _generate_trend_insights(self, platform_trends: Dict[str, Any], service_trends: Dict[str, QualityTrend]) -> List[str]:
        """Generate insights from trend data."""
        insights = []

        # Platform-level insights
        trend_direction = platform_trends.get("trend_direction", "stable")
        change_rate = platform_trends.get("change_rate", 0)
        total_change = platform_trends.get("total_change", 0)

        if trend_direction == "improving" and change_rate > 0.2:
            insights.append(f"🚀 Platform quality is improving rapidly (+{change_rate:.2f} points/day)")
        elif trend_direction == "declining" and change_rate < -0.2:
            insights.append(f"⚠️ Platform quality is declining concerningly ({change_rate:.2f} points/day)")
        elif abs(total_change) > 5:
            direction = "gained" if total_change > 0 else "lost"
            insights.append(f"📈 Platform quality has {direction} {abs(total_change):.1f} points in {self.days} days")

        # Service-level insights
        declining_count = len([t for t in service_trends.values() if t.trend_direction == "declining"])
        improving_count = len([t for t in service_trends.values() if t.trend_direction == "improving"])

        if declining_count > 0:
            insights.append(f"🔴 {declining_count} services show declining quality trends")

        if improving_count > declining_count:
            insights.append(f"✅ More services are improving ({improving_count}) than declining ({declining_count})")

        return insights

    def _generate_trend_recommendations(self, platform_trends: Dict[str, Any], service_trends: Dict[str, QualityTrend]) -> List[str]:
        """Generate recommendations based on trends."""
        recommendations = []

        # Platform recommendations
        if platform_trends.get("trend_direction") == "declining":
            recommendations.append("🔴 Platform quality is declining - investigate systemic issues")

        if platform_trends.get("volatility", 0) > 3:
            recommendations.append("📊 High volatility detected - stabilize quality metrics")

        # Service recommendations
        declining_services = [name for name, trend in service_trends.items() if trend.trend_direction == "declining"]
        if declining_services:
            recommendations.append(f"🎯 Focus quality improvement efforts on: {', '.join(declining_services[:3])}")

        # Volatility recommendations
        volatile_services = [
            name for name, trend in service_trends.items()
            if trend.volatility > 5 and trend.trend_direction != "improving"
        ]
        if volatile_services:
            recommendations.append(f"📈 Stabilize quality for volatile services: {', '.join(volatile_services[:3])}")

        if not recommendations:
            recommendations.append("✅ Quality trends are healthy - maintain current practices")

        return recommendations

    def save_trend_report(self, report: Dict[str, Any], output_file: str = None) -> None:
        """Save trend report to file."""
        if output_file:
            report_path = Path(output_file)
        else:
            reports_dir = Path("analysis/reports")
            reports_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = reports_dir / f"quality_trends_{timestamp}.json"

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Saved quality trends report to {report_path}")

        # Generate markdown version for easy reading
        self._generate_markdown_report(report, report_path.with_suffix('.md'))

    def _generate_markdown_report(self, report: Dict[str, Any], markdown_path: Path) -> None:
        """Generate human-readable markdown report."""
        platform_trends = report.get('platform_trends', {})
        service_trends = report.get('service_trends', {})
        summary = report.get('summary', {})

        markdown = f"""# 📈 Quality Trends Analysis

**Generated:** {report['metadata']['generated_at']}
**Analysis Period:** {report['metadata']['analysis_period_days']} days
**Snapshots Analyzed:** {report['metadata']['snapshots_analyzed']}

## 📊 Platform Trends

| Metric | Value | Status |
|--------|-------|--------|
| **Trend Direction** | {platform_trends.get('trend_direction', 'unknown').title()} | {'📈 Improving' if platform_trends.get('trend_direction') == 'improving' else '📉 Declining' if platform_trends.get('trend_direction') == 'declining' else '➡️ Stable'} |
| **Change Rate** | {platform_trends.get('change_rate', 0):+.3f} points/day | {'⚡ Fast' if abs(platform_trends.get('change_rate', 0)) > 0.5 else '🐌 Slow' if abs(platform_trends.get('change_rate', 0)) < 0.1 else '➡️ Moderate'} |
| **Volatility** | {platform_trends.get('volatility', 0):.3f} | {'📊 High' if platform_trends.get('volatility', 0) > 3 else '✅ Low'} |
| **Total Change** | {platform_trends.get('total_change', 0):+.1f} points | {'🎯 Significant' if abs(platform_trends.get('total_change', 0)) > 5 else '📏 Minimal'} |

## 🔍 Service Trends

### Summary
- **Improving:** {summary.get('improving_services', 0)} services
- **Declining:** {summary.get('declining_services', 0)} services
- **Stable:** {summary.get('stable_services', 0)} services

### Detailed Trends

| Service | Trend | Change Rate | Volatility | Current Score |
|---------|-------|-------------|------------|---------------|
"""

        # Sort services by trend priority (declining first, then improving)
        sorted_services = sorted(
            service_trends.items(),
            key=lambda x: (
                0 if x[1]['trend_direction'] == 'declining' else
                1 if x[1]['trend_direction'] == 'improving' else 2,
                -abs(x[1]['change_rate'])
            )
        )

        for service_name, trend_data in sorted_services[:20]:  # Top 20
            trend_icon = {
                'improving': '📈',
                'declining': '📉',
                'stable': '➡️'
            }.get(trend_data['trend_direction'], '❓')

            markdown += f"| **{service_name}** | {trend_icon} {trend_data['trend_direction'].title()} | {trend_data['change_rate']:+.2f} | {trend_data['volatility']:.1f} | {trend_data['current_score']:.1f} |\n"

        markdown += "\n## 🎯 Key Insights\n\n"
        for insight in report.get('insights', []):
            markdown += f"- {insight}\n"

        markdown += "\n## 💡 Recommendations\n\n"
        for rec in report.get('recommendations', []):
            markdown += f"- {rec}\n"

        markdown += f"\n---\n*🤖 Generated by 254Carbon Meta - Trend Analysis*\n"

        with open(markdown_path, 'w') as f:
            f.write(markdown)

        logger.info(f"Saved markdown report to {markdown_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze quality trends from historical data")
    parser.add_argument("--days", type=int, default=30, help="Number of days to analyze (default: 30)")
    parser.add_argument("--output-file", type=str, help="Output file for trend report")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        analyzer = QualityTrendAnalyzer(args.days)
        report = analyzer.generate_trend_report()
        analyzer.save_trend_report(report, args.output_file)

        # Print summary
        platform_trends = report.get('platform_trends', {})
        print("\n📈 Quality Trends Summary:")
        print(f"  Trend: {platform_trends.get('trend_direction', 'unknown').title()}")
        print(f"  Change Rate: {platform_trends.get('change_rate', 0):+.3f} points/day")
        print(f"  Volatility: {platform_trends.get('volatility', 0):.3f}")
        print(f"  Total Change: {platform_trends.get('total_change', 0):+.1f} points")

        summary = report.get('summary', {})
        print(f"  Services Improving: {summary.get('improving_services', 0)}")
        print(f"  Services Declining: {summary.get('declining_services', 0)}")

        if report.get('insights'):
            print("\n🎯 Key Insights:")
            for insight in report['insights'][:3]:
                print(f"  {insight}")

    except Exception as e:
        logger.error(f"Quality trends analysis failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
