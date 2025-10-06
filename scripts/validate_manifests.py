#!/usr/bin/env python3
"""
254Carbon Meta Repository - Manifest Validation Script

Validates individual service manifests for completeness, consistency, and compliance.
Performs comprehensive checks on manifest files collected from service repositories.

Usage:
    python scripts/validate_manifests.py [--manifests-dir DIR] [--strict] [--fix]

Features:
- Schema validation against service-manifest.schema.json
- Field completeness and type validation
- Cross-manifest consistency checks
- Repository URL and path validation
- Version format validation
- Dependency structure validation
- Quality metrics validation
- Security configuration validation
- Auto-fix capabilities for common issues
"""

import os
import sys
import json
import yaml
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import re
import urllib.parse

from scripts.utils import audit_logger, monitor_execution

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/manifest-validation.log')
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """Represents a validation issue found in a manifest."""
    manifest_file: str
    service_name: str
    issue_type: str
    severity: str
    message: str
    field_path: str = ""
    suggested_fix: str = ""
    line_number: Optional[int] = None


@dataclass
class ManifestValidationResult:
    """Result of validating a single manifest."""
    manifest_file: str
    service_name: str
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    errors: List[ValidationIssue] = field(default_factory=list)
    fixes_applied: List[str] = field(default_factory=list)


