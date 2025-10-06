#!/usr/bin/env python3
"""
254Carbon Meta Repository - Catalog Building Script

Builds the unified service catalog from collected manifests and validates the
result against the JSON Schemas.

Usage:
    python scripts/build_catalog.py [--validate-only] [--force]

Overview:
- Loads YAML manifests from `manifests/collected/`, strips collection metadata,
  validates each manifest, checks required fields and duplicates, and assembles
  a deterministic, sorted catalog document.

Outputs:
- `catalog/service-index.yaml` (primary), JSON mirror, and a small summary JSON
  for fast UI/report consumption. Validation logs stored under `catalog/`.
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
import jsonschema


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/build.log')
    ]
)
logger = logging.getLogger(__name__)


class CatalogBuilder:
    """Builds and validates the unified service catalog."""

    def __init__(self, validate_only: bool = False, force: bool = False):
        self.validate_only = validate_only
        self.force = force
        self.manifests_dir = Path("manifests/collected")
        self.catalog_dir = Path("catalog")
        self.schemas_dir = Path("schemas")

        # Load schemas
        self.service_schema = self._load_schema("service-manifest.schema.json")
        self.catalog_schema = self._load_schema("service-index.schema.json")

    def _load_schema(self, schema_file: str) -> Dict[str, Any]:
        """Load JSON schema from file."""
        schema_path = self.schemas_dir / schema_file
        with open(schema_path) as f:
            return json.load(f)

    def _validate_manifest(self, manifest: Dict[str, Any], source_file: str) -> None:
        """Validate individual manifest against schema."""
        try:
            jsonschema.validate(manifest, self.service_schema)
            logger.debug(f"Validated manifest from {source_file}")
        except jsonschema.ValidationError as e:
            error_msg = f"Schema validation failed for {source_file}: {e.message}"
            if self.force:
                logger.warning(error_msg)
            else:
                raise ValueError(error_msg)
        except jsonschema.SchemaError as e:
            raise ValueError(f"Schema error in {schema_file}: {e}")

    def _load_manifests(self) -> List[Dict[str, Any]]:
        """Load all collected manifests."""
        manifests = []

        if not self.manifests_dir.exists():
            logger.error(f"Manifests directory does not exist: {self.manifests_dir}")
            return manifests

        # Look for YAML files (excluding collection summary)
        yaml_files = list(self.manifests_dir.glob("*.yaml"))
        yaml_files = [f for f in yaml_files if f.name != "collection-summary.json"]

        for manifest_file in yaml_files:
            try:
                logger.debug(f"Loading manifest from {manifest_file}")
                with open(manifest_file) as f:
                    manifest = yaml.safe_load(f)

                if manifest is None:
                    logger.warning(f"Empty or invalid YAML in {manifest_file}")
                    continue

                # Remove metadata added by collector
                manifest_copy = manifest.copy()
                manifest_copy.pop('_metadata', None)

                # Validate against schema
                self._validate_manifest(manifest_copy, manifest_file.name)

                manifests.append(manifest)

            except Exception as e:
                logger.error(f"Failed to load manifest from {manifest_file}: {e}")
                if not self.force:
                    raise

        logger.info(f"Loaded {len(manifests)} manifests")
        return manifests

    def _check_duplicates(self, manifests: List[Dict[str, Any]]) -> None:
        """Check for duplicate service names."""
        names = [m['name'] for m in manifests]
        duplicates = set([name for name in names if names.count(name) > 1])

        if duplicates:
            error_msg = f"Duplicate service names found: {duplicates}"
            if self.force:
                logger.warning(error_msg)
            else:
                raise ValueError(error_msg)

    def _build_service_index(self, manifests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build the service index from manifests."""
        services = []

        for manifest in manifests:
            # Remove metadata if present
            manifest_copy = manifest.copy()
            metadata = manifest_copy.pop('_metadata', {})

            # Add status field if not present
            if 'status' not in manifest_copy:
                manifest_copy['status'] = 'active'

            # Add last_update if we have metadata
            if metadata and 'collected_at' in metadata:
                manifest_copy['last_update'] = metadata['collected_at']

            services.append(manifest_copy)

        # Sort services by name for consistency
        services.sort(key=lambda x: x['name'])

        # Build catalog structure
        catalog = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version": "1.0.0",
                "total_services": len(services)
            },
            "services": services
        }

        return catalog

    def _validate_catalog(self, catalog: Dict[str, Any]) -> None:
        """Validate complete catalog against schema."""
        try:
            jsonschema.validate(catalog, self.catalog_schema)
            logger.info("Catalog schema validation passed")
        except jsonschema.ValidationError as e:
            error_msg = f"Catalog validation failed: {e.message}"
            if self.force:
                logger.warning(error_msg)
            else:
                raise ValueError(error_msg)

    def _check_required_fields(self, services: List[Dict[str, Any]]) -> None:
        """Check that all services have required fields."""
        required_fields = ['name', 'repo', 'domain', 'version', 'maturity', 'dependencies']

        for service in services:
            missing = [field for field in required_fields if field not in service]
            if missing:
                error_msg = f"Service {service.get('name', 'unknown')} missing required fields: {missing}"
                if self.force:
                    logger.warning(error_msg)
                else:
                    raise ValueError(error_msg)

    def _check_service_uniqueness(self, services: List[Dict[str, Any]]) -> None:
        """Check that service names are unique."""
        names = [s['name'] for s in services]
        duplicates = set([name for name in names if names.count(name) > 1])

        if duplicates:
            error_msg = f"Duplicate service names in catalog: {duplicates}"
            if self.force:
                logger.warning(error_msg)
            else:
                raise ValueError(error_msg)

    def build_catalog(self) -> Dict[str, Any]:
        """Main catalog building process."""
        logger.info("Starting catalog build process...")

        # Load manifests
        manifests = self._load_manifests()

        if not manifests:
            logger.warning("No manifests found to build catalog")
            return {}

        # Validate manifests
        logger.info("Validating manifests...")
        for manifest in manifests:
            manifest_copy = manifest.copy()
            manifest_copy.pop('_metadata', None)
            self._validate_manifest(manifest_copy, f"manifest for {manifest.get('name', 'unknown')}")

        # Build service index
        logger.info("Building service index...")
        catalog = self._build_service_index(manifests)

        # Additional validations
        logger.info("Running additional validations...")
        self._check_required_fields(catalog['services'])
        self._check_service_uniqueness(catalog['services'])

        # Schema validation
        logger.info("Validating complete catalog...")
        self._validate_catalog(catalog)

        # Save catalog if not validate-only mode
        if not self.validate_only:
            self._save_catalog(catalog)

        logger.info(f"Catalog build completed successfully with {len(catalog['services'])} services")
        return catalog

    def _save_catalog(self, catalog: Dict[str, Any]) -> None:
        """Save catalog to files."""
        # Ensure catalog directory exists
        self.catalog_dir.mkdir(exist_ok=True)

        # Save main catalog file
        catalog_file = self.catalog_dir / "service-index.yaml"
        with open(catalog_file, 'w') as f:
            yaml.dump(catalog, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved catalog to {catalog_file}")

        # Save JSON version for programmatic access
        json_file = self.catalog_dir / "service-index.json"
        with open(json_file, 'w') as f:
            json.dump(catalog, f, indent=2)

        logger.info(f"Saved JSON catalog to {json_file}")

        # Save summary metadata
        summary = {
            "generated_at": catalog["metadata"]["generated_at"],
            "total_services": catalog["metadata"]["total_services"],
            "service_names": [s["name"] for s in catalog["services"]],
            "domains": list(set(s["domain"] for s in catalog["services"])),
            "maturities": list(set(s["maturity"] for s in catalog["services"]))
        }

        summary_file = self.catalog_dir / "catalog-summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Saved summary to {summary_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Build service catalog from collected manifests")
    parser.add_argument("--validate-only", action="store_true", help="Only validate, don't save catalog")
    parser.add_argument("--force", action="store_true", help="Continue despite validation errors")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        builder = CatalogBuilder(args.validate_only, args.force)
        catalog = builder.build_catalog()

        if args.validate_only:
            logger.info("Validation completed successfully")
        else:
            logger.info("Catalog build completed successfully")

    except Exception as e:
        logger.error(f"Catalog build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
