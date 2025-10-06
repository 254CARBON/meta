#!/usr/bin/env python3
"""
254Carbon Meta Repository - Platform Dashboard Generator

Generates interactive HTML dashboards for platform monitoring.

Usage:
    python scripts/generate_dashboard.py --type overview [--output-dir public]
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
from jinja2 import Environment, FileSystemLoader, Template
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/dashboard-generation.log')
    ]
)
logger = logging.getLogger(__name__)


class DashboardGenerator:
    """Generates interactive HTML dashboards."""

    def __init__(self, output_dir: str = "public"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Setup Jinja2
        self.template_env = Environment(
            loader=FileSystemLoader("analysis/templates/dashboards/"),
            autoescape=True
        )

        # Load platform data
        self.catalog_data = self._load_catalog_data()
        self.quality_data = self._load_quality_data()
        self.drift_data = self._load_drift_data()

    def _load_catalog_data(self) -> Dict[str, Any]:
        """Load service catalog data."""
        catalog_file = Path("catalog/service-index.yaml")

        if not catalog_file.exists():
            logger.warning("Catalog not found, using empty data")
            return {"services": []}

        try:
            with open(catalog_file) as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load catalog: {e}")
            return {"services": []}

    def _load_quality_data(self) -> Dict[str, Any]:
        """Load quality metrics data."""
        quality_file = Path("catalog/latest_quality_snapshot.json")

        if not quality_file.exists():
            logger.warning("Quality data not found")
            return {}

        try:
            with open(quality_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load quality data: {e}")
            return {}

    def _load_drift_data(self) -> Dict[str, Any]:
        """Load drift analysis data."""
        drift_file = Path("catalog/latest_drift_report.json")

        if not drift_file.exists():
            logger.warning("Drift data not found")
            return {}

        try:
            with open(drift_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load drift data: {e}")
            return {}

    def generate_overview_dashboard(self) -> str:
        """Generate main platform overview dashboard."""
        logger.info("Generating platform overview dashboard...")

        # Prepare dashboard data
        dashboard_data = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'title': '254Carbon Platform Overview',
                'version': '1.0.0'
            },
            'platform_summary': self._get_platform_summary(),
            'quality_overview': self._get_quality_overview(),
            'drift_overview': self._get_drift_overview(),
            'architecture_overview': self._get_architecture_overview(),
            'charts': self._generate_charts()
        }

        # Generate HTML
        template = self.template_env.get_template("overview.html.j2")
        html_content = template.render(**dashboard_data)

        # Save dashboard
        dashboard_path = self.output_dir / "index.html"
        with open(dashboard_path, 'w') as f:
            f.write(html_content)

        logger.info(f"Overview dashboard saved to {dashboard_path}")
        return str(dashboard_path)

    def _get_platform_summary(self) -> Dict[str, Any]:
        """Get platform-level summary metrics."""
        services = self.catalog_data.get('services', [])
        total_services = len(services)

        # Calculate domain distribution
        domains = {}
        for service in services:
            domain = service.get('domain', 'unknown')
            domains[domain] = domains.get(domain, 0) + 1

        # Calculate maturity distribution
        maturities = {}
        for service in services:
            maturity = service.get('maturity', 'unknown')
            maturities[maturity] = maturities.get(maturity, 0) + 1

        return {
            'total_services': total_services,
            'total_domains': len(domains),
            'domain_distribution': domains,
            'maturity_distribution': maturities,
            'last_updated': self.catalog_data.get('metadata', {}).get('generated_at', 'Unknown')
        }

    def _get_quality_overview(self) -> Dict[str, Any]:
        """Get quality metrics overview."""
        if not self.quality_data:
            return {}

        global_data = self.quality_data.get('global', {})
        services_data = self.quality_data.get('services', {})

        return {
            'average_score': global_data.get('avg_score', 0),
            'median_score': global_data.get('median_score', 0),
            'grade_distribution': global_data.get('grade_distribution', {}),
            'services_below_threshold': len(global_data.get('services_below_threshold', [])),
            'failing_services': len([s for s in services_data.values() if s.get('status') == 'failing']),
            'total_services': len(services_data)
        }

    def _get_drift_overview(self) -> Dict[str, Any]:
        """Get drift analysis overview."""
        if not self.drift_data:
            return {}

        metadata = self.drift_data.get('metadata', {})
        summary = self.drift_data.get('summary', {})

        return {
            'total_issues': metadata.get('total_issues', 0),
            'issues_by_severity': summary.get('issues_by_severity', {}),
            'issues_by_type': summary.get('issues_by_type', {}),
            'overall_healthy': metadata.get('overall_healthy', True)
        }

    def _get_architecture_overview(self) -> Dict[str, Any]:
        """Get architecture health overview."""
        # This would load from architecture analysis if available
        # For now, return basic metrics

        services = self.catalog_data.get('services', [])

        # Count services by domain for architecture overview
        domain_services = {}
        for service in services:
            domain = service.get('domain', 'unknown')
            domain_services[domain] = domain_services.get(domain, 0) + 1

        return {
            'total_services': len(services),
            'domain_distribution': domain_services,
            'architecture_score': 85,  # Placeholder
            'last_assessment': '2025-10-05T22:30:00Z'  # Placeholder
        }

    def _generate_charts(self) -> Dict[str, str]:
        """Generate interactive charts for the dashboard."""
        charts = {}

        # Quality score distribution chart
        if self.quality_data:
            quality_chart = self._generate_quality_chart()
            if quality_chart:
                charts['quality_distribution'] = quality_chart

        # Domain distribution chart
        if self.catalog_data:
            domain_chart = self._generate_domain_chart()
            if domain_chart:
                charts['domain_distribution'] = domain_chart

        # Drift issues chart
        if self.drift_data:
            drift_chart = self._generate_drift_chart()
            if drift_chart:
                charts['drift_issues'] = drift_chart

        return charts

    def _generate_quality_chart(self) -> Optional[str]:
        """Generate quality score distribution chart."""
        try:
            services = self.quality_data.get('services', {})
            if not services:
                return None

            # Prepare data for chart
            scores = [service.get('score', 0) for service in services.values()]
            grades = [service.get('grade', 'F') for service in services.values()]

            # Create histogram
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=scores,
                nbinsx=10,
                name='Quality Scores',
                marker_color='lightblue',
                opacity=0.7
            ))

            fig.update_layout(
                title='Quality Score Distribution',
                xaxis_title='Quality Score',
                yaxis_title='Number of Services',
                showlegend=False
            )

            # Save as HTML
            chart_html = fig.to_html(full_html=False, include_plotlyjs=True)
            return chart_html

        except Exception as e:
            logger.error(f"Failed to generate quality chart: {e}")
            return None

    def _generate_domain_chart(self) -> Optional[str]:
        """Generate domain distribution chart."""
        try:
            services = self.catalog_data.get('services', [])
            if not services:
                return None

            # Count services by domain
            domain_counts = {}
            for service in services:
                domain = service.get('domain', 'unknown')
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

            # Create pie chart
            fig = go.Figure(data=[go.Pie(
                labels=list(domain_counts.keys()),
                values=list(domain_counts.values()),
                title='Services by Domain'
            )])

            fig.update_layout(
                title='Platform Services by Domain',
                showlegend=True
            )

            # Save as HTML
            chart_html = fig.to_html(full_html=False, include_plotlyjs=True)
            return chart_html

        except Exception as e:
            logger.error(f"Failed to generate domain chart: {e}")
            return None

    def _generate_drift_chart(self) -> Optional[str]:
        """Generate drift issues chart."""
        try:
            summary = self.drift_data.get('summary', {})
            issues_by_severity = summary.get('issues_by_severity', {})

            if not issues_by_severity:
                return None

            # Create bar chart
            fig = go.Figure(data=[go.Bar(
                x=list(issues_by_severity.keys()),
                y=list(issues_by_severity.values()),
                marker_color=['red' if k in ['high', 'error'] else 'orange' if k == 'moderate' else 'green' for k in issues_by_severity.keys()]
            )])

            fig.update_layout(
                title='Drift Issues by Severity',
                xaxis_title='Severity Level',
                yaxis_title='Number of Issues',
                showlegend=False
            )

            # Save as HTML
            chart_html = fig.to_html(full_html=False, include_plotlyjs=True)
            return chart_html

        except Exception as e:
            logger.error(f"Failed to generate drift chart: {e}")
            return None

    def generate_service_dashboard(self, service_name: str) -> str:
        """Generate service-specific dashboard."""
        logger.info(f"Generating dashboard for service: {service_name}")

        # Find service data
        service = next((s for s in self.catalog_data.get('services', []) if s['name'] == service_name), None)
        if not service:
            raise ValueError(f"Service not found: {service_name}")

        # Get quality data for service
        service_quality = self.quality_data.get('services', {}).get(service_name, {})

        # Get drift data for service
        service_drift = {
            'issues': [i for i in self.drift_data.get('issues', []) if i.get('service') == service_name]
        }

        # Prepare service dashboard data
        dashboard_data = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'service_name': service_name,
                'title': f'{service_name.title()} Service Dashboard'
            },
            'service_info': {
                'name': service['name'],
                'domain': service.get('domain', 'unknown'),
                'maturity': service.get('maturity', 'stable'),
                'version': service.get('version', 'unknown'),
                'runtime': service.get('runtime', 'unknown'),
                'repo': service.get('repo', 'unknown')
            },
            'quality_metrics': service_quality,
            'drift_issues': service_drift,
            'dependencies': service.get('dependencies', {}),
            'charts': self._generate_service_charts(service_name, service_quality)
        }

        # Generate HTML
        template = self.template_env.get_template("service.html.j2")
        html_content = template.render(**dashboard_data)

        # Save service dashboard
        service_dashboard_path = self.output_dir / f"service-{service_name}.html"
        with open(service_dashboard_path, 'w') as f:
            f.write(html_content)

        logger.info(f"Service dashboard saved to {service_dashboard_path}")
        return str(service_dashboard_path)

    def _generate_service_charts(self, service_name: str, quality_data: Dict[str, Any]) -> Dict[str, str]:
        """Generate charts for service-specific dashboard."""
        charts = {}

        try:
            # Quality trend chart (placeholder - would need historical data)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=[datetime.now(timezone.utc)],
                y=[quality_data.get('score', 0)],
                mode='lines+markers',
                name='Quality Score'
            ))

            fig.update_layout(
                title=f'Quality Score Trend - {service_name}',
                xaxis_title='Time',
                yaxis_title='Quality Score',
                showlegend=False
            )

            charts['quality_trend'] = fig.to_html(full_html=False, include_plotlyjs=True)

        except Exception as e:
            logger.warning(f"Failed to generate service charts for {service_name}: {e}")

        return charts

    def generate_team_dashboard(self, domain: str) -> str:
        """Generate domain-specific team dashboard."""
        logger.info(f"Generating team dashboard for domain: {domain}")

        # Filter services by domain
        domain_services = [
            s for s in self.catalog_data.get('services', [])
            if s.get('domain') == domain
        ]

        if not domain_services:
            raise ValueError(f"No services found for domain: {domain}")

        # Get quality data for domain services
        domain_quality = {
            name: self.quality_data.get('services', {}).get(name, {})
            for name in [s['name'] for s in domain_services]
        }

        # Prepare team dashboard data
        dashboard_data = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'domain': domain,
                'title': f'{domain.title()} Team Dashboard'
            },
            'team_summary': {
                'domain': domain,
                'total_services': len(domain_services),
                'maturity_distribution': self._calculate_maturity_distribution(domain_services),
                'average_quality': self._calculate_domain_average_quality(domain_quality)
            },
            'services': [
                {
                    'name': s['name'],
                    'maturity': s.get('maturity', 'unknown'),
                    'version': s.get('version', 'unknown'),
                    'quality_score': domain_quality.get(s['name'], {}).get('score', 0),
                    'quality_grade': domain_quality.get(s['name'], {}).get('grade', 'F'),
                    'dependencies': s.get('dependencies', {})
                }
                for s in domain_services
            ],
            'charts': self._generate_team_charts(domain, domain_services, domain_quality)
        }

        # Generate HTML
        template = self.template_env.get_template("team.html.j2")
        html_content = template.render(**dashboard_data)

        # Save team dashboard
        team_dashboard_path = self.output_dir / f"team-{domain}.html"
        with open(team_dashboard_path, 'w') as f:
            f.write(html_content)

        logger.info(f"Team dashboard saved to {team_dashboard_path}")
        return str(team_dashboard_path)

    def _calculate_maturity_distribution(self, services: List[Dict[str, Any]]) -> Dict[str, int]:
        """Calculate maturity distribution for services."""
        distribution = {}
        for service in services:
            maturity = service.get('maturity', 'unknown')
            distribution[maturity] = distribution.get(maturity, 0) + 1
        return distribution

    def _calculate_domain_average_quality(self, quality_data: Dict[str, Dict[str, Any]]) -> float:
        """Calculate average quality score for domain."""
        scores = [data.get('score', 0) for data in quality_data.values()]
        return sum(scores) / len(scores) if scores else 0

    def _generate_team_charts(self, domain: str, services: List[Dict[str, Any]],
                            quality_data: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """Generate charts for team dashboard."""
        charts = {}

        try:
            # Quality distribution for domain
            scores = [quality_data.get(s['name'], {}).get('score', 0) for s in services]

            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=scores,
                nbinsx=5,
                name='Quality Scores',
                marker_color='lightgreen',
                opacity=0.7
            ))

            fig.update_layout(
                title=f'Quality Score Distribution - {domain.title()}',
                xaxis_title='Quality Score',
                yaxis_title='Number of Services',
                showlegend=False
            )

            charts['quality_distribution'] = fig.to_html(full_html=False, include_plotlyjs=True)

        except Exception as e:
            logger.warning(f"Failed to generate team charts for {domain}: {e}")

        return charts

    def create_dashboard_assets(self) -> None:
        """Create static assets for dashboards."""
        # Copy CSS and JS assets
        assets_dir = self.output_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        # Create basic CSS
        css_content = """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .dashboard-header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .metric-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .metric-value {
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
        }
        .metric-label {
            color: #666;
            font-size: 0.9em;
        }
        .chart-container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .status-good { color: #28a745; }
        .status-warning { color: #ffc107; }
        .status-danger { color: #dc3545; }
        .status-info { color: #17a2b8; }
        """

        css_path = assets_dir / "dashboard.css"
        with open(css_path, 'w') as f:
            f.write(css_content)

        # Create basic JavaScript for interactivity
        js_content = """
        // Dashboard interactivity
        document.addEventListener('DOMContentLoaded', function() {
            console.log('254Carbon Dashboard loaded');

            // Add refresh functionality
            const refreshBtn = document.getElementById('refresh-dashboard');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', function() {
                    location.reload();
                });
            }

            // Add export functionality
            const exportBtn = document.getElementById('export-dashboard');
            if (exportBtn) {
                exportBtn.addEventListener('click', function() {
                    window.print();
                });
            }
        });
        """

        js_path = assets_dir / "dashboard.js"
        with open(js_path, 'w') as f:
            f.write(js_content)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate interactive platform dashboards")
    parser.add_argument("--type", choices=["overview", "service", "team"], default="overview",
                       help="Type of dashboard to generate")
    parser.add_argument("--service", type=str, help="Service name for service dashboard")
    parser.add_argument("--domain", type=str, help="Domain name for team dashboard")
    parser.add_argument("--output-dir", type=str, default="public",
                       help="Output directory for dashboard files")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        generator = DashboardGenerator(args.output_dir)

        if args.type == "overview":
            dashboard_path = generator.generate_overview_dashboard()
        elif args.type == "service":
            if not args.service:
                parser.error("--service required for service dashboard")
            dashboard_path = generator.generate_service_dashboard(args.service)
        elif args.type == "team":
            if not args.domain:
                parser.error("--domain required for team dashboard")
            dashboard_path = generator.generate_team_dashboard(args.domain)
        else:
            parser.print_help()
            sys.exit(1)

        # Create static assets
        generator.create_dashboard_assets()

        # Print success message
        print("\n📊 Dashboard Generated Successfully!")
        print(f"  Type: {args.type.title()}")
        print(f"  Location: {dashboard_path}")
        print(f"  Assets: {args.output_dir}/assets/")

        if args.type == "overview":
            print("  Access at: file://" + str(Path(dashboard_path).absolute()))

    except Exception as e:
        logger.error(f"Dashboard generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
