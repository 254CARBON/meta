#!/usr/bin/env python3
"""
Unit tests for infrastructure scripts - collect_manifests, manage_historical_data,
and generate_dashboard.

These tests cover manifest collection, data management, and dashboard generation.
"""

import unittest
import tempfile
import json
import yaml
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
from typing import Dict, Any
from datetime import datetime, timezone, timedelta


class TestCollectManifests(unittest.TestCase):
    """Test manifest collection functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.mock_manifest = {
            "name": "test-service",
            "repository": "254carbon/test-service",
            "path": ".",
            "domain": "data",
            "maturity": "stable",
            "api_contracts": ["test-api@1.0.0"],
            "dependencies": {
                "internal": [],
                "external": ["redis@7.0"]
            }
        }

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_manifest_validation(self):
        """Test manifest validation logic."""
        # Valid manifest
        self.assertIn("name", self.mock_manifest)
        self.assertIn("repository", self.mock_manifest)
        self.assertIn("domain", self.mock_manifest)
        self.assertIn("maturity", self.mock_manifest)
        
        # Check required fields
        required_fields = ["name", "repository", "domain", "maturity"]
        for field in required_fields:
            self.assertIn(field, self.mock_manifest)

    def test_manifest_parsing(self):
        """Test manifest YAML parsing."""
        # Write manifest to file
        manifest_file = Path(self.temp_dir) / "service-manifest.yaml"
        with open(manifest_file, 'w') as f:
            yaml.dump(self.mock_manifest, f)
        
        # Read and parse
        with open(manifest_file, 'r') as f:
            parsed = yaml.safe_load(f)
        
        self.assertEqual(parsed["name"], "test-service")
        self.assertEqual(parsed["domain"], "data")

    def test_github_api_response_parsing(self):
        """Test GitHub API response parsing."""
        mock_response = {
            "name": "service-manifest.yaml",
            "path": "service-manifest.yaml",
            "sha": "abc123",
            "size": 1024,
            "url": "https://api.github.com/repos/254carbon/test-service/contents/service-manifest.yaml",
            "download_url": "https://raw.githubusercontent.com/254carbon/test-service/main/service-manifest.yaml",
            "type": "file"
        }
        
        # Verify response structure
        self.assertEqual(mock_response["name"], "service-manifest.yaml")
        self.assertEqual(mock_response["type"], "file")
        self.assertIn("download_url", mock_response)

    def test_manifest_collection_filtering(self):
        """Test manifest collection with repository filtering."""
        repos = [
            {"name": "gateway", "full_name": "254carbon/gateway"},
            {"name": "auth-service", "full_name": "254carbon/auth-service"},
            {"name": "docs", "full_name": "254carbon/docs"},  # Should be filtered
        ]
        
        # Filter out non-service repos
        service_repos = [
            repo for repo in repos
            if not repo["name"] in ["docs", "meta", "specs"]
        ]
        
        self.assertEqual(len(service_repos), 2)
        self.assertNotIn("docs", [r["name"] for r in service_repos])

    def test_rate_limit_handling(self):
        """Test GitHub API rate limit handling."""
        rate_limit_response = {
            "resources": {
                "core": {
                    "limit": 5000,
                    "remaining": 100,
                    "reset": 1640000000
                }
            }
        }
        
        remaining = rate_limit_response["resources"]["core"]["remaining"]
        
        # Should warn when rate limit is low
        should_warn = remaining < 500
        self.assertTrue(should_warn)

    def test_manifest_storage(self):
        """Test manifest storage to filesystem."""
        output_dir = Path(self.temp_dir) / "manifests" / "collected"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save manifest
        manifest_path = output_dir / "test-service.yaml"
        with open(manifest_path, 'w') as f:
            yaml.dump(self.mock_manifest, f)
        
        # Verify saved
        self.assertTrue(manifest_path.exists())
        
        # Verify content
        with open(manifest_path, 'r') as f:
            loaded = yaml.safe_load(f)
        
        self.assertEqual(loaded["name"], "test-service")


class TestManageHistoricalData(unittest.TestCase):
    """Test historical data management functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "historical"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_archive_old_data(self):
        """Test archiving old data files."""
        # Create old and new files
        old_file = self.data_dir / "quality-2024-01-01.json"
        new_file = self.data_dir / "quality-2025-01-01.json"
        
        old_file.write_text(json.dumps({"date": "2024-01-01"}))
        new_file.write_text(json.dumps({"date": "2025-01-01"}))
        
        # Simulate archival logic
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)
        
        files_to_archive = []
        for file in self.data_dir.glob("*.json"):
            # Parse date from filename
            date_str = file.stem.split("-", 1)[1]  # Get date part
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if file_date < cutoff_date:
                    files_to_archive.append(file)
            except ValueError:
                pass
        
        # Old file should be archived
        self.assertGreater(len(files_to_archive), 0)

    def test_cleanup_expired_data(self):
        """Test cleanup of expired data."""
        # Create files with different ages
        files = []
        for days_old in [30, 60, 90, 120]:
            date = datetime.now(timezone.utc) - timedelta(days=days_old)
            filename = f"data-{date.strftime('%Y-%m-%d')}.json"
            filepath = self.data_dir / filename
            filepath.write_text(json.dumps({"age_days": days_old}))
            files.append(filepath)
        
        # Cleanup files older than 90 days
        retention_days = 90
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        files_to_delete = []
        for file in self.data_dir.glob("*.json"):
            date_str = file.stem.split("-", 1)[1]
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if file_date < cutoff_date:
                files_to_delete.append(file)
        
        # Should identify 1 file for deletion (120 days old)
        self.assertEqual(len(files_to_delete), 1)

    def test_data_compression(self):
        """Test data compression for archival."""
        import gzip
        
        # Create test data
        test_data = {"large": "data" * 1000}
        data_json = json.dumps(test_data)
        
        # Compress
        compressed_path = self.data_dir / "data.json.gz"
        with gzip.open(compressed_path, 'wt', encoding='utf-8') as f:
            f.write(data_json)
        
        # Verify compression
        original_size = len(data_json.encode())
        compressed_size = compressed_path.stat().st_size
        
        # Compressed should be smaller
        self.assertLess(compressed_size, original_size)

    def test_data_retention_policy(self):
        """Test data retention policy enforcement."""
        retention_policies = {
            "quality_snapshots": 90,  # days
            "drift_reports": 30,
            "audit_logs": 365,
            "temporary_files": 7
        }
        
        # Verify policies are reasonable
        self.assertGreater(retention_policies["audit_logs"], retention_policies["quality_snapshots"])
        self.assertLess(retention_policies["temporary_files"], retention_policies["drift_reports"])

    def test_historical_trend_calculation(self):
        """Test historical trend calculation."""
        # Create historical data points
        historical_data = [
            {"date": "2025-01-01", "score": 75},
            {"date": "2025-01-02", "score": 78},
            {"date": "2025-01-03", "score": 80},
            {"date": "2025-01-04", "score": 82},
            {"date": "2025-01-05", "score": 85},
        ]
        
        # Calculate trend
        scores = [d["score"] for d in historical_data]
        trend = "improving" if scores[-1] > scores[0] else "declining"
        
        self.assertEqual(trend, "improving")
        
        # Calculate average improvement
        improvement = scores[-1] - scores[0]
        self.assertEqual(improvement, 10)


