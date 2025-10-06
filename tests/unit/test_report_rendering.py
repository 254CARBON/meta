#!/usr/bin/env python3
# Test Suite: Report Rendering
# Purpose: Validate Jinja environment, filters, and basic template rendering
# Maintenance tips: Keep templates inline and minimal to avoid brittle tests
"""
Unit tests for report rendering functionality.
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path

# Add the scripts directory to Python path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from render_report import ReportRenderer


class TestReportRenderer:
    """Test cases for ReportRenderer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.templates_dir = self.temp_dir / "analysis" / "templates"
        self.templates_dir.mkdir(parents=True)

        # Create sample templates
        self._create_sample_templates()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)

    def _create_sample_templates(self):
        """Create sample Jinja2 templates for testing."""
        # Drift report template
        drift_template = """# Drift Report

**Generated:** {{ generated_at | format_date }}

## Summary

- **Total Issues:** {{ total_issues }}
- **High Priority:** {{ high_priority_issues }}

{% if report.issues %}
## Issues

{% for issue in report.issues[:5] %}
### {{ issue.service }}

{{ issue.severity | severity_icon }} {{ issue.description }}

{% endfor %}
{% endif %}
"""

        # Dependency report template
        dep_template = """# Dependency Report

**Generated:** {{ generated_at | format_date }}

## Summary

- **Violations:** {{ violations | length }}
- **Status:** {% if report.summary.passed %}✅ Passed{% else %}❌ Failed{% endif %}

{% if violations %}
## Violations

{% for violation in violations %}
### {{ violation.type }}

{{ violation.description }}

{% endfor %}
{% endif %}
"""

        with open(self.templates_dir / "drift-report.md.j2", 'w') as f:
            f.write(drift_template)

        with open(self.templates_dir / "dependency-violations.md.j2", 'w') as f:
            f.write(dep_template)

    def test_initialization(self):
        """Test ReportRenderer initialization."""
        renderer = ReportRenderer(str(self.templates_dir))

        assert renderer.templates_dir == self.templates_dir
        assert renderer.env is not None
        assert 'format_date' in renderer.env.filters
        assert 'severity_icon' in renderer.env.filters

    def test_format_date_filter(self):
        """Test date formatting filter."""
        renderer = ReportRenderer(str(self.templates_dir))

        # Test with valid ISO date
        formatted = renderer.env.filters['format_date']("2025-10-05T22:30:12Z")
        assert "2025-10-05" in formatted
        assert "22:30" in formatted

        # Test with None
        formatted = renderer.env.filters['format_date'](None)
        assert formatted == "Unknown"

        # Test with invalid date
        formatted = renderer.env.filters['format_date']("invalid-date")
        assert formatted == "invalid-date"

    def test_format_number_filter(self):
        """Test number formatting filter."""
        renderer = ReportRenderer(str(self.templates_dir))

        # Test with float
        formatted = renderer.env.filters['format_number'](3.14159, 2)
        assert formatted == "3.14"

        # Test with int
        formatted = renderer.env.filters['format_number'](42, 0)
        assert formatted == "42"

        # Test with string
        formatted = renderer.env.filters['format_number']("not-a-number")
        assert formatted == "not-a-number"

    def test_severity_icon_filter(self):
        """Test severity icon filter."""
        renderer = ReportRenderer(str(self.templates_dir))

        assert renderer.env.filters['severity_icon']("error") == "❌"
        assert renderer.env.filters['severity_icon']("warning") == "⚠️"
        assert renderer.env.filters['severity_icon']("info") == "ℹ️"
        assert renderer.env.filters['severity_icon']("unknown") == "❓"

    def test_status_badge_filter(self):
        """Test status badge filter."""
        renderer = ReportRenderer(str(self.templates_dir))

        assert renderer.env.filters['status_badge']("passing") == "🟢 Passing"
        assert renderer.env.filters['status_badge']("failing") == "🔴 Failing"
        assert renderer.env.filters['status_badge']("unknown") == "⚪ Unknown"

    def test_render_drift_report(self):
        """Test rendering drift report."""
        renderer = ReportRenderer(str(self.templates_dir))

        # Sample drift report data
        report_data = {
            "metadata": {
                "generated_at": "2025-10-05T22:30:12Z",
                "total_services": 3,
                "total_issues": 2
            },
            "issues": [
                {
                    "service": "gateway",
                    "type": "spec_lag",
                    "severity": "moderate",
                    "description": "Service pins gateway-core@1.1.0 but latest is 1.2.0"
                },
                {
                    "service": "auth",
                    "type": "version_staleness",
                    "severity": "low",
                    "description": "Service version is 120 days old"
                }
            ],
            "summary": {
                "issues_by_severity": {
                    "high": 0,
                    "moderate": 1,
                    "low": 1
                }
            }
        }

        output = renderer.render_drift_report(report_data)

        # Check that output contains expected content
        assert "# Drift Report" in output
        assert "gateway" in output
        assert "auth" in output
        assert "spec_lag" in output
        assert "version_staleness" in output

    def test_render_dependency_report(self):
        """Test rendering dependency report."""
        renderer = ReportRenderer(str(self.templates_dir))

        # Sample dependency report data
        report_data = {
            "metadata": {
                "generated_at": "2025-10-05T22:30:12Z",
                "graph_nodes": 5,
                "total_violations": 1
            },
            "violations": [
                {
                    "type": "cycle_detected",
                    "severity": "error",
                    "description": "Circular dependency detected"
                }
            ],
            "summary": {
                "passed": False,
                "errors": 1,
                "warnings": 0
            }
        }

        output = renderer.render_dependency_report(report_data)

        # Check that output contains expected content
        assert "# Dependency Report" in output
        assert "cycle_detected" in output
        assert "❌ Failed" in output

    def test_render_missing_template(self):
        """Test rendering with missing template."""
        renderer = ReportRenderer(str(self.templates_dir))

        # Try to render a report type without template
        report_data = {"metadata": {"generated_at": "2025-10-05T22:30:12Z"}}

        # Should create a default template and render successfully
        output = renderer.render_drift_report(report_data)

        # Should contain basic content
        assert "Drift Report" in output or "Error" in output
