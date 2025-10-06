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

    def generate_health_dashboard(self) -> str:
        """Generate real-time health dashboard."""
        logger.info("Generating health dashboard...")

        # Prepare health data
        health_data = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'title': '254Carbon Platform Health Dashboard',
                'version': '1.0.0'
            },
            'service_health': self._get_service_health_status(),
            'overall_health': self._calculate_overall_health(),
            'alerts': self._get_active_alerts(),
            'incidents': self._get_recent_incidents(),
            'charts': self._generate_health_charts()
        }

        # Generate HTML
        template = self.template_env.get_template("realtime_health.html.j2")
        html_content = template.render(**health_data)

        # Save dashboard
        dashboard_path = self.output_dir / "health.html"
        with open(dashboard_path, 'w') as f:
            f.write(html_content)

        logger.info(f"Health dashboard saved to {dashboard_path}")
        return str(dashboard_path)

    def generate_quality_dashboard(self) -> str:
        """Generate quality trends dashboard."""
        logger.info("Generating quality trends dashboard...")

        # Prepare quality data
        quality_data = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'title': '254Carbon Platform Quality Trends',
                'version': '1.0.0'
            },
            'quality_summary': self._get_quality_overview(),
            'service_quality': self._get_service_quality_details(),
            'quality_trends': self._get_quality_trends(),
            'grade_distribution': self._get_grade_distribution(),
            'charts': self._generate_quality_charts()
        }

        # Generate HTML
        template = self.template_env.get_template("quality_trends.html.j2")
        html_content = template.render(**quality_data)

        # Save dashboard
        dashboard_path = self.output_dir / "quality.html"
        with open(dashboard_path, 'w') as f:
            f.write(html_content)

        logger.info(f"Quality dashboard saved to {dashboard_path}")
        return str(dashboard_path)

    def generate_release_dashboard(self) -> str:
        """Generate release calendar dashboard."""
        logger.info("Generating release calendar dashboard...")

        # Prepare release data
        release_data = {
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'title': '254Carbon Release Calendar',
                'version': '1.0.0'
            },
            'release_trains': self._get_release_trains(),
            'upcoming_releases': self._get_upcoming_releases(),
            'release_history': self._get_release_history(),
            'charts': self._generate_release_charts()
        }

        # Generate HTML
        template = self.template_env.get_template("release_calendar.html.j2")
        html_content = template.render(**release_data)

        # Save dashboard
        dashboard_path = self.output_dir / "releases.html"
        with open(dashboard_path, 'w') as f:
            f.write(html_content)

        logger.info(f"Release dashboard saved to {dashboard_path}")
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

    def _get_service_health_status(self) -> Dict[str, Any]:
        """Get health status for all services."""
        services = self.catalog_data.get('services', [])
        health_status = {}
        
        for service in services:
            service_name = service.get('name', 'unknown')
            
            # Determine health status based on quality and drift
            quality_score = self.quality_data.get('services', {}).get(service_name, {}).get('score', 0)
            drift_issues = self.drift_data.get('services', {}).get(service_name, {}).get('issues', [])
            
            # Calculate health status
            if quality_score >= 80 and len(drift_issues) == 0:
                status = 'healthy'
                color = 'green'
            elif quality_score >= 60 and len(drift_issues) <= 2:
                status = 'warning'
                color = 'yellow'
            else:
                status = 'critical'
                color = 'red'
            
            health_status[service_name] = {
                'status': status,
                'color': color,
                'quality_score': quality_score,
                'drift_issues': len(drift_issues),
                'last_updated': service.get('last_update', 'Unknown'),
                'domain': service.get('domain', 'unknown'),
                'maturity': service.get('maturity', 'unknown')
            }
        
        return health_status

    def _calculate_overall_health(self) -> Dict[str, Any]:
        """Calculate overall platform health."""
        service_health = self._get_service_health_status()
        
        total_services = len(service_health)
        healthy_services = len([s for s in service_health.values() if s['status'] == 'healthy'])
        warning_services = len([s for s in service_health.values() if s['status'] == 'warning'])
        critical_services = len([s for s in service_health.values() if s['status'] == 'critical'])
        
        # Calculate overall health percentage
        if total_services > 0:
            health_percentage = (healthy_services / total_services) * 100
        else:
            health_percentage = 0
        
        return {
            'total_services': total_services,
            'healthy_services': healthy_services,
            'warning_services': warning_services,
            'critical_services': critical_services,
            'health_percentage': round(health_percentage, 1),
            'overall_status': 'healthy' if health_percentage >= 80 else 'warning' if health_percentage >= 60 else 'critical'
        }

    def _get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts and notifications."""
        alerts = []
        
        # Check for quality threshold breaches
        quality_data = self.quality_data.get('services', {})
        for service_name, service_data in quality_data.items():
            score = service_data.get('score', 0)
            if score < 70:
                alerts.append({
                    'type': 'quality_threshold_breach',
                    'severity': 'high',
                    'service': service_name,
                    'message': f'Quality score {score} below threshold (70)',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
        
        # Check for drift issues
        drift_data = self.drift_data.get('services', {})
        for service_name, service_data in drift_data.items():
            issues = service_data.get('issues', [])
            if len(issues) > 3:
                alerts.append({
                    'type': 'drift_detected',
                    'severity': 'medium',
                    'service': service_name,
                    'message': f'{len(issues)} drift issues detected',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
        
        return alerts

    def _get_recent_incidents(self) -> List[Dict[str, Any]]:
        """Get recent incidents and outages."""
        # This would typically load from an incident management system
        # For now, return mock data
        incidents = [
            {
                'id': 'INC-001',
                'title': 'Service Discovery Crawler Timeout',
                'status': 'resolved',
                'severity': 'medium',
                'start_time': '2025-01-05T10:30:00Z',
                'end_time': '2025-01-05T11:15:00Z',
                'affected_services': ['gateway', 'auth-service'],
                'description': 'GitHub API rate limiting caused service discovery to fail'
            },
            {
                'id': 'INC-002',
                'title': 'Quality Score Calculation Error',
                'status': 'investigating',
                'severity': 'low',
                'start_time': '2025-01-06T09:00:00Z',
                'end_time': None,
                'affected_services': ['user-service'],
                'description': 'Incorrect quality score calculation for user-service'
            }
        ]
        
        return incidents

    def _generate_health_charts(self) -> Dict[str, str]:
        """Generate health-specific charts."""
        charts = {}
        
        # Health overview pie chart
        overall_health = self._calculate_overall_health()
        health_fig = go.Figure(data=[go.Pie(
            labels=['Healthy', 'Warning', 'Critical'],
            values=[overall_health['healthy_services'], 
                   overall_health['warning_services'], 
                   overall_health['critical_services']],
            colors=['#28a745', '#ffc107', '#dc3545']
        )])
        health_fig.update_layout(title="Service Health Distribution")
        charts['health_overview'] = health_fig.to_html(include_plotlyjs=False, div_id="health-overview")
        
        # Alert timeline
        alerts = self._get_active_alerts()
        if alerts:
            alert_fig = go.Figure()
            alert_fig.add_trace(go.Scatter(
                x=[alert['timestamp'] for alert in alerts],
                y=[alert['severity'] for alert in alerts],
                mode='markers',
                marker=dict(size=10, color='red'),
                text=[alert['message'] for alert in alerts],
                name='Alerts'
            ))
            alert_fig.update_layout(title="Active Alerts Timeline")
            charts['alert_timeline'] = alert_fig.to_html(include_plotlyjs=False, div_id="alert-timeline")
        
        return charts

    def _get_service_quality_details(self) -> Dict[str, Any]:
        """Get detailed quality information for all services."""
        services_data = self.quality_data.get('services', {})
        service_details = {}
        
        for service_name, service_data in services_data.items():
            service_details[service_name] = {
                'score': service_data.get('score', 0),
                'grade': service_data.get('grade', 'F'),
                'coverage': service_data.get('coverage', 0),
                'lint_pass': service_data.get('lint_pass', False),
                'critical_vulns': service_data.get('vuln_critical', 0),
                'high_vulns': service_data.get('vuln_high', 0),
                'policy_failures': service_data.get('policy_failures', 0),
                'status': service_data.get('status', 'unknown'),
                'last_updated': service_data.get('last_updated', 'Unknown')
            }
        
        return service_details

    def _get_quality_trends(self) -> List[Dict[str, Any]]:
        """Get quality trends over time."""
        # This would typically load from historical data
        # For now, return mock trend data
        trends = [
            {
                'date': '2025-01-01',
                'average_score': 75.2,
                'services_count': 3,
                'grade_distribution': {'A': 1, 'B': 1, 'C': 1, 'D': 0, 'F': 0}
            },
            {
                'date': '2025-01-02',
                'average_score': 78.5,
                'services_count': 3,
                'grade_distribution': {'A': 2, 'B': 1, 'C': 0, 'D': 0, 'F': 0}
            },
            {
                'date': '2025-01-03',
                'average_score': 82.1,
                'services_count': 3,
                'grade_distribution': {'A': 2, 'B': 1, 'C': 0, 'D': 0, 'F': 0}
            }
        ]
        
        return trends

    def _get_grade_distribution(self) -> Dict[str, int]:
        """Get current grade distribution."""
        services_data = self.quality_data.get('services', {})
        grade_dist = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}
        
        for service_data in services_data.values():
            grade = service_data.get('grade', 'F')
            if grade in grade_dist:
                grade_dist[grade] += 1
        
        return grade_dist

    def _generate_quality_charts(self) -> Dict[str, str]:
        """Generate quality-specific charts."""
        charts = {}
        
        # Quality trends over time
        trends = self._get_quality_trends()
        if trends:
            trend_fig = go.Figure()
            trend_fig.add_trace(go.Scatter(
                x=[trend['date'] for trend in trends],
                y=[trend['average_score'] for trend in trends],
                mode='lines+markers',
                name='Average Quality Score',
                line=dict(color='#007bff', width=3)
            ))
            trend_fig.update_layout(
                title="Quality Score Trends",
                xaxis_title="Date",
                yaxis_title="Average Quality Score",
                yaxis=dict(range=[0, 100])
            )
            charts['quality_trends'] = trend_fig.to_html(include_plotlyjs=False, div_id="quality-trends")
        
        # Grade distribution pie chart
        grade_dist = self._get_grade_distribution()
        grade_fig = go.Figure(data=[go.Pie(
            labels=list(grade_dist.keys()),
            values=list(grade_dist.values()),
            colors=['#28a745', '#20c997', '#ffc107', '#fd7e14', '#dc3545']
        )])
        grade_fig.update_layout(title="Grade Distribution")
        charts['grade_distribution'] = grade_fig.to_html(include_plotlyjs=False, div_id="grade-distribution")
        
        # Service quality scatter plot
        service_details = self._get_service_quality_details()
        if service_details:
            scatter_fig = go.Figure()
            
            # Group services by grade for different colors
            grade_colors = {'A': '#28a745', 'B': '#20c997', 'C': '#ffc107', 'D': '#fd7e14', 'F': '#dc3545'}
            
            for grade, color in grade_colors.items():
                grade_services = [(name, data) for name, data in service_details.items() if data['grade'] == grade]
                if grade_services:
                    scatter_fig.add_trace(go.Scatter(
                        x=[data['coverage'] for _, data in grade_services],
                        y=[data['score'] for _, data in grade_services],
                        mode='markers',
                        name=f'Grade {grade}',
                        marker=dict(color=color, size=10),
                        text=[name for name, _ in grade_services],
                        hovertemplate='<b>%{text}</b><br>Coverage: %{x}%<br>Score: %{y}<extra></extra>'
                    ))
            
            scatter_fig.update_layout(
                title="Quality Score vs Test Coverage",
                xaxis_title="Test Coverage (%)",
                yaxis_title="Quality Score",
                xaxis=dict(range=[0, 100]),
                yaxis=dict(range=[0, 100])
            )
            charts['quality_scatter'] = scatter_fig.to_html(include_plotlyjs=False, div_id="quality-scatter")
        
        return charts

    def _get_release_trains(self) -> List[Dict[str, Any]]:
        """Get active and planned release trains."""
        # Load from release trains configuration
        try:
            with open('catalog/release-trains.yaml', 'r') as f:
                trains_data = yaml.safe_load(f)
                return trains_data.get('trains', [])
        except FileNotFoundError:
            logger.warning("Release trains file not found")
            return []
        except Exception as e:
            logger.error(f"Error loading release trains: {e}")
            return []

    def _get_upcoming_releases(self) -> List[Dict[str, Any]]:
        """Get upcoming individual service releases."""
        # This would typically load from a release planning system
        # For now, return mock data
        upcoming = [
            {
                'service': 'gateway',
                'version': '1.2.0',
                'release_date': '2025-01-15',
                'status': 'planned',
                'description': 'Gateway service update with new authentication features'
            },
            {
                'service': 'auth-service',
                'version': '1.1.0',
                'release_date': '2025-01-20',
                'status': 'planned',
                'description': 'Authentication service security improvements'
            },
            {
                'service': 'user-service',
                'version': '2.0.0',
                'release_date': '2025-01-25',
                'status': 'planned',
                'description': 'Major user service refactor'
            }
        ]
        
        return upcoming

    def _get_release_history(self) -> List[Dict[str, Any]]:
        """Get recent release history."""
        # This would typically load from version control or release tracking
        # For now, return mock data
        history = [
            {
                'service': 'gateway',
                'version': '1.1.0',
                'release_date': '2025-01-05',
                'status': 'completed',
                'description': 'Gateway service bug fixes'
            },
            {
                'service': 'auth-service',
                'version': '1.0.0',
                'release_date': '2025-01-03',
                'status': 'completed',
                'description': 'Initial authentication service release'
            },
            {
                'service': 'user-service',
                'version': '1.0.0',
                'release_date': '2025-01-01',
                'status': 'completed',
                'description': 'Initial user service release'
            }
        ]
        
        return history

    def _generate_release_charts(self) -> Dict[str, str]:
        """Generate release-specific charts."""
        charts = {}
        
        # Release timeline
        upcoming = self._get_upcoming_releases()
        history = self._get_release_history()
        
        if upcoming or history:
            timeline_fig = go.Figure()
            
            # Add upcoming releases
            if upcoming:
                timeline_fig.add_trace(go.Scatter(
                    x=[release['release_date'] for release in upcoming],
                    y=[release['service'] for release in upcoming],
                    mode='markers',
                    name='Upcoming Releases',
                    marker=dict(color='#ffc107', size=15, symbol='diamond'),
                    text=[f"{release['service']} v{release['version']}" for release in upcoming],
                    hovertemplate='<b>%{text}</b><br>Date: %{x}<extra></extra>'
                ))
            
            # Add completed releases
            if history:
                timeline_fig.add_trace(go.Scatter(
                    x=[release['release_date'] for release in history],
                    y=[release['service'] for release in history],
                    mode='markers',
                    name='Completed Releases',
                    marker=dict(color='#28a745', size=12, symbol='circle'),
                    text=[f"{release['service']} v{release['version']}" for release in history],
                    hovertemplate='<b>%{text}</b><br>Date: %{x}<extra></extra>'
                ))
            
            timeline_fig.update_layout(
                title="Release Timeline",
                xaxis_title="Release Date",
                yaxis_title="Service",
                height=400
            )
            charts['release_timeline'] = timeline_fig.to_html(include_plotlyjs=False, div_id="release-timeline")
        
        # Release frequency chart
        if history:
            # Group releases by month
            monthly_releases = {}
            for release in history:
                month = release['release_date'][:7]  # YYYY-MM
                monthly_releases[month] = monthly_releases.get(month, 0) + 1
            
            freq_fig = go.Figure(data=[go.Bar(
                x=list(monthly_releases.keys()),
                y=list(monthly_releases.values()),
                marker_color='#007bff'
            )])
            freq_fig.update_layout(
                title="Release Frequency by Month",
                xaxis_title="Month",
                yaxis_title="Number of Releases"
            )
            charts['release_frequency'] = freq_fig.to_html(include_plotlyjs=False, div_id="release-frequency")
        
        return charts


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate interactive platform dashboards")
    parser.add_argument("--type", choices=["overview", "service", "team", "health", "quality", "releases"], default="overview",
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
        elif args.type == "health":
            dashboard_path = generator.generate_health_dashboard()
        elif args.type == "quality":
            dashboard_path = generator.generate_quality_dashboard()
        elif args.type == "releases":
            dashboard_path = generator.generate_release_dashboard()
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
