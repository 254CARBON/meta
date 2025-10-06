#!/usr/bin/env python3
"""
Unit tests for compute_quality.py - Quality scoring computation functionality.

Tests cover:
- QualityMetrics: score computation, grade assignment, status determination
- QualityComputer: catalog loading, thresholds, service metric extraction
- Integration scenarios with realistic service data
"""

import unittest
import tempfile
import json
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any
from datetime import datetime, timezone, timedelta

# Import the classes we want to test
from scripts.compute_quality import (
    QualityMetrics,
    QualityComputer
)


class TestQualityMetrics(unittest.TestCase):
    """Test QualityMetrics class functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.service_name = "test-service"

    def test_quality_metrics_initialization(self):
        """Test QualityMetrics object creation."""
        metrics = QualityMetrics(
            service_name=self.service_name,
            coverage=0.85,
            lint_pass=True,
            critical_vulns=0,
            high_vulns=1,
            policy_failures=2,
            policy_warnings=0,
            build_success_rate=0.95,
            signed_images=True,
            deployment_days=5,
            drift_issues=1,
            maturity="stable",
            sbom_present=True,
            deployment_freshness_days=3
        )

        self.assertEqual(metrics.service_name, self.service_name)
        self.assertEqual(metrics.coverage, 0.85)
        self.assertEqual(metrics.critical_vulns, 0)
        self.assertEqual(metrics.high_vulns, 1)
        self.assertEqual(metrics.policy_failures, 2)
        self.assertEqual(metrics.deployment_days, 5)
        self.assertEqual(metrics.drift_issues, 1)
        self.assertEqual(metrics.maturity, "stable")
        self.assertTrue(metrics.signed_images)
        self.assertTrue(metrics.sbom_present)

    def test_compute_score_perfect_service(self):
        """Test score computation for a perfect service."""
        metrics = QualityMetrics(
            service_name="perfect-service",
            coverage=0.90,  # Above target
            critical_vulns=0,
            high_vulns=0,
            policy_failures=0,
            deployment_days=3,  # Recent deployment
            drift_issues=0,
            maturity="stable",
            signed_images=True,
            sbom_present=True
        )

        thresholds = {
            "base_score": 50,
            "weights": {
                "coverage": 0.25,
                "security": 0.35,
                "policy": 0.15,
                "stability": 0.10,
                "drift": 0.15
            },
            "coverage": {
                "target": 0.80,
                "excellent_threshold": 0.90
            },
            "security": {
                "max_critical_vulns": 0,
                "max_high_vulns": 2,
                "signed_images_bonus": 10,
                "sbom_bonus": 5
            },
            "drift": {
                "penalty_per_issue": 5,
                "max_penalty": 20
            }
        }

        score = metrics.compute_score(thresholds)

        # Perfect service should get maximum score (100)
        self.assertEqual(score, 100)

    def test_compute_score_poor_service(self):
        """Test score computation for a poor quality service."""
        metrics = QualityMetrics(
            service_name="poor-service",
            coverage=0.40,  # Below target
            critical_vulns=2,  # Critical vulnerabilities
            high_vulns=3,
            policy_failures=5,
            deployment_days=120,  # Very old deployment
            drift_issues=8,  # High drift
            maturity="stable",
            signed_images=False,
            sbom_present=False
        )

        thresholds = {
            "base_score": 50,
            "weights": {
                "coverage": 0.25,
                "security": 0.35,
                "policy": 0.15,
                "stability": 0.10,
                "drift": 0.15
            },
            "coverage": {
                "target": 0.80
            },
            "security": {
                "max_critical_vulns": 0,
                "max_high_vulns": 2,
                "signed_images_bonus": 10,
                "sbom_bonus": 5
            },
            "drift": {
                "penalty_per_issue": 5,
                "max_penalty": 20
            }
        }

        score = metrics.compute_score(thresholds)

        # Poor service should get very low score
        self.assertLess(score, 60)
        self.assertGreater(score, 0)  # Should not be negative

    def test_compute_score_beta_service_maturity_adjustment(self):
        """Test score computation with maturity adjustments."""
        # Create identical metrics but different maturity levels
        stable_metrics = QualityMetrics(
            service_name="stable-service",
            coverage=0.75,
            critical_vulns=0,
            high_vulns=1,
            policy_failures=1,
            deployment_days=15,
            drift_issues=2,
            maturity="stable",
            signed_images=True,
            sbom_present=True
        )

        beta_metrics = QualityMetrics(
            service_name="beta-service",
            coverage=0.75,
            critical_vulns=0,
            high_vulns=1,
            policy_failures=1,
            deployment_days=15,
            drift_issues=2,
            maturity="beta",
            signed_images=True,
            sbom_present=True
        )

        thresholds = {
            "base_score": 50,
            "weights": {
                "coverage": 0.25,
                "security": 0.35,
                "policy": 0.15,
                "stability": 0.10,
                "drift": 0.15
            },
            "maturity_multipliers": {
                "stable": 1.0,
                "beta": 0.9,
                "experimental": 0.8,
                "deprecated": 0.6
            }
        }

        stable_score = stable_metrics.compute_score(thresholds)
        beta_score = beta_metrics.compute_score(thresholds)

        # Beta service should get slightly lower score due to maturity multiplier
        self.assertGreater(stable_score, beta_score)
        self.assertAlmostEqual(beta_score, stable_score * 0.9, places=1)

    def test_get_grade_assignment(self):
        """Test grade assignment based on score."""
        test_cases = [
            (95, "A"),  # Excellent
            (85, "B"),  # Good
            (75, "C"),  # Acceptable
            (65, "D"),  # Needs improvement
            (50, "F"),  # Failing
        ]

        for score, expected_grade in test_cases:
            with self.subTest(score=score):
                grade = QualityMetrics.get_grade(None, score)
                self.assertEqual(grade, expected_grade)

    def test_get_status(self):
        """Test status determination based on score and thresholds."""
        thresholds = {
            "quality_grades": {
                "excellent_threshold": 90,
                "good_threshold": 80,
                "acceptable_threshold": 70
            }
        }

        test_cases = [
            (95, "excellent"),
            (85, "good"),
            (75, "acceptable"),
            (65, "needs_improvement"),
            (50, "failing"),
        ]

        for score, expected_status in test_cases:
            with self.subTest(score=score):
                status = QualityMetrics.get_status(None, score, thresholds)
                self.assertEqual(status, expected_status)

    def test_coverage_component_calculation(self):
        """Test coverage score component calculation."""
        thresholds = {
            "base_score": 50,
            "weights": {"coverage": 0.25},
            "coverage": {"target": 0.80}
        }

        # Test above target coverage
        metrics_above = QualityMetrics(
            service_name="above-target",
            coverage=0.90,
            critical_vulns=0,
            high_vulns=0,
            policy_failures=0,
            deployment_days=1,
            drift_issues=0,
            maturity="stable"
        )

        # Test below target coverage
        metrics_below = QualityMetrics(
            service_name="below-target",
            coverage=0.60,
            critical_vulns=0,
            high_vulns=0,
            policy_failures=0,
            deployment_days=1,
            drift_issues=0,
            maturity="stable"
        )

        score_above = metrics_above.compute_score(thresholds)
        score_below = metrics_below.compute_score(thresholds)

        # Above target should get higher score
        self.assertGreater(score_above, score_below)

        # Coverage component should be capped at 25 points (25% of base 50 = 12.5, but with weight 0.25)
        # Actually, let's calculate exactly:
        # Base: 50
        # Coverage above: (0.90 / 0.80) * 25 = 28.125 → capped at 25
        # Total: 50 + 25 = 75
        # Coverage below: (0.60 / 0.80) * 25 = 18.75
        # Total: 50 + 18.75 = 68.75

        self.assertAlmostEqual(score_above, 75, places=1)
        self.assertAlmostEqual(score_below, 68.75, places=1)


class TestQualityComputer(unittest.TestCase):
    """Test QualityComputer class functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.catalog_file = Path(self.temp_dir) / "catalog.json"
        self.thresholds_file = Path(self.temp_dir) / "thresholds.yaml"

        # Create mock catalog with various service types
        self.mock_catalog = {
            "services": {
                "excellent-service": {
                    "name": "excellent-service",
                    "maturity": "stable",
                    "quality": {
                        "coverage": 0.92,
                        "vulnerabilities": {
                            "critical": 0,
                            "high": 0,
                            "medium": 0,
                            "low": 0
                        }
                    },
                    "deployment": {
                        "last_update": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
                    }
                },
                "poor-service": {
                    "name": "poor-service",
                    "maturity": "stable",
                    "quality": {
                        "coverage": 0.45,
                        "vulnerabilities": {
                            "critical": 2,
                            "high": 3,
                            "medium": 5,
                            "low": 10
                        }
                    },
                    "deployment": {
                        "last_update": (datetime.now(timezone.utc) - timedelta(days=150)).isoformat()
                    }
                },
                "beta-service": {
                    "name": "beta-service",
                    "maturity": "beta",
                    "quality": {
                        "coverage": 0.70,
                        "vulnerabilities": {
                            "critical": 0,
                            "high": 1,
                            "medium": 2,
                            "low": 3
                        }
                    },
                    "deployment": {
                        "last_update": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
                    }
                }
            }
        }

        # Create mock thresholds
        self.mock_thresholds = {
            "base_score": 50,
            "weights": {
                "coverage": 0.25,
                "security": 0.35,
                "policy": 0.15,
                "stability": 0.10,
                "drift": 0.15
            },
            "coverage": {
                "target": 0.80,
                "excellent_threshold": 0.90
            },
            "security": {
                "max_critical_vulns": 0,
                "max_high_vulns": 2,
                "signed_images_bonus": 10,
                "sbom_bonus": 5
            },
            "drift": {
                "penalty_per_issue": 5,
                "max_penalty": 20
            },
            "maturity_multipliers": {
                "stable": 1.0,
                "beta": 0.9,
                "experimental": 0.8,
                "deprecated": 0.6
            }
        }

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization_with_defaults(self):
        """Test QualityComputer initialization with default files."""
        with patch('scripts.compute_quality.Path.exists') as mock_exists:
            mock_exists.return_value = True

            with patch('scripts.compute_quality.QualityComputer._load_catalog') as mock_load_catalog:
                with patch('scripts.compute_quality.QualityComputer._load_thresholds') as mock_load_thresholds:
                    mock_load_catalog.return_value = self.mock_catalog
                    mock_load_thresholds.return_value = self.mock_thresholds

                    computer = QualityComputer()

                    self.assertIsNotNone(computer.catalog_file)
                    self.assertIsNotNone(computer.thresholds_file)

    def test_initialization_with_custom_files(self):
        """Test QualityComputer initialization with custom files."""
        computer = QualityComputer(
            catalog_file=str(self.catalog_file),
            thresholds_file=str(self.thresholds_file)
        )

        self.assertEqual(computer.catalog_file, self.catalog_file)
        self.assertEqual(computer.thresholds_file, self.thresholds_file)

    def test_load_catalog(self):
        """Test catalog loading functionality."""
        # Write mock catalog to file
        with open(self.catalog_file, 'w') as f:
            json.dump(self.mock_catalog, f)

        computer = QualityComputer(catalog_file=str(self.catalog_file))
        catalog = computer._load_catalog()

        self.assertEqual(catalog, self.mock_catalog)
        self.assertIn("services", catalog)
        self.assertEqual(len(catalog["services"]), 3)

    def test_load_thresholds(self):
        """Test thresholds loading functionality."""
        # Write mock thresholds to file
        with open(self.thresholds_file, 'w') as f:
            yaml.dump(self.mock_thresholds, f)

        computer = QualityComputer(thresholds_file=str(self.thresholds_file))
        thresholds = computer._load_thresholds()

        self.assertEqual(thresholds, self.mock_thresholds)
        self.assertIn("base_score", thresholds)
        self.assertIn("weights", thresholds)

    def test_get_default_thresholds(self):
        """Test default thresholds generation."""
        computer = QualityComputer()
        thresholds = computer._get_default_thresholds()

        self.assertIn("base_score", thresholds)
        self.assertIn("weights", thresholds)
        self.assertIn("coverage", thresholds)
        self.assertIn("security", thresholds)
        self.assertIn("drift", thresholds)
        self.assertIn("maturity_multipliers", thresholds)

        # Check default values
        self.assertEqual(thresholds["base_score"], 50)
        self.assertEqual(thresholds["weights"]["coverage"], 0.25)
        self.assertEqual(thresholds["weights"]["security"], 0.35)

    def test_extract_service_metrics(self):
        """Test service metrics extraction from catalog entry."""
        computer = QualityComputer()
        computer.thresholds = self.mock_thresholds

        service_data = self.mock_catalog["services"]["excellent-service"]
        metrics = computer._extract_service_metrics(service_data)

        self.assertEqual(metrics.service_name, "excellent-service")
        self.assertEqual(metrics.maturity, "stable")
        self.assertEqual(metrics.coverage, 0.92)
        self.assertEqual(metrics.critical_vulns, 0)
        self.assertEqual(metrics.high_vulns, 0)

        # Check deployment days calculation
        expected_days = 2  # From our mock data
        self.assertEqual(metrics.deployment_days, expected_days)

    def test_extract_service_metrics_missing_data(self):
        """Test service metrics extraction with missing data."""
        computer = QualityComputer()
        computer.thresholds = self.mock_thresholds

        # Service with missing quality data
        incomplete_service = {
            "name": "incomplete-service",
            "maturity": "beta"
            # Missing quality and deployment data
        }

        metrics = computer._extract_service_metrics(incomplete_service)

        self.assertEqual(metrics.service_name, "incomplete-service")
        self.assertEqual(metrics.maturity, "beta")
        self.assertEqual(metrics.coverage, 0.0)  # Default for missing data
        self.assertEqual(metrics.critical_vulns, 0)  # Default for missing data

    def test_load_drift_data(self):
        """Test drift data loading."""
        # Create mock drift file
        drift_file = Path(self.temp_dir) / "drift-report.json"
        drift_data = {
            "excellent-service": 0,
            "poor-service": 5,
            "beta-service": 2
        }

        with open(drift_file, 'w') as f:
            json.dump(drift_data, f)

        computer = QualityComputer()
        computer.catalog = self.mock_catalog

        with patch('scripts.compute_quality.Path') as mock_path:
            mock_path.return_value.exists.return_value = True
            mock_path.return_value = drift_file

            drift = computer._load_drift_data()

            self.assertEqual(drift["excellent-service"], 0)
            self.assertEqual(drift["poor-service"], 5)
            self.assertEqual(drift["beta-service"], 2)

    def test_load_drift_data_missing_file(self):
        """Test drift data loading when file doesn't exist."""
        computer = QualityComputer()
        computer.catalog = self.mock_catalog

        with patch('scripts.compute_quality.Path') as mock_path:
            mock_path.return_value.exists.return_value = False

            drift = computer._load_drift_data()

            # Should return empty dict when file doesn't exist
            self.assertEqual(drift, {})

    def test_compute_all_quality_scores(self):
        """Test computation of quality scores for all services."""
        computer = QualityComputer()
        computer.catalog = self.mock_catalog
        computer.thresholds = self.mock_thresholds

        scores = computer.compute_all_quality_scores()

        # Check structure
        self.assertIn("services", scores)
        self.assertIn("summary", scores)
        self.assertIn("insights", scores)

        # Check service scores
        service_scores = scores["services"]
        self.assertIn("excellent-service", service_scores)
        self.assertIn("poor-service", service_scores)
        self.assertIn("beta-service", service_scores)

        # Check score ranges
        excellent_score = service_scores["excellent-service"]["score"]
        poor_score = service_scores["poor-service"]["score"]
        beta_score = service_scores["beta-service"]["score"]

        self.assertGreater(excellent_score, 90)  # Should be excellent
        self.assertLess(poor_score, 60)  # Should be failing
        self.assertGreater(beta_score, poor_score)  # Beta should score better than poor

        # Check grades
        self.assertEqual(service_scores["excellent-service"]["grade"], "A")
        self.assertEqual(service_scores["poor-service"]["grade"], "F")

    def test_generate_insights(self):
        """Test insight generation from service scores."""
        computer = QualityComputer()

        # Mock service scores
        service_scores = {
            "excellent-service": {"score": 95, "grade": "A"},
            "good-service": {"score": 85, "grade": "B"},
            "poor-service": {"score": 45, "grade": "F"}
        }

        all_scores = [95, 85, 45]

        insights = computer._generate_insights(service_scores, all_scores)

        self.assertIsInstance(insights, list)
        self.assertGreater(len(insights), 0)

        # Check for common insight patterns
        insight_text = " ".join(insights).lower()
        self.assertTrue(any("excellent" in insight_text for insight in [insight_text]))
        self.assertTrue(any("poor" in insight_text for insight in [insight_text]))

    def test_save_quality_snapshot(self):
        """Test quality snapshot saving."""
        computer = QualityComputer()
        computer.catalog = self.mock_catalog
        computer.thresholds = self.mock_thresholds

        # Create mock snapshot
        snapshot = {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "services": {
                "test-service": {
                    "score": 85,
                    "grade": "B",
                    "metrics": {}
                }
            },
            "summary": {
                "total_services": 1,
                "average_score": 85.0
            }
        }

        # Mock the catalog file path for output
        computer.catalog_file = Path(self.temp_dir) / "catalog.json"

        with patch('scripts.compute_quality.json.dump') as mock_json_dump:
            with patch('scripts.compute_quality.Path') as mock_path:
                mock_path_instance = Mock()
                mock_path_instance.parent = Path(self.temp_dir)
                mock_path.return_value = mock_path_instance

                computer.save_quality_snapshot(snapshot)

                # Verify JSON was saved twice (snapshot and latest)
                self.assertEqual(mock_json_dump.call_count, 2)


