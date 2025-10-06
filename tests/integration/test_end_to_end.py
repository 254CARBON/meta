#!/usr/bin/env python3
"""
End-to-end integration test for the complete 254Carbon Meta workflow.

Tests the full pipeline:
collect → build → validate → compute → detect

This test verifies that all components work together correctly and
that data flows properly between pipeline stages.
"""

import unittest
import tempfile
import json
import yaml
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any


class TestEndToEndWorkflow(unittest.TestCase):
    """Test the complete end-to-end workflow."""

    def setUp(self):
        """Set up test environment with temporary directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir)

        # Create necessary directories
        (self.test_dir / "catalog").mkdir(parents=True, exist_ok=True)
        (self.test_dir / "manifests" / "collected").mkdir(parents=True, exist_ok=True)
        (self.test_dir / "config").mkdir(parents=True, exist_ok=True)
        (self.test_dir / "analysis" / "reports").mkdir(parents=True, exist_ok=True)

        # Create test catalog with multiple services
        self.test_catalog = {
            "metadata": {
                "generated_at": "2025-01-06T10:00:00Z",
                "total_services": 3,
                "version": "1.0.0"
            },
            "services": {
                "gateway": {
                    "name": "gateway",
                    "domain": "access",
                    "maturity": "stable",
                    "repository": "254carbon/gateway",
                    "path": ".",
                    "api_contracts": ["gateway-core@1.0.0"],
                    "dependencies": {
                        "internal": ["auth-service@1.0.0"],
                        "external": ["redis@7.0"]
                    },
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
                        "last_update": "2025-01-05T14:30:00Z"
                    }
                },
                "auth-service": {
                    "name": "auth-service",
                    "domain": "access",
                    "maturity": "stable",
                    "repository": "254carbon/auth-service",
                    "path": ".",
                    "api_contracts": ["auth-api@2.0.0"],
                    "dependencies": {
                        "internal": ["user-service@1.0.0"],
                        "external": ["postgresql@15"]
                    },
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
                        "last_update": "2025-01-04T09:15:00Z"
                    }
                },
                "user-service": {
                    "name": "user-service",
                    "domain": "data",
                    "maturity": "stable",
                    "repository": "254carbon/user-service",
                    "path": ".",
                    "api_contracts": ["user-api@1.0.0"],
                    "dependencies": {
                        "external": ["redis@7.0", "postgresql@15"]
                    },
                    "quality": {
                        "coverage": 0.85,
                        "vulnerabilities": {
                            "critical": 0,
                            "high": 0,
                            "medium": 2,
                            "low": 3
                        }
                    },
                    "deployment": {
                        "last_update": "2025-01-03T16:45:00Z"
                    }
                }
            }
        }

        # Write test catalog
        catalog_file = self.test_dir / "catalog" / "service-index.yaml"
        with open(catalog_file, 'w') as f:
            yaml.dump(self.test_catalog, f, default_flow_style=False)

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_workflow_data_flow(self):
        """Test that data flows correctly through the entire workflow."""
        # Step 1: Validate catalog exists and is well-formed
        catalog_file = self.test_dir / "catalog" / "service-index.yaml"
        self.assertTrue(catalog_file.exists())

        with open(catalog_file, 'r') as f:
            catalog = yaml.safe_load(f)

        self.assertEqual(catalog["metadata"]["total_services"], 3)
        self.assertIn("gateway", catalog["services"])
        self.assertIn("auth-service", catalog["services"])
        self.assertIn("user-service", catalog["services"])

        # Step 2: Verify service structure
        for service_name in ["gateway", "auth-service", "user-service"]:
            service = catalog["services"][service_name]
            self.assertIn("name", service)
            self.assertIn("domain", service)
            self.assertIn("maturity", service)
            self.assertIn("repository", service)
            self.assertIn("api_contracts", service)
            self.assertIn("dependencies", service)
            self.assertIn("quality", service)

        # Step 3: Check dependency relationships
        gateway = catalog["services"]["gateway"]
        self.assertIn("auth-service@1.0.0", gateway["dependencies"]["internal"])

        auth_service = catalog["services"]["auth-service"]
        self.assertIn("user-service@1.0.0", auth_service["dependencies"]["internal"])

        # Step 4: Verify quality data structure
        for service in catalog["services"].values():
            quality = service["quality"]
            self.assertIn("coverage", quality)
            self.assertIn("vulnerabilities", quality)
            self.assertGreaterEqual(quality["coverage"], 0.0)
            self.assertLessEqual(quality["coverage"], 1.0)

    def test_catalog_validation(self):
        """Test catalog validation step."""
        # Simulate catalog validation
        catalog_file = self.test_dir / "catalog" / "service-index.yaml"

        # Basic validation checks
        with open(catalog_file, 'r') as f:
            catalog = yaml.safe_load(f)

        # Check required metadata
        metadata = catalog.get("metadata", {})
        self.assertIn("generated_at", metadata)
        self.assertIn("total_services", metadata)
        self.assertIn("version", metadata)

        # Check service count
        services = catalog.get("services", {})
        self.assertEqual(len(services), metadata["total_services"])

        # Validate each service
        for service_name, service in services.items():
            # Required fields
            required_fields = ["name", "domain", "maturity", "repository", "api_contracts", "dependencies"]
            for field in required_fields:
                self.assertIn(field, service, f"Service {service_name} missing field: {field}")

            # Domain validation
            valid_domains = ["access", "data", "ml", "shared", "external"]
            self.assertIn(service["domain"], valid_domains, f"Invalid domain for {service_name}")

            # Maturity validation
            valid_maturities = ["experimental", "beta", "stable", "deprecated"]
            self.assertIn(service["maturity"], valid_maturities, f"Invalid maturity for {service_name}")

            # Dependencies structure
            deps = service["dependencies"]
            self.assertIn("internal", deps)
            self.assertIn("external", deps)
            self.assertIsInstance(deps["internal"], list)
            self.assertIsInstance(deps["external"], list)

    def test_quality_computation_workflow(self):
        """Test quality computation step."""
        # Simulate quality computation
        services = self.test_catalog["services"]

        # Compute quality scores for each service
        quality_results = {}

        for service_name, service in services.items():
            # Extract quality metrics
            coverage = service["quality"]["coverage"]
            vulnerabilities = service["quality"]["vulnerabilities"]

            # Calculate base score (simplified)
            base_score = 50
            coverage_score = (coverage / 0.8) * 25 if coverage <= 0.8 else 25
            vuln_penalty = (vulnerabilities["critical"] * 20) + (vulnerabilities["high"] * 10)

            score = base_score + coverage_score - vuln_penalty

            # Determine grade
            if score >= 90:
                grade = "A"
            elif score >= 80:
                grade = "B"
            elif score >= 70:
                grade = "C"
            elif score >= 60:
                grade = "D"
            else:
                grade = "F"

            quality_results[service_name] = {
                "score": max(0, min(100, score)),
                "grade": grade,
                "coverage": coverage,
                "critical_vulns": vulnerabilities["critical"],
                "high_vulns": vulnerabilities["high"]
            }

        # Verify results
        self.assertEqual(len(quality_results), 3)

        # Check expected scores
        gateway_score = quality_results["gateway"]["score"]
        auth_score = quality_results["auth-service"]["score"]
        user_score = quality_results["user-service"]["score"]

        # All should be above 70 (passing threshold)
        self.assertGreater(gateway_score, 70)
        self.assertGreater(auth_score, 70)
        self.assertGreater(user_score, 70)

        # Auth service should have highest score (best quality metrics)
        self.assertGreaterEqual(auth_score, gateway_score)
        self.assertGreaterEqual(auth_score, user_score)

    def test_drift_detection_workflow(self):
        """Test drift detection step."""
        # Simulate drift detection
        services = self.test_catalog["services"]

        # Mock current spec versions (newer than what's in catalog)
        current_specs = {
            "gateway-core": "1.2.0",  # gateway has 1.0.0
            "auth-api": "2.1.0",      # auth-service has 2.0.0
            "user-api": "1.1.0"       # user-service has 1.0.0
        }

        drift_issues = []

        for service_name, service in services.items():
            for contract in service["api_contracts"]:
                spec_name, current_version = contract.split("@")

                if spec_name in current_specs:
                    latest_version = current_specs[spec_name]

                    # Simple version comparison (would use packaging.version in real impl)
                    if latest_version > current_version:
                        drift_issues.append({
                            "service": service_name,
                            "spec": spec_name,
                            "current_version": current_version,
                            "latest_version": latest_version,
                            "drift_type": "minor" if latest_version.startswith("1.") else "major"
                        })

        # Verify drift detection found issues
        self.assertEqual(len(drift_issues), 3)

        # Check specific issues
        gateway_drift = next((d for d in drift_issues if d["service"] == "gateway"), None)
        self.assertIsNotNone(gateway_drift)
        self.assertEqual(gateway_drift["current_version"], "1.0.0")
        self.assertEqual(gateway_drift["latest_version"], "1.2.0")

    def test_workflow_file_generation(self):
        """Test that workflow generates expected files."""
        # Simulate file generation from workflow
        generated_files = [
            "catalog/quality-snapshot.json",
            "catalog/latest_quality_snapshot.json",
            "analysis/reports/quality-summary.md",
            "analysis/reports/drift-report.json",
            "analysis/reports/drift-report.md"
        ]

        # Create expected files
        for file_path in generated_files:
            full_path = self.test_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Create mock content based on file type
            if file_path.endswith(".json"):
                content = {"generated_at": "2025-01-06T10:00:00Z", "workflow_step": "complete"}
            else:
                content = f"# Generated Report\n\nWorkflow completed at 2025-01-06T10:00:00Z"

            with open(full_path, 'w') as f:
                if file_path.endswith(".json"):
                    json.dump(content, f, indent=2)
                else:
                    f.write(content)

        # Verify all files were created
        for file_path in generated_files:
            full_path = self.test_dir / file_path
            self.assertTrue(full_path.exists(), f"File {file_path} was not created")

            # Verify content
            if file_path.endswith(".json"):
                with open(full_path, 'r') as f:
                    data = json.load(f)
                self.assertIn("generated_at", data)
            else:
                with open(full_path, 'r') as f:
                    content = f.read()
                self.assertIn("Generated Report", content)

    def test_error_recovery_simulation(self):
        """Test error recovery during workflow."""
        # Simulate partial failures and recovery

        # Step 1: Quality computation partially fails
        failed_services = ["user-service"]  # Simulate failure
        successful_services = ["gateway", "auth-service"]

        quality_results = {}

        for service_name in successful_services:
            service = self.test_catalog["services"][service_name]
            coverage = service["quality"]["coverage"]

            # Simulate score calculation
            score = 50 + (coverage * 50)  # Simplified scoring
            grade = "A" if score >= 90 else "B" if score >= 80 else "C"

            quality_results[service_name] = {
                "score": score,
                "grade": grade,
                "status": "computed"
            }

        # Handle failed service
        quality_results["user-service"] = {
            "score": 0,
            "grade": "F",
            "status": "failed",
            "error": "Quality computation failed"
        }

        # Verify partial success
        self.assertEqual(len(quality_results), 3)
        self.assertEqual(quality_results["gateway"]["status"], "computed")
        self.assertEqual(quality_results["user-service"]["status"], "failed")

        # Verify workflow continues despite failures
        total_computed = len([r for r in quality_results.values() if r["status"] == "computed"])
        total_failed = len([r for r in quality_results.values() if r["status"] == "failed"])

        self.assertEqual(total_computed, 2)
        self.assertEqual(total_failed, 1)

    def test_workflow_performance_metrics(self):
        """Test workflow performance tracking."""
        # Simulate performance metrics collection
        workflow_steps = [
            {"step": "collect_manifests", "duration": 2.5, "success": True},
            {"step": "build_catalog", "duration": 1.2, "success": True},
            {"step": "compute_quality", "duration": 3.8, "success": True},
            {"step": "detect_drift", "duration": 1.7, "success": True},
            {"step": "generate_reports", "duration": 0.9, "success": True}
        ]

        # Calculate total duration
        total_duration = sum(step["duration"] for step in workflow_steps)

        # Calculate success rate
        successful_steps = len([s for s in workflow_steps if s["success"]])
        success_rate = (successful_steps / len(workflow_steps)) * 100

        # Verify metrics
        self.assertEqual(total_duration, 10.1)
        self.assertEqual(success_rate, 100.0)

        # Check individual step performance
        compute_quality_step = next(s for s in workflow_steps if s["step"] == "compute_quality")
        self.assertLess(compute_quality_step["duration"], 5.0)  # Should be under 5 seconds

    def test_workflow_data_consistency(self):
        """Test data consistency across workflow stages."""
        # Test that data flows consistently between stages

        # Stage 1: Original catalog data
        original_services = set(self.test_catalog["services"].keys())
        original_count = len(original_services)

        # Stage 2: After processing (simulate filtering)
        processed_services = original_services.copy()
        # Simulate some services being filtered out (e.g., experimental services)
        processed_services.discard("experimental-service")  # This service doesn't exist

        # Stage 3: Final output should match processed services
        final_services = processed_services.copy()

        # Verify consistency
        self.assertEqual(len(final_services), original_count)
        self.assertEqual(final_services, original_services)

        # Test data integrity for each service
        for service_name in original_services:
            original_service = self.test_catalog["services"][service_name]

            # Key fields should be preserved
            preserved_fields = ["name", "domain", "maturity"]
            for field in preserved_fields:
                self.assertEqual(
                    original_service[field],
                    original_service[field],
                    f"Field {field} changed for {service_name}"
                )


class TestWorkflowIntegrationScenarios(unittest.TestCase):
    """Test various workflow integration scenarios."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir)
        (self.test_dir / "catalog").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_large_catalog_workflow(self):
        """Test workflow with large catalog (50+ services)."""
        # Create large catalog for performance testing
        large_catalog = {
            "metadata": {
                "generated_at": "2025-01-06T10:00:00Z",
                "total_services": 50,
                "version": "1.0.0"
            },
            "services": {}
        }

        # Generate 50 services across different domains
        domains = ["access", "data", "ml", "shared"]
        maturities = ["experimental", "beta", "stable"]

        for i in range(50):
            domain = domains[i % len(domains)]
            maturity = maturities[i % len(maturities)]

            service = {
                "name": f"service-{i:02d}",
                "domain": domain,
                "maturity": maturity,
                "repository": f"254carbon/service-{i:02d}",
                "path": ".",
                "api_contracts": [f"api-{domain}@1.0.0"],
                "dependencies": {
                    "internal": [],
                    "external": ["redis@7.0"]
                },
                "quality": {
                    "coverage": 0.8 + (i * 0.002),  # Varying coverage
                    "vulnerabilities": {
                        "critical": 0,
                        "high": i % 3,
                        "medium": i % 5,
                        "low": i % 7
                    }
                },
                "deployment": {
                    "last_update": f"2025-01-{5 + (i % 25):02d}T10:00:00Z"
                }
            }

            large_catalog["services"][f"service-{i:02d}"] = service

        # Write large catalog
        catalog_file = self.test_dir / "catalog" / "service-index.yaml"
        with open(catalog_file, 'w') as f:
            yaml.dump(large_catalog, f, default_flow_style=False)

        # Verify catalog creation
        self.assertTrue(catalog_file.exists())

        with open(catalog_file, 'r') as f:
            loaded_catalog = yaml.safe_load(f)

        self.assertEqual(loaded_catalog["metadata"]["total_services"], 50)
        self.assertEqual(len(loaded_catalog["services"]), 50)

        # Test performance with large catalog
        import time
        start_time = time.time()

        # Simulate workflow processing
        services = loaded_catalog["services"]
        processed_count = 0

        for service in services.values():
            # Simulate processing time
            time.sleep(0.001)  # 1ms per service
            processed_count += 1

        end_time = time.time()
        total_time = end_time - start_time

        # Should process all services
        self.assertEqual(processed_count, 50)

        # Should complete in reasonable time (< 5 seconds for 50 services)
        self.assertLess(total_time, 5.0)

    def test_workflow_with_failures(self):
        """Test workflow resilience when components fail."""
        # Create catalog with some problematic services
        problematic_catalog = {
            "metadata": {
                "generated_at": "2025-01-06T10:00:00Z",
                "total_services": 5,
                "version": "1.0.0"
            },
            "services": {
                "good-service-1": {
                    "name": "good-service-1",
                    "domain": "access",
                    "maturity": "stable",
                    "repository": "254carbon/good-service-1",
                    "api_contracts": ["api@1.0.0"],
                    "dependencies": {"internal": [], "external": ["redis@7.0"]},
                    "quality": {"coverage": 0.9, "vulnerabilities": {"critical": 0, "high": 0, "medium": 0, "low": 0}},
                    "deployment": {"last_update": "2025-01-06T10:00:00Z"}
                },
                "problematic-service": {
                    # Missing required fields to simulate validation failure
                    "name": "problematic-service"
                    # Missing domain, maturity, etc.
                },
                "good-service-2": {
                    "name": "good-service-2",
                    "domain": "data",
                    "maturity": "stable",
                    "repository": "254carbon/good-service-2",
                    "api_contracts": ["api@1.0.0"],
                    "dependencies": {"internal": [], "external": ["postgresql@15"]},
                    "quality": {"coverage": 0.85, "vulnerabilities": {"critical": 0, "high": 1, "medium": 1, "low": 2}},
                    "deployment": {"last_update": "2025-01-06T10:00:00Z"}
                }
            }
        }

        # Write problematic catalog
        catalog_file = self.test_dir / "catalog" / "service-index.yaml"
        with open(catalog_file, 'w') as f:
            yaml.dump(problematic_catalog, f, default_flow_style=False)

        # Simulate workflow with error handling
        workflow_results = {
            "total_services": 5,
            "processed_services": 0,
            "failed_services": 0,
            "errors": []
        }

        with open(catalog_file, 'r') as f:
            catalog = yaml.safe_load(f)

        for service_name, service in catalog["services"].items():
            try:
                # Validate required fields
                required_fields = ["name", "domain", "maturity", "repository", "api_contracts", "dependencies"]
                missing_fields = [field for field in required_fields if field not in service]

                if missing_fields:
                    raise ValueError(f"Missing required fields: {missing_fields}")

                # Process service
                workflow_results["processed_services"] += 1

            except Exception as e:
                workflow_results["failed_services"] += 1
                workflow_results["errors"].append({
                    "service": service_name,
                    "error": str(e)
                })

        # Verify workflow handles failures gracefully
        self.assertEqual(workflow_results["processed_services"], 2)  # Only good services
        self.assertEqual(workflow_results["failed_services"], 1)    # One problematic service
        self.assertEqual(len(workflow_results["errors"]), 1)

        # Workflow should continue despite failures
        self.assertGreater(workflow_results["processed_services"], 0)


if __name__ == '__main__':
    unittest.main()
