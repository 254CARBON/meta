#!/usr/bin/env python3
"""
254Carbon Meta Repository - Report Rendering Script

Renders Markdown reports from JSON/YAML inputs using Jinja2 templates for
posting in PRs, issues, or publishing as artifacts.

Usage:
    python scripts/render_report.py --report-type drift --input-file FILE --output-file FILE

Templates and inputs:
- Drift: expects the drift report shape from `scripts/detect_drift.py`.
- Dependency: expects the graph validation report from `scripts/validate_graph.py`.
- Catalog: expects the catalog document as per `schemas/service-index.schema.json`.
- Quality: expects the quality snapshot from `scripts/compute_quality.py`.

Environment:
- Templates live under `analysis/templates/`; filters like `format_date` and
  `severity_icon` are registered here for all templates.
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


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/render.log')
    ]
)
logger = logging.getLogger(__name__)


class ReportRenderer:
    """Renders reports using Jinja2 templates."""

    def __init__(self, templates_dir: str = "analysis/templates"):
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Add custom filters
        self.env.filters['format_date'] = self._format_date
        self.env.filters['format_number'] = self._format_number
        self.env.filters['severity_icon'] = self._severity_icon
        self.env.filters['status_badge'] = self._status_badge

    def _format_date(self, date_str: str) -> str:
        """Format ISO date for display."""
        if not date_str:
            return "Unknown"

        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, AttributeError):
            return date_str

    def _format_number(self, value: Any, decimals: int = 2) -> str:
        """Format number with specified decimal places."""
        if isinstance(value, (int, float)):
            return f"{value:.{decimals}f}"
        return str(value)

    def _severity_icon(self, severity: str) -> str:
        """Get icon for severity level."""
        icons = {
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'success': '✅',
            'high': '🔴',
            'moderate': '🟡',
            'low': '🟢'
        }
        return icons.get(severity.lower(), '❓')

    def _status_badge(self, status: str) -> str:
        """Get badge for status."""
        badges = {
            'passing': '🟢 Passing',
            'warning': '🟡 Warning',
            'failing': '🔴 Failing',
            'unknown': '⚪ Unknown',
            'active': '🟢 Active',
            'deprecated': '🟠 Deprecated',
            'experimental': '🔵 Experimental'
        }
        return badges.get(status.lower(), status)

    def render_drift_report(self, report_data: Dict[str, Any]) -> str:
        """Render drift detection report."""
        template_file = "drift-report.md.j2"

        # Prepare template data
        template_data = {
            'report': report_data,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_issues': len(report_data.get('issues', [])),
            'high_priority_issues': len([i for i in report_data.get('issues', []) if i.get('severity') in ['high', 'error']]),
            'summary': report_data.get('summary', {})
        }

        return self._render_template(template_file, template_data)

    def render_dependency_report(self, report_data: Dict[str, Any]) -> str:
        """Render dependency validation report."""
        template_file = "dependency-violations.md.j2"

        # Prepare template data
        template_data = {
            'report': report_data,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'violations': report_data.get('violations', []),
            'summary': report_data.get('summary', {})
        }

        return self._render_template(template_file, template_data)

    def render_catalog_summary(self, catalog_data: Dict[str, Any]) -> str:
        """Render catalog summary report."""
        template_file = "catalog-summary.md.j2"

        # Prepare template data
        services = catalog_data.get('services', [])
        domains = {}
        maturities = {}
        runtimes = {}

        for service in services:
            domain = service.get('domain', 'unknown')
            maturity = service.get('maturity', 'unknown')
            runtime = service.get('runtime', 'unknown')

            domains[domain] = domains.get(domain, 0) + 1
            maturities[maturity] = maturities.get(maturity, 0) + 1
            runtimes[runtime] = runtimes.get(runtime, 0) + 1

        template_data = {
            'catalog': catalog_data,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_services': len(services),
            'domains': domains,
            'maturities': maturities,
            'runtimes': runtimes,
            'services': services[:20]  # Limit for display
        }

        return self._render_template(template_file, template_data)

    def render_quality_report(self, quality_data: Dict[str, Any]) -> str:
        """Render quality metrics report."""
        template_file = "quality-summary.md.j2"

        # Prepare template data
        services = quality_data.get('services', {})
        service_list = [
            {
                'name': name,
                'score': data.get('score', 0),
                'grade': data.get('grade', 'F'),
                'coverage': data.get('coverage', 0),
                'lint_pass': data.get('lint_pass', False),
                'critical_vulns': data.get('vuln_critical', 0)
            }
            for name, data in services.items()
        ]

        # Sort by score descending
        service_list.sort(key=lambda x: x['score'], reverse=True)

        template_data = {
            'quality': quality_data,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_services': len(services),
            'global_avg': quality_data.get('global', {}).get('avg_score', 0),
            'services': service_list,
            'grade_distribution': quality_data.get('global', {}).get('quality_distribution', {})
        }

        return self._render_template(template_file, template_data)

    def _render_template(self, template_file: str, data: Dict[str, Any]) -> str:
        """Render template with data."""
        try:
            template_path = self.templates_dir / template_file

            # If template doesn't exist, create a default one
            if not template_path.exists():
                logger.warning(f"Template not found: {template_path}, creating default")
                self._create_default_template(template_file)

            template = self.env.get_template(template_file)
            return template.render(**data)

        except Exception as e:
            logger.error(f"Failed to render template {template_file}: {e}")
            return f"Error rendering template: {e}"

    def _create_default_template(self, template_file: str) -> None:
        """Create a default template if it doesn't exist."""
        template_content = self._get_default_template_content(template_file)

        with open(self.templates_dir / template_file, 'w') as f:
            f.write(template_content)

    def _get_default_template_content(self, template_file: str) -> str:
        """Get default template content based on file name."""
        if 'drift' in template_file:
            return """# Drift Detection Report

Generated: {{ generated_at | format_date }}

## Summary

- **Total Issues:** {{ total_issues }}
- **High Priority:** {{ high_priority_issues }}
- **Overall Status:** {% if summary.issues_by_severity.high > 0 or summary.issues_by_severity.error > 0 %}⚠️ Needs Attention{% else %}✅ Healthy{% endif %}

## Issues by Severity

- 🔴 **High:** {{ summary.issues_by_severity.high | default(0) }}
- 🟡 **Moderate:** {{ summary.issues_by_severity.moderate | default(0) }}
- 🟢 **Low:** {{ summary.issues_by_severity.low | default(0) }}

## Issues by Type

{% for type, count in summary.issues_by_type.items() %}
- {{ type | title }}: {{ count }}
{% endfor %}

{% if report.issues %}
## Detailed Issues

{% for issue in report.issues[:20] %}
### {{ issue.service }} - {{ issue.type | title }}

{{ issue.severity | severity_icon }} **{{ issue.severity | title }}**

{{ issue.description }}

**Current:** {{ issue.current_value }}
**Expected:** {{ issue.expected_value }}
**Remediation:** {{ issue.remediation }}

---
{% endfor %}
{% endif %}

*Generated by 254Carbon Meta*
"""

        elif 'dependency' in template_file:
            return """# Dependency Validation Report

Generated: {{ generated_at | format_date }}

## Summary

- **Graph Nodes:** {{ report.metadata.graph_nodes | default(0) }}
- **Graph Edges:** {{ report.metadata.graph_edges | default(0) }}
- **Violations:** {{ report.metadata.total_violations | default(0) }}
- **Status:** {% if summary.passed %}✅ Passed{% else %}❌ Failed{% endif %}

## Violations by Severity

- 🔴 **Errors:** {{ summary.errors | default(0) }}
- 🟡 **Warnings:** {{ summary.warnings | default(0) }}

{% if violations %}
## Detailed Violations

{% for violation in violations %}
### {{ violation.type | title }}

{{ violation.severity | severity_icon }} **{{ violation.severity | title }}**

{{ violation.description }}

{% if violation.details %}
**Details:**
{% for key, value in violation.details.items() %}
- {{ key }}: {{ value }}
{% endfor %}
{% endif %}

---
{% endfor %}
{% endif %}

*Generated by 254Carbon Meta*
"""

        elif 'catalog-summary' in template_file:
            return """# Service Catalog Summary

Generated: {{ generated_at | format_date }}

## Overview

- **Total Services:** {{ total_services }}
- **Catalog Version:** {{ catalog.metadata.version | default('1.0.0') }}
- **Last Updated:** {{ catalog.metadata.generated_at | format_date }}

## Services by Domain

{% for domain, count in domains.items() %}
- **{{ domain | title }}:** {{ count }} services
{% endfor %}

## Services by Maturity

{% for maturity, count in maturities.items() %}
- **{{ maturity | title }}:** {{ count }} services
{% endfor %}

## Services by Runtime

{% for runtime, count in runtimes.items() %}
- **{{ runtime | title }}:** {{ count }} services
{% endfor %}

## Recent Services

{% for service in services %}
### {{ service.name }}

- **Domain:** {{ service.domain | title }}
- **Maturity:** {{ service.maturity | status_badge }}
- **Version:** {{ service.version }}
- **Runtime:** {{ service.runtime | default('Not specified') }}

{% endfor %}

*Generated by 254Carbon Meta*
"""

        elif 'quality-summary' in template_file:
            return """# Quality Metrics Summary

Generated: {{ generated_at | format_date }}

## Overview

- **Total Services:** {{ total_services }}
- **Average Score:** {{ global_avg | format_number(1) }}/100
- **Overall Grade:** {% if global_avg >= 90 %}A (Excellent){% elif global_avg >= 80 %}B (Good){% elif global_avg >= 70 %}C (Acceptable){% elif global_avg >= 60 %}D (Needs Improvement){% else %}F (Failing){% endif %}

## Grade Distribution

{% for grade, count in grade_distribution.items() %}
- **{{ grade }}:** {{ count }} services
{% endfor %}

## Service Quality Rankings

| Service | Score | Grade | Coverage | Lint | Critical Vulns |
|---------|-------|-------|----------|------|----------------|
{% for service in services %}
| {{ service.name }} | {{ service.score | format_number(1) }} | {{ service.grade }} | {{ service.coverage | format_number(1) }} | {{ service.lint_pass | upper }} | {{ service.critical_vulns }} |
{% endfor %}

## Quality Insights

{% for service in services %}
{% if service.score < 70 %}
⚠️ **{{ service.name }}** needs attention (Score: {{ service.score | format_number(1) }})
{% endif %}
{% endfor %}

*Generated by 254Carbon Meta*
"""

        else:
            return """# Report

Generated: {{ generated_at | format_date }}

**Report Type:** {{ report_type | default('Unknown') }}

No template available for this report type.

*Generated by 254Carbon Meta*
"""


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Render reports using Jinja2 templates")
    parser.add_argument("--report-type", required=True, choices=['drift', 'dependency', 'catalog', 'quality'],
                       help="Type of report to render")
    parser.add_argument("--input-file", required=True, help="Input JSON/YAML report file")
    parser.add_argument("--output-file", help="Output markdown file (default: stdout)")
    parser.add_argument("--templates-dir", default="analysis/templates", help="Templates directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Load input data
        input_path = Path(args.input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        with open(input_path) as f:
            if input_path.suffix.lower() in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            else:
                data = json.load(f)

        # Create renderer
        renderer = ReportRenderer(args.templates_dir)

        # Render report
        if args.report_type == 'drift':
            output = renderer.render_drift_report(data)
        elif args.report_type == 'dependency':
            output = renderer.render_dependency_report(data)
        elif args.report_type == 'catalog':
            output = renderer.render_catalog_summary(data)
        elif args.report_type == 'quality':
            output = renderer.render_quality_report(data)
        else:
            raise ValueError(f"Unknown report type: {args.report_type}")

        # Output result
        if args.output_file:
            output_path = Path(args.output_file)
            with open(output_path, 'w') as f:
                f.write(output)
            logger.info(f"Report saved to {output_path}")
        else:
            print(output)

    except Exception as e:
        logger.error(f"Report rendering failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