class TestQualityComputationIntegration(unittest.TestCase):
    """Integration tests for quality computation with realistic scenarios."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

        # Create realistic catalog with comprehensive service data
        self.realistic_catalog = {
            "services": {
                "gateway": {
                    "name": "gateway",
                    "domain": "access",
                    "maturity": "stable",
                    "quality": {
                        "coverage": 0.88,
                        "vulnerabilities": {
                            "critical": 0,
                            "high": 0,
                            "medium": 1,
                            "low": 2
                        }
                    },
                    "deployment": {
                        "last_update": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
                    }
                },
                "auth-service": {
                    "name": "auth-service",
                    "domain": "access",
                    "maturity": "stable",
                    "quality": {
                        "coverage": 0.92,
                        "vulnerabilities": {
                            "critical": 0,
                            "high": 1,
                            "medium": 0,
                            "low": 1
                        }
                    },
                    "deployment": {
                        "last_update": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
                    }
                },
                "streaming-service": {
                    "name": "streaming-service",
                    "domain": "data",
                    "maturity": "beta",
                    "quality": {
                        "coverage": 0.75,
                        "vulnerabilities": {
                            "critical": 0,
                            "high": 2,
                            "medium": 3,
                            "low": 5
                        }
                    },
                    "deployment": {
                        "last_update": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                    }
                },
                "ml-engine": {
                    "name": "ml-engine",
                    "domain": "ml",
                    "maturity": "experimental",
                    "quality": {
                        "coverage": 0.65,
                        "vulnerabilities": {
                            "critical": 1,
                            "high": 3,
                            "medium": 4,
                            "low": 8
                        }
                    },
                    "deployment": {
                        "last_update": (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
                    }
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

    def test_realistic_quality_computation(self):
        """Test quality computation with realistic multi-service catalog."""
        computer = QualityComputer(catalog_file=str(self.catalog_file))

        # Load catalog and thresholds
        catalog = computer._load_catalog()
        thresholds = computer._get_default_thresholds()

        self.assertEqual(len(catalog["services"]), 4)

        # Compute all scores
        scores = computer.compute_all_quality_scores()

        # Verify structure
        self.assertIn("services", scores)
        self.assertIn("summary", scores)
        self.assertIn("insights", scores)

        # Check individual service scores
        service_scores = scores["services"]
        self.assertIn("gateway", service_scores)
        self.assertIn("auth-service", service_scores)
        self.assertIn("streaming-service", service_scores)
        self.assertIn("ml-engine", service_scores)

        # Verify score relationships
        gateway_score = service_scores["gateway"]["score"]
        auth_score = service_scores["auth-service"]["score"]
        streaming_score = service_scores["streaming-service"]["score"]
        ml_score = service_scores["ml-engine"]["score"]

        # Stable services should score higher than experimental
        self.assertGreater(gateway_score, ml_score)
        self.assertGreater(auth_score, ml_score)

        # Beta service should score between stable and experimental
        self.assertGreater(streaming_score, ml_score)
        self.assertLess(streaming_score, gateway_score)

        # Check grades
        self.assertEqual(service_scores["gateway"]["grade"], "B")  # 80-89
        self.assertEqual(service_scores["auth-service"]["grade"], "A")  # 90+
        self.assertEqual(service_scores["streaming-service"]["grade"], "C")  # 70-79 (beta adjusted)
        self.assertEqual(service_scores["ml-engine"]["grade"], "F")  # <60

    def test_quality_computation_with_drift_data(self):
        """Test quality computation with drift penalty data."""
        # Create drift data file
        drift_file = Path(self.temp_dir) / "drift-report.json"
        drift_data = {
            "gateway": 0,
            "auth-service": 2,
            "streaming-service": 5,
            "ml-engine": 10
        }

        with open(drift_file, 'w') as f:
            json.dump(drift_data, f)

        computer = QualityComputer(catalog_file=str(self.catalog_file))

        # Mock drift file path
        with patch('scripts.compute_quality.Path') as mock_path:
            mock_path_instance = Mock()
            mock_path_instance.exists.return_value = True
            mock_path_instance = drift_file
            mock_path.return_value = drift_file

            scores = computer.compute_all_quality_scores()

            # Check that drift penalties were applied
            service_scores = scores["services"]

            # Services with higher drift should have lower scores
            gateway_score = service_scores["gateway"]["score"]
            auth_score = service_scores["auth-service"]["score"]
            streaming_score = service_scores["streaming-service"]["score"]
            ml_score = service_scores["ml-engine"]["score"]

            # Higher drift should result in lower scores
            self.assertGreater(gateway_score, auth_score)  # 0 drift > 2 drift
            self.assertGreater(auth_score, streaming_score)  # 2 drift > 5 drift
            self.assertGreater(streaming_score, ml_score)  # 5 drift > 10 drift

    def test_quality_summary_generation(self):
        """Test quality summary and insights generation."""
        computer = QualityComputer(catalog_file=str(self.catalog_file))

        scores = computer.compute_all_quality_scores()

        # Check summary structure
        summary = scores["summary"]
        self.assertIn("total_services", summary)
        self.assertIn("average_score", summary)
        self.assertIn("grade_distribution", summary)
        self.assertIn("domain_breakdown", summary)

        self.assertEqual(summary["total_services"], 4)

        # Check grade distribution
        grade_dist = summary["grade_distribution"]
        self.assertIn("A", grade_dist)
        self.assertIn("B", grade_dist)
        self.assertIn("C", grade_dist)
        self.assertIn("F", grade_dist)

        # Check insights
        insights = scores["insights"]
        self.assertIsInstance(insights, list)
        self.assertGreater(len(insights), 0)

        # Should contain insights about the services
        insight_text = " ".join(insights).lower()
        self.assertTrue("service" in insight_text or "quality" in insight_text)


if __name__ == '__main__':
    unittest.main()
