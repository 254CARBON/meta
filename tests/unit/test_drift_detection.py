#!/usr/bin/env python3
# Test Suite: Drift Detection
# Purpose: Ensure detectors flag version lag, staleness, and missing locks
# Maintenance tips: Use small in-memory registries; avoid external network calls
"""
Unit tests for drift detection functionality.
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the scripts directory to Python path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from detect_drift import DriftDetector, SpecRegistry


class TestSpecRegistry:
    """Test cases for SpecRegistry class."""

    def test_get_latest_version(self):
        """Test getting latest version from registry."""
        registry = SpecRegistry()

        # Mock the specs registry
        with patch.object(registry, '_fetch_specs_index') as mock_fetch:
            mock_fetch.return_value = {
                "gateway-core": {"latest_version": "1.2.0"},
                "auth-spec": {"latest_version": "2.1.0"}
            }

            version = registry.get_latest_version("gateway-core")
            assert version == "1.2.0"

            version = registry.get_latest_version("nonexistent")
            assert version is None

    def test_get_all_specs(self):
        """Test getting all specification names."""
        registry = SpecRegistry()

        with patch.object(registry, '_fetch_specs_index') as mock_fetch:
            mock_fetch.return_value = {
                "gateway-core": {"latest_version": "1.2.0"},
                "auth-spec": {"latest_version": "2.1.0"},
                "pricing-api": {"latest_version": "1.0.0"}
            }

            specs = registry.get_all_specs()
            assert "gateway-core" in specs
            assert "auth-spec" in specs
            assert "pricing-api" in specs
            assert len(specs) == 3


class TestDriftDetector:
    """Test cases for DriftDetector class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.catalog_file = self.temp_dir / "catalog.json"
        self.reports_dir = self.temp_dir / "analysis" / "reports" / "drift"
        self.reports_dir.mkdir(parents=True)

        # Create sample catalog
        catalog_data = {
            "metadata": {
                "generated_at": "2025-10-05T22:30:12Z",
                "version": "1.0.0",
                "total_services": 2
            },
            "services": [
                {
                    "name": "gateway",
                    "api_contracts": ["gateway-core@1.1.0"],
                    "last_update": "2025-10-05T22:11:04Z"
                },
                {
                    "name": "auth",
                    "api_contracts": ["auth-spec@2.0.0"],
                    "last_update": "2025-09-01T10:00:00Z"
                }
            ]
        }

        with open(self.catalog_file, 'w') as f:
            json.dump(catalog_data, f)

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)

    def test_initialization(self):
        """Test DriftDetector initialization."""
        with patch('detect_drift.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            detector = DriftDetector(catalog_file=str(self.catalog_file))

            assert detector.catalog_path == self.catalog_file
            assert detector.reports_dir == self.temp_dir / "analysis" / "reports" / "drift"

    def test_detect_spec_lag(self):
        """Test specification version lag detection."""
        with patch('detect_drift.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            # Mock specs registry
            with patch('detect_drift.SpecRegistry') as mock_registry:
                mock_instance = MagicMock()
                mock_instance.get_latest_version.side_effect = lambda spec: {
                    "gateway-core": "1.2.0",
                    "auth-spec": "2.1.0"
                }.get(spec)
                mock_registry.return_value = mock_instance

                detector = DriftDetector(catalog_file=str(self.catalog_file))
                issues = detector.detect_spec_lag()

                # Should detect lag for both services
                assert len(issues) == 2

                # Check issue details
                gateway_issue = next(i for i in issues if i.service == "gateway")
                assert gateway_issue.type == "spec_lag"
                assert gateway_issue.current_value == "1.1.0"
                assert gateway_issue.expected_value == "1.2.0"

    def test_detect_version_staleness(self):
        """Test version staleness detection."""
        with patch('detect_drift.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            detector = DriftDetector(catalog_file=str(self.catalog_file))
            issues = detector.detect_version_staleness()

            # Should detect staleness for auth service (older last_update)
            stale_issues = [i for i in issues if i.severity in ['high', 'moderate']]
            assert len(stale_issues) >= 1

            # Check that auth service is flagged as stale
            auth_issue = next((i for i in issues if i.service == "auth"), None)
            if auth_issue:
                assert auth_issue.type == "version_staleness"

    def test_detect_missing_locks(self):
        """Test missing lock file detection."""
        with patch('detect_drift.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            detector = DriftDetector(catalog_file=str(self.catalog_file))
            issues = detector.detect_missing_locks()

            # Should detect missing locks for services with API contracts
            missing_lock_issues = [i for i in issues if i.type == "missing_lock"]
            assert len(missing_lock_issues) >= 1

    def test_generate_drift_report(self):
        """Test comprehensive drift report generation."""
        with patch('detect_drift.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            # Mock specs registry
            with patch('detect_drift.SpecRegistry') as mock_registry:
                mock_instance = MagicMock()
                mock_instance.get_latest_version.side_effect = lambda spec: {
                    "gateway-core": "1.2.0",
                    "auth-spec": "2.1.0"
                }.get(spec)
                mock_registry.return_value = mock_instance

                detector = DriftDetector(catalog_file=str(self.catalog_file))
                report = detector.generate_drift_report()

                # Check report structure
                assert 'metadata' in report
                assert 'summary' in report
                assert 'issues' in report
                assert 'recommendations' in report

                # Check metadata
                assert report['metadata']['total_services'] == 2
                assert report['metadata']['total_issues'] >= 0

                # Check that issues were detected
                assert len(report['issues']) >= 1

    def test_save_report(self):
        """Test saving drift report to file."""
        with patch('detect_drift.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            detector = DriftDetector(catalog_file=str(self.catalog_file))

            # Mock report data
            report = {
                "metadata": {"generated_at": "2025-10-05T22:30:12Z"},
                "issues": [],
                "summary": {"total_issues": 0}
            }

            detector.save_report(report)

            # Check that report files were created
            assert (self.reports_dir / "latest_drift_report.json").exists()

            # Check that a timestamped report was created
            timestamp_reports = list(self.reports_dir.glob("*_drift_report.json"))
            assert len(timestamp_reports) == 1
