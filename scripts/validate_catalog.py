#!/usr/bin/env python3
"""
254Carbon Meta Repository - Catalog Validation Script

Validates the service catalog for integrity and consistency.

Usage:
    python scripts/validate_catalog.py [--catalog-file FILE] [--strict]
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple
import jsonschema


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('catalog/validation.log')
    ]
)
logger = logging.getLogger(__name__)


class CatalogValidator:
    """Validates service catalog integrity and consistency."""

    def __init__(self, catalog_file: str = None, strict: bool = False):
        self.strict = strict
        self.schemas_dir = Path("schemas")

        # Determine catalog file path
        if catalog_file:
            self.catalog_path = Path(catalog_file)
        else:
            # Default locations to check
            yaml_path = Path("catalog/service-index.yaml")
            json_path = Path("catalog/service-index.json")

            if yaml_path.exists():
                self.catalog_path = yaml_path
            elif json_path.exists():
                self.catalog_path = json_path
            else:
                raise FileNotFoundError("No catalog file found. Run 'make build-catalog' first.")

        # Load schemas
        self.catalog_schema = self._load_schema("service-index.schema.json")
        self.manifest_schema = self._load_schema("service-manifest.schema.json")

        # Load catalog
        self.catalog = self._load_catalog()

    def _load_schema(self, schema_file: str) -> Dict[str, Any]:
        """Load JSON schema from file."""
        schema_path = self.schemas_dir / schema_file
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path) as f:
            return json.load(f)

    def _load_catalog(self) -> Dict[str, Any]:
        """Load catalog from file."""
        logger.info(f"Loading catalog from {self.catalog_path}")

        with open(self.catalog_path) as f:
            if self.catalog_path.suffix == '.yaml':
                return yaml.safe_load(f)
            else:
                return json.load(f)

    def validate_schema(self) -> bool:
        """Validate catalog against JSON schema."""
        logger.info("Validating catalog against schema...")

        try:
            jsonschema.validate(self.catalog, self.catalog_schema)
            logger.info("✓ Schema validation passed")
            return True
        except jsonschema.ValidationError as e:
            logger.error(f"✗ Schema validation failed: {e.message}")
            if self.strict:
                raise
            return False
        except jsonschema.SchemaError as e:
            logger.error(f"✗ Schema error: {e}")
            raise

    def validate_metadata(self) -> bool:
        """Validate catalog metadata."""
        logger.info("Validating metadata...")

        metadata = self.catalog.get('metadata', {})
        issues = []

        # Check required metadata fields
        required_fields = ['generated_at', 'version', 'total_services']
        for field in required_fields:
            if field not in metadata:
                issues.append(f"Missing metadata field: {field}")

        # Validate metadata field types
        if 'total_services' in metadata:
            total = metadata['total_services']
            if not isinstance(total, int) or total < 0:
                issues.append("total_services must be a non-negative integer")

        if 'version' in metadata:
            version = metadata['version']
            if not isinstance(version, str) or not version.replace('.', '').isdigit():
                issues.append("version must be a valid semver string")

        if 'generated_at' in metadata:
            generated_at = metadata['generated_at']
            if not isinstance(generated_at, str):
                issues.append("generated_at must be an ISO timestamp string")

        if issues:
            for issue in issues:
                logger.error(f"✗ Metadata issue: {issue}")
            return False

        logger.info("✓ Metadata validation passed")
        return True

    def validate_services(self) -> bool:
        """Validate individual services in catalog."""
        logger.info("Validating services...")

        services = self.catalog.get('services', [])
        if not services:
            logger.error("✗ No services found in catalog")
            return False

        # Basic service validations
        service_names = set()
        issues = []

        for i, service in enumerate(services):
            service_name = service.get('name', f'service_{i}')

            # Check for duplicate names
            if service_name in service_names:
                issues.append(f"Duplicate service name: {service_name}")
            service_names.add(service_name)

            # Check required fields
            required_fields = ['name', 'repo', 'domain', 'version', 'maturity', 'dependencies']
            for field in required_fields:
                if field not in service:
                    issues.append(f"Service {service_name} missing required field: {field}")

            # Validate field types and formats
            if 'name' in service and not isinstance(service['name'], str):
                issues.append(f"Service {service_name} name must be a string")

            if 'version' in service:
                version = service['version']
                if not isinstance(version, str) or not version.replace('.', '').isdigit():
                    issues.append(f"Service {service_name} version must be a valid semver string")

            if 'domain' in service:
                domain = service['domain']
                valid_domains = ['access', 'data-processing', 'ml', 'infrastructure', 'shared']
                if domain not in valid_domains:
                    issues.append(f"Service {service_name} domain must be one of: {valid_domains}")

            if 'maturity' in service:
                maturity = service['maturity']
                valid_maturities = ['experimental', 'beta', 'stable', 'deprecated']
                if maturity not in valid_maturities:
                    issues.append(f"Service {service_name} maturity must be one of: {valid_maturities}")

            # Validate dependencies structure
            if 'dependencies' in service:
                deps = service['dependencies']
                if not isinstance(deps, dict):
                    issues.append(f"Service {service_name} dependencies must be an object")
                else:
                    for dep_type in ['internal', 'external']:
                        if dep_type in deps and not isinstance(deps[dep_type], list):
                            issues.append(f"Service {service_name} {dep_type} dependencies must be a list")

        if issues:
            for issue in issues[:10]:  # Show first 10 issues
                logger.error(f"✗ Service issue: {issue}")
            if len(issues) > 10:
                logger.error(f"✗ ... and {len(issues) - 10} more issues")
            return False

        logger.info(f"✓ Services validation passed ({len(services)} services)")
        return True

    def validate_dependencies(self) -> bool:
        """Validate dependency relationships."""
        logger.info("Validating dependency relationships...")

        services = self.catalog.get('services', [])
        service_map = {s['name']: s for s in services}
        issues = []

        for service in services:
            service_name = service['name']
            dependencies = service.get('dependencies', {})

            # Check internal dependencies exist
            internal_deps = dependencies.get('internal', [])
            for dep in internal_deps:
                if dep not in service_map:
                    issues.append(f"Service {service_name} depends on unknown service: {dep}")

            # Check external dependencies format
            external_deps = dependencies.get('external', [])
            for dep in external_deps:
                if not isinstance(dep, str) or not dep.strip():
                    issues.append(f"Service {service_name} has invalid external dependency: {dep}")

        if issues:
            for issue in issues[:10]:  # Show first 10 issues
                logger.error(f"✗ Dependency issue: {issue}")
            if len(issues) > 10:
                logger.error(f"✗ ... and {len(issues) - 10} more issues")
            return False

        logger.info("✓ Dependency validation passed")
        return True

    def validate_domains(self) -> bool:
        """Validate domain consistency."""
        logger.info("Validating domain consistency...")

        services = self.catalog.get('services', [])
        domain_services = {}

        # Group services by domain
        for service in services:
            domain = service.get('domain')
            if domain not in domain_services:
                domain_services[domain] = []
            domain_services[domain].append(service['name'])

        # Check for potential issues
        issues = []

        # Warn about domains with too few services (might indicate misclassification)
        for domain, services_in_domain in domain_services.items():
            if len(services_in_domain) == 1:
                logger.warning(f"⚠ Domain '{domain}' has only one service: {services_in_domain[0]}")

        if not issues:
            logger.info("✓ Domain validation passed")
            return True

        for issue in issues:
            logger.error(f"✗ Domain issue: {issue}")
        return False

    def validate_completeness(self) -> bool:
        """Validate catalog completeness."""
        logger.info("Validating catalog completeness...")

        services = self.catalog.get('services', [])
        issues = []

        # Check for services missing optional but recommended fields
        recommended_fields = ['runtime', 'api_contracts', 'events_in', 'events_out', 'quality', 'security']

        for service in services:
            service_name = service['name']

            # Check for missing quality metrics (should be present for mature services)
            maturity = service.get('maturity')
            if maturity in ['stable', 'beta']:
                if 'quality' not in service:
                    logger.warning(f"⚠ Service {service_name} ({maturity}) missing quality metrics")

            # Check for missing runtime for certain domains
            domain = service.get('domain')
            if domain in ['data-processing', 'ml'] and 'runtime' not in service:
                logger.warning(f"⚠ Service {service_name} ({domain}) missing runtime specification")

        logger.info("✓ Completeness validation passed")
        return True

    def generate_report(self) -> Dict[str, Any]:
        """Generate validation report."""
        report = {
            "timestamp": self.catalog.get('metadata', {}).get('generated_at'),
            "catalog_file": str(self.catalog_path),
            "total_services": len(self.catalog.get('services', [])),
            "validations": {
                "schema": self.validate_schema(),
                "metadata": self.validate_metadata(),
                "services": self.validate_services(),
                "dependencies": self.validate_dependencies(),
                "domains": self.validate_domains(),
                "completeness": self.validate_completeness()
            }
        }

        # Overall result
        report["overall"] = all(report["validations"].values())

        return report

    def run_all_validations(self) -> bool:
        """Run all validation checks."""
        logger.info("Running comprehensive catalog validation...")

        validations = [
            ("Schema", self.validate_schema),
            ("Metadata", self.validate_metadata),
            ("Services", self.validate_services),
            ("Dependencies", self.validate_dependencies),
            ("Domains", self.validate_domains),
            ("Completeness", self.validate_completeness)
        ]

        results = []
        for name, validation_func in validations:
            try:
                result = validation_func()
                results.append((name, result))
            except Exception as e:
                logger.error(f"✗ {name} validation failed with exception: {e}")
                results.append((name, False))

        # Summary
        passed = sum(1 for _, result in results if result)
        total = len(results)

        logger.info(f"Validation complete: {passed}/{total} checks passed")

        if passed == total:
            logger.info("✓ All validations passed")
            return True
        else:
            logger.error(f"✗ {total - passed} validations failed")
            if self.strict:
                raise ValueError("Strict validation mode: failing validations found")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate service catalog integrity")
    parser.add_argument("--catalog-file", type=str, help="Path to catalog file (default: auto-detect)")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings and minor issues")
    parser.add_argument("--report", action="store_true", help="Generate detailed validation report")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        validator = CatalogValidator(args.catalog_file, args.strict)

        if args.report:
            report = validator.generate_report()
            print(json.dumps(report, indent=2))
        else:
            success = validator.run_all_validations()
            sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