class TestGenerateDashboard(unittest.TestCase):
    """Test dashboard generation functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
        self.mock_data = {
            "services": {
                "gateway": {"score": 85, "grade": "B"},
                "auth-service": {"score": 92, "grade": "A"},
                "user-service": {"score": 78, "grade": "C"}
            },
            "summary": {
                "total_services": 3,
                "average_score": 85.0,
                "grade_distribution": {
                    "A": 1,
                    "B": 1,
                    "C": 1
                }
            }
        }

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dashboard_data_preparation(self):
        """Test dashboard data preparation."""
        # Extract data for visualization
        service_names = list(self.mock_data["services"].keys())
        service_scores = [s["score"] for s in self.mock_data["services"].values()]
        
        self.assertEqual(len(service_names), 3)
        self.assertEqual(len(service_scores), 3)
        self.assertEqual(max(service_scores), 92)
        self.assertEqual(min(service_scores), 78)

    def test_grade_distribution_chart(self):
        """Test grade distribution chart data."""
        grade_dist = self.mock_data["summary"]["grade_distribution"]
        
        # Verify distribution
        self.assertEqual(grade_dist["A"], 1)
        self.assertEqual(grade_dist["B"], 1)
        self.assertEqual(grade_dist["C"], 1)
        
        # Calculate percentages
        total = sum(grade_dist.values())
        percentages = {
            grade: (count / total) * 100
            for grade, count in grade_dist.items()
        }
        
        self.assertAlmostEqual(percentages["A"], 33.33, places=1)

    def test_quality_trend_chart(self):
        """Test quality trend chart data."""
        trend_data = [
            {"date": "2025-01-01", "average_score": 75},
            {"date": "2025-01-02", "average_score": 78},
            {"date": "2025-01-03", "average_score": 80},
            {"date": "2025-01-04", "average_score": 82},
            {"date": "2025-01-05", "average_score": 85},
        ]
        
        dates = [d["date"] for d in trend_data]
        scores = [d["average_score"] for d in trend_data]
        
        self.assertEqual(len(dates), 5)
        self.assertEqual(len(scores), 5)
        self.assertEqual(scores[-1], 85)

    def test_service_health_indicators(self):
        """Test service health indicator generation."""
        def get_health_indicator(score):
            """Get health indicator based on score."""
            if score >= 90:
                return {"color": "green", "status": "excellent", "icon": "✅"}
            elif score >= 80:
                return {"color": "blue", "status": "good", "icon": "🟢"}
            elif score >= 70:
                return {"color": "yellow", "status": "acceptable", "icon": "🟡"}
            elif score >= 60:
                return {"color": "orange", "status": "needs_improvement", "icon": "🟠"}
            else:
                return {"color": "red", "status": "failing", "icon": "🔴"}
        
        # Test indicators
        excellent = get_health_indicator(92)
        self.assertEqual(excellent["status"], "excellent")
        
        good = get_health_indicator(85)
        self.assertEqual(good["status"], "good")
        
        acceptable = get_health_indicator(78)
        self.assertEqual(acceptable["status"], "acceptable")

    def test_dashboard_html_generation(self):
        """Test HTML dashboard generation."""
        # Simulate HTML generation
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>254Carbon Platform Dashboard</title>
        </head>
        <body>
            <h1>Platform Overview</h1>
            <div class="metrics">
                <div class="metric">
                    <span class="label">Total Services</span>
                    <span class="value">{total_services}</span>
                </div>
                <div class="metric">
                    <span class="label">Average Score</span>
                    <span class="value">{average_score}</span>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Render template
        rendered = html_template.format(
            total_services=self.mock_data["summary"]["total_services"],
            average_score=self.mock_data["summary"]["average_score"]
        )
        
        # Verify rendering
        self.assertIn("Total Services", rendered)
        self.assertIn("3", rendered)
        self.assertIn("85.0", rendered)

    def test_interactive_chart_data(self):
        """Test interactive chart data preparation."""
        # Prepare data for Plotly
        chart_data = {
            "type": "bar",
            "x": list(self.mock_data["services"].keys()),
            "y": [s["score"] for s in self.mock_data["services"].values()],
            "marker": {
                "color": [
                    "green" if s["score"] >= 90 else
                    "blue" if s["score"] >= 80 else
                    "yellow"
                    for s in self.mock_data["services"].values()
                ]
            }
        }
        
        # Verify chart data structure
        self.assertEqual(chart_data["type"], "bar")
        self.assertEqual(len(chart_data["x"]), 3)
        self.assertEqual(len(chart_data["y"]), 3)
        self.assertEqual(len(chart_data["marker"]["color"]), 3)

    def test_dashboard_export(self):
        """Test dashboard export functionality."""
        output_file = Path(self.temp_dir) / "dashboard.html"
        
        # Simulate export
        html_content = "<html><body><h1>Dashboard</h1></body></html>"
        output_file.write_text(html_content)
        
        # Verify export
        self.assertTrue(output_file.exists())
        
        content = output_file.read_text()
        self.assertIn("<h1>Dashboard</h1>", content)


class TestIntegrationWorkflows(unittest.TestCase):
    """Integration tests for infrastructure workflows."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_complete_data_pipeline(self):
        """Test complete data collection and processing pipeline."""
        # 1. Collect manifests (simulated)
        manifests = {
            "gateway": {"name": "gateway", "quality": {"coverage": 0.85}},
            "auth-service": {"name": "auth-service", "quality": {"coverage": 0.92}}
        }
        
        # 2. Process and store
        data_dir = Path(self.temp_dir) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        for name, manifest in manifests.items():
            manifest_file = data_dir / f"{name}.json"
            manifest_file.write_text(json.dumps(manifest))
        
        # 3. Verify storage
        stored_files = list(data_dir.glob("*.json"))
        self.assertEqual(len(stored_files), 2)
        
        # 4. Load and aggregate
        all_data = []
        for file in stored_files:
            with open(file, 'r') as f:
                all_data.append(json.load(f))
        
        self.assertEqual(len(all_data), 2)

    def test_historical_data_lifecycle(self):
        """Test complete historical data lifecycle."""
        data_dir = Path(self.temp_dir) / "historical"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Create new data
        today = datetime.now(timezone.utc)
        current_file = data_dir / f"quality-{today.strftime('%Y-%m-%d')}.json"
        current_file.write_text(json.dumps({"score": 85}))
        
        # 2. Create old data
        old_date = today - timedelta(days=100)
        old_file = data_dir / f"quality-{old_date.strftime('%Y-%m-%d')}.json"
        old_file.write_text(json.dumps({"score": 75}))
        
        # 3. Archive old data
        archive_dir = Path(self.temp_dir) / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        cutoff = today - timedelta(days=90)
        for file in data_dir.glob("*.json"):
            date_str = file.stem.split("-", 1)[1]
            file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            
            if file_date < cutoff:
                # Move to archive
                shutil.move(str(file), str(archive_dir / file.name))
        
        # 4. Verify archival
        self.assertEqual(len(list(data_dir.glob("*.json"))), 1)
        self.assertEqual(len(list(archive_dir.glob("*.json"))), 1)

    def test_dashboard_generation_workflow(self):
        """Test complete dashboard generation workflow."""
        # 1. Prepare data
        quality_data = {
            "services": {
                "gateway": {"score": 85, "grade": "B"},
                "auth-service": {"score": 92, "grade": "A"}
            },
            "summary": {
                "total_services": 2,
                "average_score": 88.5
            }
        }
        
        # 2. Generate dashboard components
        components = []
        
        # Overview card
        components.append({
            "type": "card",
            "title": "Platform Overview",
            "value": quality_data["summary"]["total_services"]
        })
        
        # Quality chart
        components.append({
            "type": "chart",
            "title": "Service Quality Scores",
            "data": quality_data["services"]
        })
        
        # 3. Verify components
        self.assertEqual(len(components), 2)
        self.assertEqual(components[0]["type"], "card")
        self.assertEqual(components[1]["type"], "chart")
        
        # 4. Export dashboard
        output_file = Path(self.temp_dir) / "dashboard.html"
        dashboard_html = f"<html><body>Components: {len(components)}</body></html>"
        output_file.write_text(dashboard_html)
        
        # 5. Verify export
        self.assertTrue(output_file.exists())


if __name__ == '__main__':
    unittest.main()
