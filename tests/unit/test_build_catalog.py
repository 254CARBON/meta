#!/usr/bin/env python3
# Test Suite: Catalog Building
# Purpose: Validate manifest loading, catalog assembly, and schema/field checks
# Maintenance tips: Keep schema fixtures minimal; prefer mocking filesystem paths
"""
Unit tests for catalog building functionality.
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, mock_open

# Add the scripts directory to Python path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from build_catalog import CatalogBuilder


class TestCatalogBuilder:
    """Test cases for CatalogBuilder class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.manifests_dir = self.temp_dir / "manifests" / "collected"
        self.catalog_dir = self.temp_dir / "catalog"
        self.schemas_dir = self.temp_dir / "schemas"

        # Create directories
        self.manifests_dir.mkdir(parents=True)
        self.catalog_dir.mkdir(parents=True)
        self.schemas_dir.mkdir(parents=True)

        # Copy test files
        self._setup_test_files()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)

    def _setup_test_files(self):
        """Set up test manifest and schema files."""
        # Create a test manifest
        manifest_content = {
            "name": "test-service",
            "repo": "https://github.com/test/repo",
            "domain": "access",
            "version": "1.0.0",
            "maturity": "beta",
            "dependencies": {
                "internal": ["auth"],
                "external": ["redis"]
            }
        }

        manifest_file = self.manifests_dir / "test-service.yaml"
        import yaml
        with open(manifest_file, 'w') as f:
            yaml.dump(manifest_content, f)

        # Create schemas
        service_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "repo": {"type": "string"},
                "domain": {"type": "string"},
                "version": {"type": "string"},
                "maturity": {"type": "string"},
                "dependencies": {"type": "object"}
            },
            "required": ["name", "repo", "domain", "version", "maturity", "dependencies"]
        }

        catalog_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "metadata": {"type": "object"},
                "services": {"type": "array"}
            },
            "required": ["metadata", "services"]
        }

        with open(self.schemas_dir / "service-manifest.schema.json", 'w') as f:
            json.dump(service_schema, f)

        with open(self.schemas_dir / "service-index.schema.json", 'w') as f:
            json.dump(catalog_schema, f)

    def test_initialization(self):
        """Test CatalogBuilder initialization."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()

            assert builder.validate_only is False
            assert builder.force is False
            assert builder.catalog_dir == self.temp_dir / "catalog"

    def test_load_manifests(self):
        """Test loading manifests from directory."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()
            manifests = builder._load_manifests()

            assert len(manifests) == 1
            assert manifests[0]['name'] == 'test-service'

    def test_build_service_index(self):
        """Test building service index from manifests."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()
            manifests = builder._load_manifests()

            catalog = builder._build_service_index(manifests)

            assert 'metadata' in catalog
            assert 'services' in catalog
            assert len(catalog['services']) == 1
            assert catalog['services'][0]['name'] == 'test-service'
            assert catalog['services'][0]['status'] == 'active'

    def test_validate_manifest_success(self):
        """Test manifest validation with valid data."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()

            manifest = {
                "name": "test-service",
                "repo": "https://github.com/test/repo",
                "domain": "access",
                "version": "1.0.0",
                "maturity": "beta",
                "dependencies": {
                    "internal": ["auth"],
                    "external": ["redis"]
                }
            }

            # Should not raise an exception
            builder._validate_manifest(manifest, "test-service.yaml")

    def test_validate_manifest_failure(self):
        """Test manifest validation with invalid data."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()

            # Missing required field
            invalid_manifest = {
                "name": "test-service"
                # Missing other required fields
            }

            with pytest.raises(ValueError):
                builder._validate_manifest(invalid_manifest, "test-service.yaml")

    def test_check_duplicates(self):
        """Test duplicate service name detection."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()

            # Create manifests with duplicate names
            manifests = [
                {"name": "service1", "repo": "repo1", "domain": "access", "version": "1.0.0", "maturity": "beta", "dependencies": {"internal": [], "external": []}},
                {"name": "service1", "repo": "repo2", "domain": "access", "version": "1.0.0", "maturity": "beta", "dependencies": {"internal": [], "external": []}}
            ]

            with pytest.raises(ValueError, match="Duplicate service names"):
                builder._check_duplicates(manifests)

    def test_check_required_fields(self):
        """Test required fields validation."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()

            # Service missing required fields
            services = [
                {"name": "service1"}  # Missing other required fields
            ]

            with pytest.raises(ValueError, match="missing required fields"):
                builder._check_required_fields(services)

    def test_save_catalog(self):
        """Test saving catalog to files."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()

            catalog = {
                "metadata": {
                    "generated_at": "2025-10-05T22:30:12Z",
                    "version": "1.0.0",
                    "total_services": 1
                },
                "services": [
                    {
                        "name": "test-service",
                        "repo": "https://github.com/test/repo",
                        "domain": "access",
                        "version": "1.0.0",
                        "maturity": "beta",
                        "dependencies": {"internal": [], "external": []}
                    }
                ]
            }

            builder._save_catalog(catalog)

            # Check that files were created
            assert (self.catalog_dir / "service-index.yaml").exists()
            assert (self.catalog_dir / "service-index.json").exists()
            assert (self.catalog_dir / "catalog-summary.json").exists()

    def test_build_catalog_complete(self):
        """Test complete catalog building process."""
        with patch('build_catalog.Path') as mock_path:
            mock_path.return_value = self.temp_dir

            builder = CatalogBuilder()
            catalog = builder.build_catalog()

            assert 'metadata' in catalog
            assert 'services' in catalog
            assert len(catalog['services']) == 1
            assert catalog['services'][0]['name'] == 'test-service'

            # Check that catalog files were created
            assert (self.catalog_dir / "service-index.yaml").exists()
            assert (self.catalog_dir / "service-index.json").exists()
