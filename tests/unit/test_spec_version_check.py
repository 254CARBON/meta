#!/usr/bin/env python3
"""
Unit tests for spec_version_check.py - Specification version checking functionality.

Tests cover:
- SpecVersion: version comparison, upgrade type determination
- SpecVersionChecker: registry fetching, recommendation generation
- Integration scenarios with realistic spec data
"""

import unittest
import tempfile
import json
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any
from packaging import version

# Import the classes we want to test
from scripts.spec_version_check import (
    SpecVersion,
    UpgradeRecommendation,
    SpecVersionChecker
)


class TestSpecVersion(unittest.TestCase):
    """Test SpecVersion class functionality."""

    def test_spec_version_initialization(self):
        """Test SpecVersion object creation."""
        spec = SpecVersion(
            name="gateway-core",
            current_version="1.0.0",
            latest_version="1.2.0"
        )

        self.assertEqual(spec.name, "gateway-core")
        self.assertEqual(spec.current_version, "1.0.0")
        self.assertEqual(spec.latest_version, "1.2.0")

    def test_version_comparison_patch(self):
        """Test patch version comparison."""
        spec = SpecVersion(
            name="test-spec",
            current_version="1.0.0",
            latest_version="1.0.2"
        )

        # Post-init should calculate upgrade type
        self.assertEqual(spec.upgrade_type, "patch")
        self.assertEqual(spec.version_diff, "0.0.2")

    def test_version_comparison_minor(self):
        """Test minor version comparison."""
        spec = SpecVersion(
            name="test-spec",
            current_version="1.0.0",
            latest_version="1.2.0"
        )

        self.assertEqual(spec.upgrade_type, "minor")
        self.assertEqual(spec.version_diff, "0.2.0")

    def test_version_comparison_major(self):
        """Test major version comparison."""
        spec = SpecVersion(
            name="test-spec",
            current_version="1.0.0",
            latest_version="2.0.0"
        )

        self.assertEqual(spec.upgrade_type, "major")
        self.assertEqual(spec.version_diff, "1.0.0")

    def test_version_comparison_up_to_date(self):
        """Test version comparison when already up to date."""
        spec = SpecVersion(
            name="test-spec",
            current_version="1.2.0",
            latest_version="1.2.0"
        )

        self.assertEqual(spec.upgrade_type, "none")
        self.assertEqual(spec.version_diff, "0.0.0")

    def test_version_comparison_complex(self):
        """Test complex version comparison."""
        test_cases = [
            ("1.0.0", "1.0.1", "patch"),
            ("1.0.0", "1.1.0", "minor"),
            ("1.0.0", "2.0.0", "major"),
            ("1.2.3", "1.2.4", "patch"),
            ("1.2.3", "1.3.0", "minor"),
            ("1.2.3", "2.0.0", "major"),
        ]

        for current, latest, expected_type in test_cases:
            with self.subTest(current=current, latest=latest):
                spec = SpecVersion(
                    name="test-spec",
                    current_version=current,
                    latest_version=latest
                )
                self.assertEqual(spec.upgrade_type, expected_type)


class TestUpgradeRecommendation(unittest.TestCase):
    """Test UpgradeRecommendation class functionality."""

    def test_recommendation_initialization(self):
        """Test UpgradeRecommendation object creation."""
        spec = SpecVersion(
            name="gateway-core",
            current_version="1.0.0",
            latest_version="1.2.0"
        )

        recommendation = UpgradeRecommendation(
            service_name="gateway",
            spec_version=spec,
            priority="high",
            effort="medium",
            auto_upgrade_eligible=True,
            breaking_changes=False
        )

        self.assertEqual(recommendation.service_name, "gateway")
        self.assertEqual(recommendation.spec_version.name, "gateway-core")
        self.assertEqual(recommendation.priority, "high")
        self.assertEqual(recommendation.effort, "medium")
        self.assertTrue(recommendation.auto_upgrade_eligible)
        self.assertFalse(recommendation.breaking_changes)

    def test_recommendation_priority_levels(self):
        """Test different priority levels."""
        priorities = ["critical", "high", "medium", "low"]

        for priority in priorities:
            with self.subTest(priority=priority):
                spec = SpecVersion(
                    name="test-spec",
                    current_version="1.0.0",
                    latest_version="1.1.0"
                )

                recommendation = UpgradeRecommendation(
                    service_name="test-service",
                    spec_version=spec,
                    priority=priority,
                    effort="low",
                    auto_upgrade_eligible=False,
                    breaking_changes=False
                )

                self.assertEqual(recommendation.priority, priority)


