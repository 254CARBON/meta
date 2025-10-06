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
import hashlib
import concurrent.futures
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple
import jsonschema

from scripts.utils import monitor_execution, audit_logger, redis_client


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
    """Builds and validates the unified service catalog with performance optimizations."""

    def __init__(self, validate_only: bool = False, force: bool = False, incremental: bool = True, max_workers: int = 4):
        self.validate_only = validate_only
        self.force = force
        self.incremental = incremental
        self.max_workers = max_workers
        self.manifests_dir = Path("manifests/collected")
        self.catalog_dir = Path("catalog")
        self.schemas_dir = Path("schemas")
        self.cache_dir = Path("cache_fallback")

        # Performance tracking
        self.build_stats = {
            'start_time': None,
            'end_time': None,
            'total_services': 0,
            'cached_services': 0,
            'processed_services': 0,
            'validation_time': 0,
            'build_time': 0
        }

        # Load schemas
        self.service_schema = self._load_schema("service-manifest.schema.json")
        self.catalog_schema = self._load_schema("service-index.schema.json")

        # Initialize cache directory
        self.cache_dir.mkdir(exist_ok=True)

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

    def _get_manifest_hash(self, manifest_file: Path) -> str:
        """Get hash of manifest file for change detection."""
        try:
            with open(manifest_file, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""

    def _get_cached_manifest(self, manifest_file: Path) -> Optional[Dict[str, Any]]:
        """Get cached manifest if unchanged."""
        if not self.incremental:
            return None
        
        try:
            current_hash = self._get_manifest_hash(manifest_file)
            cache_file = self.cache_dir / f"{manifest_file.stem}.cache"
            
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                
                if cache_data.get('hash') == current_hash:
                    logger.debug(f"Using cached manifest: {manifest_file.name}")
                    return cache_data.get('manifest')
            
            return None
        except Exception as e:
            logger.debug(f"Cache miss for {manifest_file.name}: {e}")
            return None

    def _cache_manifest(self, manifest_file: Path, manifest: Dict[str, Any]):
        """Cache manifest for future incremental builds."""
        if not self.incremental:
            return
        
        try:
            current_hash = self._get_manifest_hash(manifest_file)
            cache_file = self.cache_dir / f"{manifest_file.stem}.cache"
            
            cache_data = {
                'hash': current_hash,
                'manifest': manifest,
                'cached_at': datetime.now(timezone.utc).isoformat()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
                
        except Exception as e:
            logger.debug(f"Failed to cache manifest {manifest_file.name}: {e}")

    def _load_single_manifest(self, manifest_file: Path) -> Optional[Dict[str, Any]]:
        """Load a single manifest file with caching."""
        try:
            # Try cache first
            cached_manifest = self._get_cached_manifest(manifest_file)
            if cached_manifest:
                self.build_stats['cached_services'] += 1
                return cached_manifest

            logger.debug(f"Loading manifest from {manifest_file}")
            with open(manifest_file) as f:
                manifest = yaml.safe_load(f)

            if manifest is None:
                logger.warning(f"Empty or invalid YAML in {manifest_file}")
                return None

            # Remove metadata added by collector
            manifest_copy = manifest.copy()
            manifest_copy.pop('_metadata', None)

            # Validate against schema
            self._validate_manifest(manifest_copy, manifest_file.name)

            # Cache the manifest
            self._cache_manifest(manifest_file, manifest)

            self.build_stats['processed_services'] += 1
            return manifest

        except Exception as e:
            logger.error(f"Failed to load manifest from {manifest_file}: {e}")
            if not self.force:
                raise
            return None

    def _load_manifests(self) -> List[Dict[str, Any]]:
        """Load all collected manifests with parallel processing and caching."""
        manifests = []

        if not self.manifests_dir.exists():
            logger.error(f"Manifests directory does not exist: {self.manifests_dir}")
            return manifests

        # Look for YAML files (excluding collection summary)
        yaml_files = list(self.manifests_dir.glob("*.yaml"))
        yaml_files = [f for f in yaml_files if f.name != "collection-summary.json"]

        if not yaml_files:
            logger.warning("No manifest files found")
            return manifests

        logger.info(f"Found {len(yaml_files)} manifest files")

        # Load manifests in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(self._load_single_manifest, f): f 
                for f in yaml_files
            }
            
            for future in concurrent.futures.as_completed(future_to_file):
                manifest_file = future_to_file[future]
                try:
                    manifest = future.result()
                    if manifest:
                        manifests.append(manifest)
                except Exception as e:
                    logger.error(f"Error processing {manifest_file}: {e}")
                    if not self.force:
                        raise

        logger.info(f"Loaded {len(manifests)} manifests ({self.build_stats['cached_services']} cached, {self.build_stats['processed_services']} processed)")
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

    def _validate_manifests_parallel(self, manifests: List[Dict[str, Any]]) -> None:
        """Validate manifests in parallel."""
        def validate_single(manifest: Dict[str, Any]) -> bool:
            try:
                manifest_copy = manifest.copy()
                manifest_copy.pop('_metadata', None)
                self._validate_manifest(manifest_copy, f"manifest for {manifest.get('name', 'unknown')}")
                return True
            except Exception as e:
                logger.error(f"Validation failed for {manifest.get('name', 'unknown')}: {e}")
                if not self.force:
                    raise
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(validate_single, manifest) for manifest in manifests]
            concurrent.futures.wait(futures)

    def _build_catalog_incremental(self, manifests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build catalog with incremental updates."""
        try:
            # Try to load existing catalog
            existing_catalog_file = self.catalog_dir / "service-index.yaml"
            if existing_catalog_file.exists() and self.incremental:
                with open(existing_catalog_file, 'r') as f:
                    existing_catalog = yaml.safe_load(f)
                
                # Build map of existing services
                existing_services = {s['name']: s for s in existing_catalog.get('services', [])}
                
                # Update only changed services
                updated_services = []
                for manifest in manifests:
                    service_name = manifest.get('name')
                    if service_name in existing_services:
                        # Check if service has changed
                        existing_service = existing_services[service_name]
                        if self._service_changed(existing_service, manifest):
                            updated_services.append(manifest)
                        else:
                            updated_services.append(existing_service)
                    else:
                        updated_services.append(manifest)
                
                # Add any services that exist in catalog but not in manifests
                manifest_names = {m.get('name') for m in manifests}
                for service_name, service in existing_services.items():
                    if service_name not in manifest_names:
                        updated_services.append(service)
                
                manifests = updated_services
                logger.info(f"Incremental build: {len(updated_services)} services (including unchanged)")
        except Exception as e:
            logger.warning(f"Incremental build failed, falling back to full build: {e}")
        
        return self._build_service_index(manifests)

    def _service_changed(self, existing_service: Dict[str, Any], new_manifest: Dict[str, Any]) -> bool:
        """Check if a service has changed."""
        try:
            # Compare key fields
            key_fields = ['version', 'domain', 'maturity', 'dependencies', 'status']
            for field in key_fields:
                if existing_service.get(field) != new_manifest.get(field):
                    return True
            return False
        except Exception:
            return True

    @monitor_execution("catalog-build")
    def build_catalog(self) -> Dict[str, Any]:
        """Main catalog building process with performance optimizations."""
        self.build_stats['start_time'] = datetime.now(timezone.utc)
        logger.info("Starting optimized catalog build process...")

        # Try to load cached catalog first
        cached_catalog = redis_client.get("catalog", fallback_to_file=True)
        if cached_catalog and not self.force:
            logger.info("Using cached catalog")
            return cached_catalog

        # Load manifests with parallel processing and caching
        logger.info("Loading manifests...")
        manifests = self._load_manifests()

        if not manifests:
            logger.warning("No manifests found to build catalog")
            # Return cached catalog if available
            if cached_catalog:
                logger.info("Returning cached catalog as fallback")
                return cached_catalog
            return {}

        self.build_stats['total_services'] = len(manifests)

        # Validate manifests in parallel
        logger.info("Validating manifests...")
        validation_start = datetime.now(timezone.utc)
        self._validate_manifests_parallel(manifests)
        self.build_stats['validation_time'] = (datetime.now(timezone.utc) - validation_start).total_seconds()

        # Build service index with incremental updates
        logger.info("Building service index...")
        build_start = datetime.now(timezone.utc)
        catalog = self._build_catalog_incremental(manifests)
        self.build_stats['build_time'] = (datetime.now(timezone.utc) - build_start).total_seconds()

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
            # Cache the catalog
            redis_client.set("catalog", catalog, ttl=3600, fallback_to_file=True)

        self.build_stats['end_time'] = datetime.now(timezone.utc)
        total_time = (self.build_stats['end_time'] - self.build_stats['start_time']).total_seconds()

        logger.info(f"Catalog build completed successfully with {len(catalog['services'])} services")
        logger.info(f"Performance stats: {self.build_stats['cached_services']} cached, "
                   f"{self.build_stats['processed_services']} processed, "
                   f"{total_time:.2f}s total, {self.build_stats['validation_time']:.2f}s validation, "
                   f"{self.build_stats['build_time']:.2f}s build")
        
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

        # Log catalog update
        audit_logger.log_action(
            user="system",
            action="catalog_update",
            resource="service_catalog",
            resource_type="catalog",
            details={
                "total_services": catalog["metadata"]["total_services"],
                "generated_at": catalog["metadata"]["generated_at"],
                "catalog_file": str(catalog_file),
                "json_file": str(json_file)
            },
            category=audit_logger.AuditCategory.DATA_MODIFICATION
        )

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
    parser.add_argument("--no-incremental", action="store_true", help="Disable incremental builds")
    parser.add_argument("--max-workers", type=int, default=4, help="Maximum parallel workers")
    parser.add_argument("--benchmark", action="store_true", help="Run performance benchmark")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        builder = CatalogBuilder(
            validate_only=args.validate_only,
            force=args.force,
            incremental=not args.no_incremental,
            max_workers=args.max_workers
        )
        
        if args.benchmark:
            # Run benchmark
            import time
            start_time = time.time()
            catalog = builder.build_catalog()
            end_time = time.time()
            
            print(f"\nBenchmark Results:")
            print(f"Total time: {end_time - start_time:.2f}s")
            print(f"Services processed: {builder.build_stats['total_services']}")
            print(f"Cached services: {builder.build_stats['cached_services']}")
            print(f"Newly processed: {builder.build_stats['processed_services']}")
            print(f"Validation time: {builder.build_stats['validation_time']:.2f}s")
            print(f"Build time: {builder.build_stats['build_time']:.2f}s")
            print(f"Services per second: {builder.build_stats['total_services'] / (end_time - start_time):.2f}")
        else:
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
