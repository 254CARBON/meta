#!/usr/bin/env python3
"""
Base adapter class for service manifest generation.

All service format adapters inherit from this base class to ensure
consistent interface and behavior across different formats.
"""

import json
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Union
from pathlib import Path


@dataclass
class AdapterResult:
    """Result of adapter processing."""
    success: bool
    service_manifest: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseAdapter(ABC):
    """Base class for all service manifest adapters."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the adapter with optional configuration."""
        self.config = config or {}
        self.supported_extensions = []
        self.supported_files = []
    
    @abstractmethod
    def can_process(self, file_path: str, content: str) -> bool:
        """
        Determine if this adapter can process the given file.
        
        Args:
            file_path: Path to the file
            content: File content as string
            
        Returns:
            True if this adapter can process the file
        """
        pass
    
    @abstractmethod
    def extract_manifest(self, file_path: str, content: str, 
                        repo_metadata: Optional[Dict[str, Any]] = None) -> AdapterResult:
        """
        Extract service manifest from file content.
        
        Args:
            file_path: Path to the file
            content: File content as string
            repo_metadata: Additional repository metadata
            
        Returns:
            AdapterResult with extracted manifest or errors
        """
        pass
    
    def validate_manifest(self, manifest: Dict[str, Any]) -> List[str]:
        """
        Validate extracted manifest against schema.
        
        Args:
            manifest: Extracted service manifest
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Required fields
        required_fields = ['name', 'version', 'domain', 'maturity']
        for field in required_fields:
            if field not in manifest:
                errors.append(f"Missing required field: {field}")
        
        # Validate domain
        valid_domains = ['access', 'data', 'ml', 'infrastructure', 'security', 'observability']
        if 'domain' in manifest and manifest['domain'] not in valid_domains:
            errors.append(f"Invalid domain: {manifest['domain']}")
        
        # Validate maturity
        valid_maturities = ['experimental', 'beta', 'stable', 'deprecated']
        if 'maturity' in manifest and manifest['maturity'] not in valid_maturities:
            errors.append(f"Invalid maturity: {manifest['maturity']}")
        
        # Validate version format
        if 'version' in manifest:
            version = manifest['version']
            if not isinstance(version, str) or not self._is_valid_version(version):
                errors.append(f"Invalid version format: {version}")
        
        return errors
    
    def _is_valid_version(self, version: str) -> bool:
        """Check if version string is valid."""
        import re
        # Simple semantic versioning check
        pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?(\+[a-zA-Z0-9]+)?$'
        return bool(re.match(pattern, version))
    
    def _parse_yaml(self, content: str) -> Optional[Dict[str, Any]]:
        """Safely parse YAML content."""
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            return None
    
    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Safely parse JSON content."""
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    
    def _extract_dependencies(self, content: Dict[str, Any], 
                            dependency_keys: List[str]) -> List[str]:
        """Extract dependencies from various key patterns."""
        dependencies = []
        
        for key in dependency_keys:
            if key in content:
                deps = content[key]
                if isinstance(deps, list):
                    dependencies.extend(deps)
                elif isinstance(deps, dict):
                    dependencies.extend(deps.keys())
                elif isinstance(deps, str):
                    dependencies.append(deps)
        
        return list(set(dependencies))  # Remove duplicates
    
    def _determine_runtime(self, file_path: str, content: Dict[str, Any]) -> str:
        """Determine runtime from file path and content."""
        file_path_lower = file_path.lower()
        
        # Check file extensions
        if file_path_lower.endswith('.py') or 'python' in file_path_lower:
            return 'python'
        elif file_path_lower.endswith(('.js', '.ts')) or 'node' in file_path_lower:
            return 'nodejs'
        elif file_path_lower.endswith('.go') or 'go.mod' in file_path_lower:
            return 'go'
        elif file_path_lower.endswith('.rs') or 'cargo.toml' in file_path_lower:
            return 'rust'
        elif file_path_lower.endswith('.java') or 'pom.xml' in file_path_lower:
            return 'java'
        elif file_path_lower.endswith('.cs') or 'dotnet' in file_path_lower:
            return 'dotnet'
        elif file_path_lower.endswith('.php'):
            return 'php'
        elif file_path_lower.endswith('.rb') or 'gemfile' in file_path_lower:
            return 'ruby'
        
        # Check content for runtime indicators
        content_str = str(content).lower()
        if 'python' in content_str or 'pip' in content_str:
            return 'python'
        elif 'node' in content_str or 'npm' in content_str:
            return 'nodejs'
        elif 'go' in content_str:
            return 'go'
        elif 'rust' in content_str or 'cargo' in content_str:
            return 'rust'
        elif 'java' in content_str or 'maven' in content_str:
            return 'java'
        
        return 'unknown'
    
    def _determine_domain(self, name: str, content: Dict[str, Any]) -> str:
        """Determine domain from service name and content."""
        name_lower = name.lower()
        content_str = str(content).lower()
        
        # Domain patterns
        if any(pattern in name_lower for pattern in ['access', 'auth', 'gateway', 'proxy']):
            return 'access'
        elif any(pattern in name_lower for pattern in ['data', 'database', 'storage', 'etl']):
            return 'data'
        elif any(pattern in name_lower for pattern in ['ml', 'ai', 'model', 'training']):
            return 'ml'
        elif any(pattern in name_lower for pattern in ['infra', 'platform', 'core']):
            return 'infrastructure'
        elif any(pattern in name_lower for pattern in ['security', 'vault', 'secrets']):
            return 'security'
        elif any(pattern in name_lower for pattern in ['monitoring', 'logging', 'metrics']):
            return 'observability'
        
        return 'unknown'
    
    def _determine_maturity(self, name: str, content: Dict[str, Any]) -> str:
        """Determine maturity level from service indicators."""
        name_lower = name.lower()
        content_str = str(content).lower()
        
        # Maturity indicators
        if any(pattern in name_lower for pattern in ['experimental', 'alpha', 'prototype']):
            return 'experimental'
        elif any(pattern in name_lower for pattern in ['beta', 'preview', 'rc']):
            return 'beta'
        elif any(pattern in name_lower for pattern in ['deprecated', 'legacy', 'old']):
            return 'deprecated'
        elif 'production' in content_str or 'stable' in content_str:
            return 'stable'
        
        return 'beta'  # Default to beta for unknown services
    
    def _generate_manifest(self, name: str, version: str, domain: str, 
                          maturity: str, runtime: str, 
                          additional_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate a standardized service manifest."""
        manifest = {
            'name': name,
            'version': version,
            'domain': domain,
            'maturity': maturity,
            'runtime': runtime,
            'dependencies': {
                'internal': [],
                'external': []
            },
            'last_update': datetime.now(timezone.utc).isoformat()
        }
        
        # Add additional fields
        if additional_fields:
            manifest.update(additional_fields)
        
        return manifest