class TestSpecVersionChecker(unittest.TestCase):
    """Test SpecVersionChecker class functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.catalog_file = Path(self.temp_dir) / "catalog.json"
        self.policies_file = Path(self.temp_dir) / "upgrade-policies.yaml"

        # Create mock catalog
        self.mock_catalog = {
            "services": {
                "gateway": {
                    "name": "gateway",
                    "maturity": "stable",
                    "api_contracts": [
                        "gateway-core@1.0.0",
                        "auth-service@2.0.0"
                    ],
                    "quality": {
                        "coverage": 0.85
                    }
                },
                "streaming": {
                    "name": "streaming",
                    "maturity": "beta",
                    "api_contracts": [
                        "streaming-api@1.5.0"
                    ],
                    "quality": {
                        "coverage": 0.70
                    }
                }
            }
        }

        # Create mock upgrade policies
        self.mock_policies = {
            "auto_upgrade": {
                "patch": True,
                "minor": True,
                "major": False
            },
            "quality_threshold": {
                "patch": 70,
                "minor": 80,
                "major": 90
            },
            "maturity_restrictions": {
                "experimental": {"patch": False, "minor": False, "major": False},
                "beta": {"patch": True, "minor": True, "major": False},
                "stable": {"patch": True, "minor": True, "major": False}
            }
        }

        # Create mock specs registry
        self.mock_specs_registry = {
            "gateway-core": {
                "name": "gateway-core",
                "latest_version": "1.2.0",
                "versions": {
                    "1.0.0": {"released": "2024-01-01"},
                    "1.1.0": {"released": "2024-06-01"},
                    "1.2.0": {"released": "2024-12-01"}
                }
            },
            "auth-service": {
                "name": "auth-service",
                "latest_version": "2.0.0",
                "versions": {
                    "2.0.0": {"released": "2024-11-01"}
                }
            },
            "streaming-api": {
                "name": "streaming-api",
                "latest_version": "2.0.0",
                "versions": {
                    "1.5.0": {"released": "2024-08-01"},
                    "2.0.0": {"released": "2024-12-01"}
                }
            }
        }

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization_with_defaults(self):
        """Test SpecVersionChecker initialization with default files."""
        with patch('scripts.spec_version_check.Path.exists') as mock_exists:
            mock_exists.return_value = True

            with patch('scripts.spec_version_check.SpecVersionChecker._load_catalog') as mock_load_catalog:
                with patch('scripts.spec_version_check.SpecVersionChecker._load_upgrade_policies') as mock_load_policies:
                    mock_load_catalog.return_value = self.mock_catalog
                    mock_load_policies.return_value = self.mock_policies

                    checker = SpecVersionChecker()

                    self.assertIsNotNone(checker.catalog_file)
                    self.assertEqual(checker.specs_repo, "254carbon/254carbon-specs")

    def test_initialization_with_custom_files(self):
        """Test SpecVersionChecker initialization with custom files."""
        checker = SpecVersionChecker(
            catalog_file=str(self.catalog_file),
            specs_repo="custom-org/specs"
        )

        self.assertEqual(checker.catalog_file, self.catalog_file)
        self.assertEqual(checker.specs_repo, "custom-org/specs")

    def test_load_catalog(self):
        """Test catalog loading functionality."""
        # Write mock catalog to file
        with open(self.catalog_file, 'w') as f:
            json.dump(self.mock_catalog, f)

        checker = SpecVersionChecker(catalog_file=str(self.catalog_file))
        catalog = checker._load_catalog()

        self.assertEqual(catalog, self.mock_catalog)
        self.assertIn("services", catalog)
        self.assertEqual(len(catalog["services"]), 2)

    def test_load_upgrade_policies(self):
        """Test upgrade policies loading functionality."""
        # Write mock policies to file
        with open(self.policies_file, 'w') as f:
            yaml.dump(self.mock_policies, f)

        checker = SpecVersionChecker(upgrade_policies_file=str(self.policies_file))
        policies = checker._load_upgrade_policies()

        self.assertEqual(policies, self.mock_policies)
        self.assertIn("auto_upgrade", policies)
        self.assertIn("quality_threshold", policies)

    def test_get_default_policies(self):
        """Test default policies generation."""
        checker = SpecVersionChecker()
        policies = checker._get_default_policies()

        self.assertIn("auto_upgrade", policies)
        self.assertIn("quality_threshold", policies)
        self.assertIn("maturity_restrictions", policies)

        # Check default values
        self.assertTrue(policies["auto_upgrade"]["patch"])
        self.assertTrue(policies["auto_upgrade"]["minor"])
        self.assertFalse(policies["auto_upgrade"]["major"])

    def test_fetch_specs_registry(self):
        """Test specs registry fetching."""
        checker = SpecVersionChecker()

        with patch('scripts.spec_version_check.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = self.mock_specs_registry
            mock_get.return_value = mock_response

            registry = checker._fetch_specs_registry()

            self.assertEqual(registry, self.mock_specs_registry)
            self.assertIn("gateway-core", registry)
            self.assertIn("auth-service", registry)

    def test_fetch_specs_registry_failure(self):
        """Test specs registry fetching with failure."""
        checker = SpecVersionChecker()

        with patch('scripts.spec_version_check.requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")

            registry = checker._fetch_specs_registry()

            # Should return empty dict on failure
            self.assertEqual(registry, {})

    def test_check_service_spec_versions(self):
        """Test checking spec versions for all services."""
        checker = SpecVersionChecker()
        checker.catalog = self.mock_catalog
        checker.policies = self.mock_policies
        checker.specs_registry = self.mock_specs_registry

        recommendations = checker.check_service_spec_versions()

        # Should generate recommendations for outdated specs
        self.assertIsInstance(recommendations, list)
        self.assertGreater(len(recommendations), 0)

        # Check that gateway-core upgrade is recommended (1.0.0 -> 1.2.0)
        gateway_recs = [r for r in recommendations if r.service_name == "gateway"]
        self.assertGreater(len(gateway_recs), 0)

        # Check recommendation details
        gateway_rec = gateway_recs[0]
        self.assertEqual(gateway_rec.spec_version.name, "gateway-core")
        self.assertEqual(gateway_rec.spec_version.current_version, "1.0.0")
        self.assertEqual(gateway_rec.spec_version.latest_version, "1.2.0")
        self.assertEqual(gateway_rec.spec_version.upgrade_type, "minor")

    def test_generate_recommendation_patch_upgrade(self):
        """Test recommendation generation for patch upgrade."""
        checker = SpecVersionChecker()
        checker.catalog = self.mock_catalog
        checker.policies = self.mock_policies

        spec = SpecVersion(
            name="test-spec",
            current_version="1.0.0",
            latest_version="1.0.2"
        )

        service = self.mock_catalog["services"]["gateway"]
        recommendation = checker._generate_recommendation("gateway", spec)

        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation.priority, "low")
        self.assertEqual(recommendation.effort, "low")
        self.assertTrue(recommendation.auto_upgrade_eligible)
        self.assertFalse(recommendation.breaking_changes)

    def test_generate_recommendation_minor_upgrade(self):
        """Test recommendation generation for minor upgrade."""
        checker = SpecVersionChecker()
        checker.catalog = self.mock_catalog
        checker.policies = self.mock_policies

        spec = SpecVersion(
            name="test-spec",
            current_version="1.0.0",
            latest_version="1.2.0"
        )

        service = self.mock_catalog["services"]["gateway"]
        recommendation = checker._generate_recommendation("gateway", spec)

        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation.priority, "medium")
        self.assertEqual(recommendation.effort, "medium")
        self.assertTrue(recommendation.auto_upgrade_eligible)
        self.assertFalse(recommendation.breaking_changes)

    def test_generate_recommendation_major_upgrade(self):
        """Test recommendation generation for major upgrade."""
        checker = SpecVersionChecker()
        checker.catalog = self.mock_catalog
        checker.policies = self.mock_policies

        spec = SpecVersion(
            name="test-spec",
            current_version="1.0.0",
            latest_version="2.0.0"
        )

        service = self.mock_catalog["services"]["gateway"]
        recommendation = checker._generate_recommendation("gateway", spec)

        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation.priority, "high")
        self.assertEqual(recommendation.effort, "high")
        self.assertFalse(recommendation.auto_upgrade_eligible)
        self.assertTrue(recommendation.breaking_changes)

    def test_generate_recommendation_quality_threshold(self):
        """Test recommendation generation with quality threshold check."""
        checker = SpecVersionChecker()
        checker.policies = self.mock_policies

        # Service with low quality
        low_quality_service = {
            "name": "low-quality-service",
            "maturity": "stable",
            "quality": {
                "coverage": 0.50  # Below threshold
            }
        }

        checker.catalog = {"services": {"low-quality-service": low_quality_service}}

        spec = SpecVersion(
            name="test-spec",
            current_version="1.0.0",
            latest_version="1.1.0"
        )

        recommendation = checker._generate_recommendation("low-quality-service", spec)

        # Should not be eligible for auto-upgrade due to low quality
        self.assertIsNotNone(recommendation)
        self.assertFalse(recommendation.auto_upgrade_eligible)

    def test_generate_upgrade_prs_dry_run(self):
        """Test upgrade PR generation in dry run mode."""
        checker = SpecVersionChecker()

        spec = SpecVersion(
            name="test-spec",
            current_version="1.0.0",
            latest_version="1.1.0"
        )

        recommendations = [
            UpgradeRecommendation(
                service_name="test-service",
                spec_version=spec,
                priority="medium",
                effort="medium",
                auto_upgrade_eligible=True,
                breaking_changes=False
            )
        ]

        result = checker.generate_upgrade_prs(recommendations, dry_run=True)

        # Should show what would be done
        self.assertIn("dry_run", result)
        self.assertTrue(result["dry_run"])
        self.assertIn("prs_to_create", result)

    def test_generate_report(self):
        """Test report generation."""
        checker = SpecVersionChecker()
        checker.catalog = self.mock_catalog
        checker.policies = self.mock_policies
        checker.specs_registry = self.mock_specs_registry

        report = checker.generate_report()

        # Check report structure
        self.assertIn("checked_at", report)
        self.assertIn("total_services", report)
        self.assertIn("total_recommendations", report)
        self.assertIn("recommendations", report)
        self.assertIn("summary", report)

        # Check summary
        summary = report["summary"]
        self.assertIn("by_priority", summary)
        self.assertIn("by_upgrade_type", summary)
        self.assertIn("auto_upgrade_eligible", summary)

    def test_save_report(self):
        """Test report saving."""
        checker = SpecVersionChecker()
        checker.catalog_file = Path(self.temp_dir) / "catalog.json"

        report = {
            "checked_at": "2025-01-06T10:00:00Z",
            "total_services": 2,
            "total_recommendations": 3,
            "recommendations": [],
            "summary": {}
        }

        with patch('scripts.spec_version_check.json.dump') as mock_json_dump:
            checker.save_report(report)

            # Verify JSON was saved
            mock_json_dump.assert_called_once()


class TestSpecVersionCheckIntegration(unittest.TestCase):
    """Integration tests for spec version checking with realistic scenarios."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

        # Create realistic catalog with various spec versions
        self.realistic_catalog = {
            "services": {
                "gateway": {
                    "name": "gateway",
                    "domain": "access",
                    "maturity": "stable",
                    "api_contracts": [
                        "gateway-core@1.0.0",  # Outdated
                        "auth-api@2.0.0"       # Up to date
                    ],
                    "quality": {"coverage": 0.88}
                },
                "streaming": {
                    "name": "streaming",
                    "domain": "data",
                    "maturity": "beta",
                    "api_contracts": [
                        "streaming-api@1.5.0"  # Outdated
                    ],
                    "quality": {"coverage": 0.75}
                },
                "ml-engine": {
                    "name": "ml-engine",
                    "domain": "ml",
                    "maturity": "experimental",
                    "api_contracts": [
                        "ml-api@0.5.0"  # Very outdated
                    ],
                    "quality": {"coverage": 0.60}
                }
            }
        }

        # Create realistic specs registry
        self.realistic_specs_registry = {
            "gateway-core": {
                "name": "gateway-core",
                "latest_version": "1.3.0",
                "versions": {
                    "1.0.0": {"released": "2024-01-01"},
                    "1.1.0": {"released": "2024-04-01"},
                    "1.2.0": {"released": "2024-08-01"},
                    "1.3.0": {"released": "2024-12-01"}
                }
            },
            "auth-api": {
                "name": "auth-api",
                "latest_version": "2.0.0",
                "versions": {
                    "2.0.0": {"released": "2024-11-01"}
                }
            },
            "streaming-api": {
                "name": "streaming-api",
                "latest_version": "2.0.0",
                "versions": {
                    "1.5.0": {"released": "2024-06-01"},
                    "2.0.0": {"released": "2024-12-01"}
                }
            },
            "ml-api": {
                "name": "ml-api",
                "latest_version": "1.0.0",
                "versions": {
                    "0.5.0": {"released": "2024-03-01"},
                    "1.0.0": {"released": "2024-12-01"}
                }
            }
        }

        # Write catalog to file
        self.catalog_file = Path(self.temp_dir) / "catalog.json"
        with open(self.catalog_file, 'w') as f:
            json.dump(self.realistic_catalog, f)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_realistic_spec_version_check(self):
        """Test spec version checking with realistic catalog."""
        checker = SpecVersionChecker(catalog_file=str(self.catalog_file))
        checker.specs_registry = self.realistic_specs_registry

        recommendations = checker.check_service_spec_versions()

        # Should generate recommendations for outdated specs
        self.assertGreater(len(recommendations), 0)

        # Check gateway recommendations
        gateway_recs = [r for r in recommendations if r.service_name == "gateway"]
        self.assertEqual(len(gateway_recs), 1)  # Only gateway-core is outdated

        gateway_rec = gateway_recs[0]
        self.assertEqual(gateway_rec.spec_version.name, "gateway-core")
        self.assertEqual(gateway_rec.spec_version.current_version, "1.0.0")
        self.assertEqual(gateway_rec.spec_version.latest_version, "1.3.0")
        self.assertEqual(gateway_rec.spec_version.upgrade_type, "minor")

        # Check streaming recommendations
        streaming_recs = [r for r in recommendations if r.service_name == "streaming"]
        self.assertEqual(len(streaming_recs), 1)

        streaming_rec = streaming_recs[0]
        self.assertEqual(streaming_rec.spec_version.name, "streaming-api")
        self.assertEqual(streaming_rec.spec_version.upgrade_type, "major")

        # Check ml-engine recommendations
        ml_recs = [r for r in recommendations if r.service_name == "ml-engine"]
        self.assertEqual(len(ml_recs), 1)

        ml_rec = ml_recs[0]
        self.assertEqual(ml_rec.spec_version.name, "ml-api")
        self.assertEqual(ml_rec.spec_version.upgrade_type, "major")

    def test_complete_workflow(self):
        """Test complete spec version check workflow."""
        checker = SpecVersionChecker(catalog_file=str(self.catalog_file))
        checker.specs_registry = self.realistic_specs_registry

        # Generate report
        report = checker.generate_report()

        # Verify report structure
        self.assertIn("checked_at", report)
        self.assertIn("total_services", report)
        self.assertIn("total_recommendations", report)
        self.assertIn("recommendations", report)
        self.assertIn("summary", report)

        # Check counts
        self.assertEqual(report["total_services"], 3)
        self.assertEqual(report["total_recommendations"], 3)  # All 3 services have outdated specs

        # Check summary breakdown
        summary = report["summary"]
        self.assertIn("by_priority", summary)
        self.assertIn("by_upgrade_type", summary)

        # Verify upgrade type distribution
        by_type = summary["by_upgrade_type"]
        self.assertIn("minor", by_type)
        self.assertIn("major", by_type)


if __name__ == '__main__':
    unittest.main()
