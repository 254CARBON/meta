#!/usr/bin/env python3
"""
Unit tests for schema validation.
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path

# Add the scripts directory to Python path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


class TestSchemas:
    """Test cases for JSON schema validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.schemas_dir = self.temp_dir / "schemas"
        self.schemas_dir.mkdir(parents=True)

        # Copy schema files to temp directory
        self._setup_schemas()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)

    def _setup_schemas(self):
        """Set up schema files for testing."""
        # Service manifest schema
        service_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "name": {"type": "string", "pattern": "^[a-z][a-z0-9-]*[a-z0-9]$"},
                "repo": {"type": "string", "format": "uri"},
                "domain": {"type": "string", "enum": ["access", "data-processing", "ml", "infrastructure", "shared"]},
                "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
                "maturity": {"type": "string", "enum": ["experimental", "beta", "stable", "deprecated"]},
                "dependencies": {"type": "object"}
            },
            "required": ["name", "repo", "domain", "version", "maturity", "dependencies"]
        }

        # Service index schema
        index_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "metadata": {
                    "type": "object",
                    "properties": {
                        "generated_at": {"type": "string", "format": "date-time"},
                        "version": {"type": "string"},
                        "total_services": {"type": "integer", "minimum": 0}
                    },
                    "required": ["generated_at", "version", "total_services"]
                },
                "services": {"type": "array", "items": {"$ref": "#/definitions/service"}}
            },
            "required": ["metadata", "services"],
            "definitions": {
                "service": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "status": {"type": "string", "enum": ["active", "unknown", "error"]}
                    },
                    "required": ["name", "status"]
                }
            }
        }

        with open(self.schemas_dir / "service-manifest.schema.json", 'w') as f:
            json.dump(service_schema, f)

        with open(self.schemas_dir / "service-index.schema.json", 'w') as f:
            json.dump(index_schema, f)

    def test_service_manifest_schema_valid(self):
        """Test valid service manifest against schema."""
        import jsonschema

        # Load schema
        with open(self.schemas_dir / "service-manifest.schema.json") as f:
            schema = json.load(f)

        # Valid manifest
        valid_manifest = {
            "name": "gateway",
            "repo": "https://github.com/254carbon/254carbon-access",
            "domain": "access",
            "version": "1.1.0",
            "maturity": "stable",
            "dependencies": {
                "internal": ["auth"],
                "external": ["redis"]
            }
        }

        # Should not raise an exception
        jsonschema.validate(valid_manifest, schema)

    def test_service_manifest_schema_invalid(self):
        """Test invalid service manifest against schema."""
        import jsonschema

        # Load schema
        with open(self.schemas_dir / "service-manifest.schema.json") as f:
            schema = json.load(f)

        # Invalid manifest (missing required field)
        invalid_manifest = {
            "name": "gateway"
            # Missing required fields
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid_manifest, schema)

    def test_service_index_schema_valid(self):
        """Test valid service index against schema."""
        import jsonschema

        # Load schema
        with open(self.schemas_dir / "service-index.schema.json") as f:
            schema = json.load(f)

        # Valid catalog
        valid_catalog = {
            "metadata": {
                "generated_at": "2025-10-05T22:30:12Z",
                "version": "1.0.0",
                "total_services": 1
            },
            "services": [
                {
                    "name": "gateway",
                    "status": "active"
                }
            ]
        }

        # Should not raise an exception
        jsonschema.validate(valid_catalog, schema)

    def test_service_index_schema_invalid(self):
        """Test invalid service index against schema."""
        import jsonschema

        # Load schema
        with open(self.schemas_dir / "service-index.schema.json") as f:
            schema = json.load(f)

        # Invalid catalog (missing required field)
        invalid_catalog = {
            "metadata": {
                "generated_at": "2025-10-05T22:30:12Z"
                # Missing version and total_services
            }
            # Missing services
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid_catalog, schema)

    def test_schema_patterns(self):
        """Test regex patterns in schemas."""
        import jsonschema

        # Load schema
        with open(self.schemas_dir / "service-manifest.schema.json") as f:
            schema = json.load(f)

        # Test valid patterns
        valid_cases = [
            {"name": "gateway", "version": "1.0.0", "domain": "access", "maturity": "stable"},
            {"name": "test-service", "version": "2.1.3", "domain": "data-processing", "maturity": "beta"},
            {"name": "a", "version": "0.0.1", "domain": "shared", "maturity": "experimental"}
        ]

        for case in valid_cases:
            manifest = {
                "name": case["name"],
                "repo": "https://github.com/test/repo",
                "domain": case["domain"],
                "version": case["version"],
                "maturity": case["maturity"],
                "dependencies": {"internal": [], "external": []}
            }

            # Should not raise an exception
            jsonschema.validate(manifest, schema)

    def test_schema_patterns_invalid(self):
        """Test invalid regex patterns in schemas."""
        import jsonschema

        # Load schema
        with open(self.schemas_dir / "service-manifest.schema.json") as f:
            schema = json.load(f)

        # Test invalid patterns
        invalid_cases = [
            {"name": "Gateway", "version": "1.0.0", "domain": "access", "maturity": "stable"},  # Capital letter in name
            {"name": "gateway", "version": "1.0", "domain": "access", "maturity": "stable"},   # Invalid version format
            {"name": "gateway", "version": "1.0.0", "domain": "invalid", "maturity": "stable"}, # Invalid domain
            {"name": "gateway", "version": "1.0.0", "domain": "access", "maturity": "invalid"}  # Invalid maturity
        ]

        for case in invalid_cases:
            manifest = {
                "name": case["name"],
                "repo": "https://github.com/test/repo",
                "domain": case["domain"],
                "version": case["version"],
                "maturity": case["maturity"],
                "dependencies": {"internal": [], "external": []}
            }

            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(manifest, schema)