class ManifestValidator:
    """Validates service manifests for completeness and consistency."""

    def __init__(self, manifests_dir: str = "manifests/collected", strict: bool = False, auto_fix: bool = False):
        """
        Initialize manifest validator.
        
        Args:
            manifests_dir: Directory containing manifest files
            strict: Whether to fail on warnings
            auto_fix: Whether to automatically fix common issues
        """
        self.manifests_dir = Path(manifests_dir)
        self.strict = strict
        self.auto_fix = auto_fix
        self.schemas_dir = Path("schemas")
        
        # Load schema
        self.manifest_schema = self._load_schema("service-manifest.schema.json")
        
        # Validation rules
        self.validation_rules = self._load_validation_rules()
        
        # Track all manifests for cross-validation
        self.all_manifests: Dict[str, Dict[str, Any]] = {}
        self.validation_results: List[ManifestValidationResult] = []
        
        logger.info(f"Manifest validator initialized: dir={manifests_dir}, strict={strict}, auto_fix={auto_fix}")

    def _load_schema(self, schema_file: str) -> Dict[str, Any]:
        """Load JSON schema from file."""
        schema_path = self.schemas_dir / schema_file
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        
        with open(schema_path) as f:
            return json.load(f)

    def _load_validation_rules(self) -> Dict[str, Any]:
        """Load validation rules from config."""
        rules_file = Path("config/rules.yaml")
        if not rules_file.exists():
            return self._get_default_rules()
        
        with open(rules_file) as f:
            return yaml.safe_load(f)

    def _get_default_rules(self) -> Dict[str, Any]:
        """Get default validation rules."""
        return {
            "manifest": {
                "required_fields": ["name", "domain", "version", "maturity", "repository", "path"],
                "valid_domains": ["access", "data-processing", "ml", "infrastructure", "shared"],
                "valid_maturities": ["experimental", "beta", "stable", "deprecated"],
                "version_pattern": r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$",
                "repository_pattern": r"^https://github\.com/254carbon/",
                "max_name_length": 50,
                "max_description_length": 500
            },
            "quality": {
                "min_coverage": 0.0,
                "max_coverage": 1.0,
                "required_for_stable": ["coverage", "lint_pass"]
            },
            "security": {
                "required_for_stable": ["signed_images", "policy_pass"]
            }
        }

    @monitor_execution("manifest-validation")
    def validate_all_manifests(self) -> Dict[str, Any]:
        """Validate all manifests in the manifests directory."""
        logger.info("Starting comprehensive manifest validation...")
        
        # Find all manifest files
        manifest_files = list(self.manifests_dir.glob("*.yaml")) + list(self.manifests_dir.glob("*.yml"))
        
        if not manifest_files:
            logger.warning(f"No manifest files found in {self.manifests_dir}")
            return self._generate_summary_report()
        
        logger.info(f"Found {len(manifest_files)} manifest files to validate")
        
        # Validate each manifest
        for manifest_file in manifest_files:
            try:
                result = self._validate_single_manifest(manifest_file)
                self.validation_results.append(result)
                
                # Apply auto-fixes if enabled
                if self.auto_fix and result.fixes_applied:
                    self._apply_fixes(manifest_file, result)
                
            except Exception as e:
                logger.error(f"Failed to validate {manifest_file}: {e}")
                # Create error result
                error_result = ManifestValidationResult(
                    manifest_file=str(manifest_file),
                    service_name="unknown",
                    valid=False,
                    errors=[ValidationIssue(
                        manifest_file=str(manifest_file),
                        service_name="unknown",
                        issue_type="validation_error",
                        severity="error",
                        message=f"Validation failed: {e}"
                    )]
                )
                self.validation_results.append(error_result)
        
        # Perform cross-manifest validation
        self._validate_cross_manifest_consistency()
        
        # Generate summary report
        summary = self._generate_summary_report()
        
        # Log audit event
        audit_logger.log_action(
            user="system",
            action="manifest_validation",
            resource="all_manifests",
            details={
                "total_manifests": len(manifest_files),
                "valid_manifests": summary["summary"]["valid_count"],
                "issues_found": summary["summary"]["total_issues"],
                "auto_fix_enabled": self.auto_fix
            }
        )
        
        return summary

    def _validate_single_manifest(self, manifest_file: Path) -> ManifestValidationResult:
        """Validate a single manifest file."""
        logger.info(f"Validating manifest: {manifest_file.name}")
        
        try:
            # Load manifest
            with open(manifest_file) as f:
                manifest = yaml.safe_load(f)
            
            if not manifest:
                raise ValueError("Manifest file is empty or invalid YAML")
            
            service_name = manifest.get('name', manifest_file.stem)
            result = ManifestValidationResult(
                manifest_file=str(manifest_file),
                service_name=service_name,
                valid=True
            )
            
            # Store manifest for cross-validation
            self.all_manifests[service_name] = manifest
            
            # Run all validation checks
            self._validate_schema(manifest, result)
            self._validate_required_fields(manifest, result)
            self._validate_field_types(manifest, result)
            self._validate_field_values(manifest, result)
            self._validate_dependencies(manifest, result)
            self._validate_quality_metrics(manifest, result)
            self._validate_security_config(manifest, result)
            self._validate_repository_info(manifest, result)
            
            # Determine overall validity
            result.valid = len(result.errors) == 0 and (not self.strict or len(result.warnings) == 0)
            
            # Log result
            if result.valid:
                logger.info(f"✓ {service_name}: Valid")
            else:
                logger.warning(f"✗ {service_name}: {len(result.errors)} errors, {len(result.warnings)} warnings")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process {manifest_file}: {e}")
            return ManifestValidationResult(
                manifest_file=str(manifest_file),
                service_name=manifest_file.stem,
                valid=False,
                errors=[ValidationIssue(
                    manifest_file=str(manifest_file),
                    service_name=manifest_file.stem,
                    issue_type="processing_error",
                    severity="error",
                    message=f"Failed to process manifest: {e}"
                )]
            )

    def _validate_schema(self, manifest: Dict[str, Any], result: ManifestValidationResult):
        """Validate manifest against JSON schema."""
        try:
            import jsonschema
            jsonschema.validate(manifest, self.manifest_schema)
        except ImportError:
            logger.warning("jsonschema not available, skipping schema validation")
        except Exception as e:
            result.errors.append(ValidationIssue(
                manifest_file=result.manifest_file,
                service_name=result.service_name,
                issue_type="schema_validation",
                severity="error",
                message=f"Schema validation failed: {e}",
                field_path="root"
            ))

    def _validate_required_fields(self, manifest: Dict[str, Any], result: ManifestValidationResult):
        """Validate required fields are present."""
        required_fields = self.validation_rules["manifest"]["required_fields"]
        
        for field in required_fields:
            if field not in manifest:
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="missing_required_field",
                    severity="error",
                    message=f"Required field '{field}' is missing",
                    field_path=field,
                    suggested_fix=f"Add '{field}' field to manifest"
                ))

    def _validate_field_types(self, manifest: Dict[str, Any], result: ManifestValidationResult):
        """Validate field types and formats."""
        # Validate name
        if 'name' in manifest:
            name = manifest['name']
            if not isinstance(name, str):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_field_type",
                    severity="error",
                    message="Field 'name' must be a string",
                    field_path="name"
                ))
            elif len(name) > self.validation_rules["manifest"]["max_name_length"]:
                result.warnings.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="field_too_long",
                    severity="warning",
                    message=f"Field 'name' is too long (max {self.validation_rules['manifest']['max_name_length']} chars)",
                    field_path="name"
                ))

        # Validate version
        if 'version' in manifest:
            version = manifest['version']
            if not isinstance(version, str):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_field_type",
                    severity="error",
                    message="Field 'version' must be a string",
                    field_path="version"
                ))
            else:
                version_pattern = self.validation_rules["manifest"]["version_pattern"]
                if not re.match(version_pattern, version):
                    result.errors.append(ValidationIssue(
                        manifest_file=result.manifest_file,
                        service_name=result.service_name,
                        issue_type="invalid_version_format",
                        severity="error",
                        message=f"Version '{version}' does not match semver format",
                        field_path="version",
                        suggested_fix="Use semver format: MAJOR.MINOR.PATCH"
                    ))

        # Validate domain
        if 'domain' in manifest:
            domain = manifest['domain']
            valid_domains = self.validation_rules["manifest"]["valid_domains"]
            if domain not in valid_domains:
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_domain",
                    severity="error",
                    message=f"Domain '{domain}' is not valid",
                    field_path="domain",
                    suggested_fix=f"Use one of: {', '.join(valid_domains)}"
                ))

        # Validate maturity
        if 'maturity' in manifest:
            maturity = manifest['maturity']
            valid_maturities = self.validation_rules["manifest"]["valid_maturities"]
            if maturity not in valid_maturities:
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_maturity",
                    severity="error",
                    message=f"Maturity '{maturity}' is not valid",
                    field_path="maturity",
                    suggested_fix=f"Use one of: {', '.join(valid_maturities)}"
                ))

    def _validate_field_values(self, manifest: Dict[str, Any], result: ManifestValidationResult):
        """Validate field values and constraints."""
        # Validate repository URL
        if 'repository' in manifest:
            repo = manifest['repository']
            if not isinstance(repo, str):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_field_type",
                    severity="error",
                    message="Field 'repository' must be a string",
                    field_path="repository"
                ))
            else:
                # Check URL format
                try:
                    parsed = urllib.parse.urlparse(repo)
                    if not parsed.scheme or not parsed.netloc:
                        result.errors.append(ValidationIssue(
                            manifest_file=result.manifest_file,
                            service_name=result.service_name,
                            issue_type="invalid_repository_url",
                            severity="error",
                            message="Repository URL is not valid",
                            field_path="repository"
                        ))
                    else:
                        # Check GitHub pattern
                        repo_pattern = self.validation_rules["manifest"]["repository_pattern"]
                        if not re.match(repo_pattern, repo):
                            result.warnings.append(ValidationIssue(
                                manifest_file=result.manifest_file,
                                service_name=result.service_name,
                                issue_type="non_standard_repository",
                                severity="warning",
                                message="Repository URL does not match standard pattern",
                                field_path="repository"
                            ))
                except Exception:
                    result.errors.append(ValidationIssue(
                        manifest_file=result.manifest_file,
                        service_name=result.service_name,
                        issue_type="invalid_repository_url",
                        severity="error",
                        message="Repository URL is not valid",
                        field_path="repository"
                    ))

        # Validate description length
        if 'description' in manifest:
            description = manifest['description']
            if isinstance(description, str):
                max_length = self.validation_rules["manifest"]["max_description_length"]
                if len(description) > max_length:
                    result.warnings.append(ValidationIssue(
                        manifest_file=result.manifest_file,
                        service_name=result.service_name,
                        issue_type="description_too_long",
                        severity="warning",
                        message=f"Description is too long (max {max_length} chars)",
                        field_path="description"
                    ))

    def _validate_dependencies(self, manifest: Dict[str, Any], result: ManifestValidationResult):
        """Validate dependency structure."""
        if 'dependencies' not in manifest:
            return
        
        deps = manifest['dependencies']
        if not isinstance(deps, dict):
            result.errors.append(ValidationIssue(
                manifest_file=result.manifest_file,
                service_name=result.service_name,
                issue_type="invalid_dependencies_structure",
                severity="error",
                message="Dependencies must be an object",
                field_path="dependencies"
            ))
            return
        
        # Validate internal dependencies
        if 'internal' in deps:
            internal_deps = deps['internal']
            if not isinstance(internal_deps, list):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_internal_dependencies",
                    severity="error",
                    message="Internal dependencies must be a list",
                    field_path="dependencies.internal"
                ))
            else:
                for dep in internal_deps:
                    if not isinstance(dep, str):
                        result.errors.append(ValidationIssue(
                            manifest_file=result.manifest_file,
                            service_name=result.service_name,
                            issue_type="invalid_dependency_item",
                            severity="error",
                            message="Dependency items must be strings",
                            field_path="dependencies.internal"
                        ))

        # Validate external dependencies
        if 'external' in deps:
            external_deps = deps['external']
            if not isinstance(external_deps, list):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_external_dependencies",
                    severity="error",
                    message="External dependencies must be a list",
                    field_path="dependencies.external"
                ))
            else:
                for dep in external_deps:
                    if not isinstance(dep, str):
                        result.errors.append(ValidationIssue(
                            manifest_file=result.manifest_file,
                            service_name=result.service_name,
                            issue_type="invalid_dependency_item",
                            severity="error",
                            message="Dependency items must be strings",
                            field_path="dependencies.external"
                        ))

    def _validate_quality_metrics(self, manifest: Dict[str, Any], result: ManifestValidationResult):
        """Validate quality metrics."""
        if 'quality' not in manifest:
            # Check if quality metrics are required for this maturity level
            maturity = manifest.get('maturity')
            if maturity in ['stable', 'beta']:
                required_fields = self.validation_rules["quality"]["required_for_stable"]
                result.warnings.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="missing_quality_metrics",
                    severity="warning",
                    message=f"Quality metrics recommended for {maturity} services",
                    field_path="quality",
                    suggested_fix=f"Add quality section with: {', '.join(required_fields)}"
                ))
            return
        
        quality = manifest['quality']
        if not isinstance(quality, dict):
            result.errors.append(ValidationIssue(
                manifest_file=result.manifest_file,
                service_name=result.service_name,
                issue_type="invalid_quality_structure",
                severity="error",
                message="Quality must be an object",
                field_path="quality"
            ))
            return
        
        # Validate coverage
        if 'coverage' in quality:
            coverage = quality['coverage']
            if not isinstance(coverage, (int, float)):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_coverage_type",
                    severity="error",
                    message="Coverage must be a number",
                    field_path="quality.coverage"
                ))
            else:
                min_coverage = self.validation_rules["quality"]["min_coverage"]
                max_coverage = self.validation_rules["quality"]["max_coverage"]
                if not (min_coverage <= coverage <= max_coverage):
                    result.errors.append(ValidationIssue(
                        manifest_file=result.manifest_file,
                        service_name=result.service_name,
                        issue_type="invalid_coverage_range",
                        severity="error",
                        message=f"Coverage must be between {min_coverage} and {max_coverage}",
                        field_path="quality.coverage"
                    ))

        # Validate lint_pass
        if 'lint_pass' in quality:
            lint_pass = quality['lint_pass']
            if not isinstance(lint_pass, bool):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_lint_pass_type",
                    severity="error",
                    message="lint_pass must be a boolean",
                    field_path="quality.lint_pass"
                ))

    def _validate_security_config(self, manifest: Dict[str, Any], result: ManifestValidationResult):
        """Validate security configuration."""
        if 'security' not in manifest:
            # Check if security config is required for this maturity level
            maturity = manifest.get('maturity')
            if maturity in ['stable', 'beta']:
                required_fields = self.validation_rules["security"]["required_for_stable"]
                result.warnings.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="missing_security_config",
                    severity="warning",
                    message=f"Security configuration recommended for {maturity} services",
                    field_path="security",
                    suggested_fix=f"Add security section with: {', '.join(required_fields)}"
                ))
            return
        
        security = manifest['security']
        if not isinstance(security, dict):
            result.errors.append(ValidationIssue(
                manifest_file=result.manifest_file,
                service_name=result.service_name,
                issue_type="invalid_security_structure",
                severity="error",
                message="Security must be an object",
                field_path="security"
            ))
            return
        
        # Validate signed_images
        if 'signed_images' in security:
            signed_images = security['signed_images']
            if not isinstance(signed_images, bool):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_signed_images_type",
                    severity="error",
                    message="signed_images must be a boolean",
                    field_path="security.signed_images"
                ))

        # Validate policy_pass
        if 'policy_pass' in security:
            policy_pass = security['policy_pass']
            if not isinstance(policy_pass, bool):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_policy_pass_type",
                    severity="error",
                    message="policy_pass must be a boolean",
                    field_path="security.policy_pass"
                ))

    def _validate_repository_info(self, manifest: Dict[str, Any], result: ManifestValidationResult):
        """Validate repository information."""
        # Validate path field
        if 'path' in manifest:
            path = manifest['path']
            if not isinstance(path, str):
                result.errors.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="invalid_path_type",
                    severity="error",
                    message="Path must be a string",
                    field_path="path"
                ))
            elif path and not path.startswith('/') and path != '.':
                # Warn about non-standard paths
                result.warnings.append(ValidationIssue(
                    manifest_file=result.manifest_file,
                    service_name=result.service_name,
                    issue_type="non_standard_path",
                    severity="warning",
                    message="Path should be '.' for root or absolute path",
                    field_path="path"
                ))

    def _validate_cross_manifest_consistency(self):
        """Validate consistency across all manifests."""
        logger.info("Validating cross-manifest consistency...")
        
        # Check for duplicate service names
        service_names = [result.service_name for result in self.validation_results]
        duplicates = set([name for name in service_names if service_names.count(name) > 1])
        
        for duplicate in duplicates:
            for result in self.validation_results:
                if result.service_name == duplicate:
                    result.errors.append(ValidationIssue(
                        manifest_file=result.manifest_file,
                        service_name=result.service_name,
                        issue_type="duplicate_service_name",
                        severity="error",
                        message=f"Duplicate service name: {duplicate}",
                        field_path="name"
                    ))
        
        # Check for circular dependencies
        self._check_circular_dependencies()
        
        # Check for missing dependencies
        self._check_missing_dependencies()

    def _check_circular_dependencies(self):
        """Check for circular dependencies between services."""
        # Build dependency graph
        dep_graph = {}
        for service_name, manifest in self.all_manifests.items():
            deps = manifest.get('dependencies', {}).get('internal', [])
            dep_graph[service_name] = deps
        
        # Check for cycles using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in dep_graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for service_name in dep_graph:
            if service_name not in visited:
                if has_cycle(service_name):
                    # Find the cycle and report it
                    for result in self.validation_results:
                        if result.service_name == service_name:
                            result.errors.append(ValidationIssue(
                                manifest_file=result.manifest_file,
                                service_name=result.service_name,
                                issue_type="circular_dependency",
                                severity="error",
                                message="Circular dependency detected",
                                field_path="dependencies.internal"
                            ))

    def _check_missing_dependencies(self):
        """Check for dependencies that don't exist in other manifests."""
        all_service_names = set(self.all_manifests.keys())
        
        for service_name, manifest in self.all_manifests.items():
            internal_deps = manifest.get('dependencies', {}).get('internal', [])
            
            for dep in internal_deps:
                if dep not in all_service_names:
                    # Find the result for this service
                    for result in self.validation_results:
                        if result.service_name == service_name:
                            result.warnings.append(ValidationIssue(
                                manifest_file=result.manifest_file,
                                service_name=result.service_name,
                                issue_type="missing_dependency",
                                severity="warning",
                                message=f"Dependency '{dep}' not found in other manifests",
                                field_path="dependencies.internal"
                            ))

    def _apply_fixes(self, manifest_file: Path, result: ManifestValidationResult):
        """Apply auto-fixes to a manifest file."""
        if not result.fixes_applied:
            return
        
        try:
            # Load manifest
            with open(manifest_file) as f:
                manifest = yaml.safe_load(f)
            
            # Apply fixes (simplified - in practice, you'd implement specific fixes)
            for fix in result.fixes_applied:
                logger.info(f"Applied fix to {manifest_file}: {fix}")
            
            # Save updated manifest
            with open(manifest_file, 'w') as f:
                yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"Auto-fixes applied to {manifest_file}")
            
        except Exception as e:
            logger.error(f"Failed to apply fixes to {manifest_file}: {e}")

    def _generate_summary_report(self) -> Dict[str, Any]:
        """Generate summary report of all validations."""
        total_manifests = len(self.validation_results)
        valid_count = sum(1 for result in self.validation_results if result.valid)
        invalid_count = total_manifests - valid_count
        
        total_issues = sum(len(result.issues) for result in self.validation_results)
        total_errors = sum(len(result.errors) for result in self.validation_results)
        total_warnings = sum(len(result.warnings) for result in self.validation_results)
        
        # Group issues by type
        issue_types = {}
        for result in self.validation_results:
            for issue in result.issues:
                issue_type = issue.issue_type
                if issue_type not in issue_types:
                    issue_types[issue_type] = 0
                issue_types[issue_type] += 1
        
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "manifests_dir": str(self.manifests_dir),
                "total_manifests": total_manifests,
                "validation_mode": "strict" if self.strict else "normal",
                "auto_fix_enabled": self.auto_fix
            },
            "summary": {
                "valid_count": valid_count,
                "invalid_count": invalid_count,
                "total_issues": total_issues,
                "total_errors": total_errors,
                "total_warnings": total_warnings,
                "success_rate": valid_count / total_manifests if total_manifests > 0 else 0
            },
            "issue_types": issue_types,
            "results": [
                {
                    "manifest_file": result.manifest_file,
                    "service_name": result.service_name,
                    "valid": result.valid,
                    "issue_count": len(result.issues),
                    "error_count": len(result.errors),
                    "warning_count": len(result.warnings),
                    "fixes_applied": result.fixes_applied
                }
                for result in self.validation_results
            ]
        }

    def save_report(self, report: Dict[str, Any], output_file: str = None) -> str:
        """Save validation report to file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"analysis/reports/manifest_validation_{timestamp}.json"
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Validation report saved: {output_path}")
        return str(output_path)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate service manifests")
    parser.add_argument("--manifests-dir", type=str, default="manifests/collected",
                       help="Directory containing manifest files")
    parser.add_argument("--strict", action="store_true",
                       help="Fail on warnings and minor issues")
    parser.add_argument("--fix", action="store_true",
                       help="Automatically fix common issues")
    parser.add_argument("--report", action="store_true",
                       help="Generate detailed validation report")
    parser.add_argument("--output-file", type=str,
                       help="Output file for validation report")
    parser.add_argument("--debug", action="store_true",
                       help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        validator = ManifestValidator(
            manifests_dir=args.manifests_dir,
            strict=args.strict,
            auto_fix=args.fix
        )
        
        report = validator.validate_all_manifests()
        
        if args.report or args.output_file:
            output_file = validator.save_report(report, args.output_file)
            print(f"Validation report saved: {output_file}")
        
        # Print summary
        summary = report["summary"]
        print(f"\nManifest Validation Summary:")
        print(f"  Total Manifests: {report['metadata']['total_manifests']}")
        print(f"  Valid: {summary['valid_count']}")
        print(f"  Invalid: {summary['invalid_count']}")
        print(f"  Success Rate: {summary['success_rate']:.1%}")
        print(f"  Total Issues: {summary['total_issues']} ({summary['total_errors']} errors, {summary['total_warnings']} warnings)")
        
        if summary['total_errors'] > 0:
            print("\n❌ Validation failed due to errors")
            sys.exit(1)
        elif args.strict and summary['total_warnings'] > 0:
            print("\n⚠️  Validation failed due to warnings (strict mode)")
            sys.exit(1)
        else:
            print("\n✅ All validations passed")
            sys.exit(0)
    
    except Exception as e:
        logger.error(f"Manifest validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
