#!/usr/bin/env python3
"""
Package.json adapter for service manifest generation.

Extracts service information from Node.js package.json files.
"""

import re
from typing import Dict, List, Any, Optional
from .base_adapter import BaseAdapter, AdapterResult


class PackageJsonAdapter(BaseAdapter):
    """Adapter for package.json files."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the package.json adapter."""
        super().__init__(config)
        self.supported_extensions = ['.json']
        self.supported_files = ['package.json']
    
    def can_process(self, file_path: str, content: str) -> bool:
        """Check if this adapter can process the file."""
        file_path_lower = file_path.lower()
        
        # Check if it's a package.json file
        if 'package.json' in file_path_lower:
            return True
        
        # Check for package.json indicators in content
        try:
            parsed = self._parse_json(content)
            if parsed and 'name' in parsed and 'version' in parsed:
                return True
        except:
            pass
        
        return False
    
    def extract_manifest(self, file_path: str, content: str, 
                        repo_metadata: Optional[Dict[str, Any]] = None) -> AdapterResult:
        """Extract service manifest from package.json file."""
        try:
            parsed = self._parse_json(content)
            if not parsed:
                return AdapterResult(
                    success=False,
                    errors=["Failed to parse JSON content"]
                )
            
            # Extract manifest information
            manifest = self._extract_service_manifest(
                parsed, repo_metadata
            )
            
            # Validate manifest
            errors = self.validate_manifest(manifest)
            if errors:
                return AdapterResult(
                    success=False,
                    errors=errors,
                    service_manifest=manifest
                )
            
            return AdapterResult(
                success=True,
                service_manifest=manifest,
                confidence=0.7,
                metadata={
                    'extracted_from': 'package.json',
                    'node_version': parsed.get('engines', {}).get('node'),
                    'npm_version': parsed.get('engines', {}).get('npm')
                }
            )
            
        except Exception as e:
            return AdapterResult(
                success=False,
                errors=[f"Error processing package.json file: {str(e)}"]
            )
    
    def _extract_service_manifest(self, package_json: Dict[str, Any],
                                 repo_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract service manifest from package.json."""
        
        # Extract basic information
        name = self._extract_name(package_json)
        version = self._extract_version(package_json)
        runtime = 'nodejs'
        domain = self._determine_domain(name, package_json)
        maturity = self._determine_maturity(name, package_json)
        
        # Extract dependencies
        dependencies = self._extract_dependencies(package_json)
        
        # Extract additional metadata
        additional_fields = {
            'dependencies': dependencies,
            'scripts': self._extract_scripts(package_json),
            'engines': self._extract_engines(package_json),
            'keywords': package_json.get('keywords', []),
            'description': package_json.get('description', ''),
            'license': package_json.get('license', ''),
            'author': self._extract_author(package_json),
            'repository': self._extract_repository(package_json),
            'homepage': package_json.get('homepage', ''),
            'bugs': package_json.get('bugs', {}),
            'main': package_json.get('main', ''),
            'bin': package_json.get('bin', {}),
            'files': package_json.get('files', [])
        }
        
        # Add repository metadata if available
        if repo_metadata:
            additional_fields.update({
                'repo': repo_metadata.get('repo_url'),
                'path': repo_metadata.get('path', ''),
                'last_commit': repo_metadata.get('last_commit')
            })
        
        return self._generate_manifest(
            name=name,
            version=version,
            domain=domain,
            maturity=maturity,
            runtime=runtime,
            additional_fields=additional_fields
        )
    
    def _extract_name(self, package_json: Dict[str, Any]) -> str:
        """Extract service name from package.json."""
        name = package_json.get('name', '')
        
        # Clean and normalize name
        name = re.sub(r'^254carbon-', '', name)
        name = re.sub(r'^@254carbon/', '', name)
        name = re.sub(r'-(service|api|app|web)$', '', name)
        name = re.sub(r'^service-', '', name)
        name = re.sub(r'^api-', '', name)
        
        # Convert to service name format
        name = name.replace('-', '_')
        return name.lower()
    
    def _extract_version(self, package_json: Dict[str, Any]) -> str:
        """Extract version from package.json."""
        version = package_json.get('version', '1.0.0')
        
        # Validate version format
        if not re.match(r'^\d+\.\d+\.\d+', version):
            return '1.0.0'
        
        return version
    
    def _extract_dependencies(self, package_json: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract dependencies from package.json."""
        dependencies = {
            'internal': [],
            'external': []
        }
        
        # Extract all dependencies
        all_deps = {}
        all_deps.update(package_json.get('dependencies', {}))
        all_deps.update(package_json.get('devDependencies', {}))
        all_deps.update(package_json.get('peerDependencies', {}))
        all_deps.update(package_json.get('optionalDependencies', {}))
        
        # Categorize dependencies
        for dep_name, dep_version in all_deps.items():
            # Check if it's an internal dependency (starts with @254carbon or 254carbon-)
            if dep_name.startswith('@254carbon/') or dep_name.startswith('254carbon-'):
                dependencies['internal'].append(f"{dep_name}@{dep_version}")
            else:
                dependencies['external'].append(f"{dep_name}@{dep_version}")
        
        return dependencies
    
    def _extract_scripts(self, package_json: Dict[str, Any]) -> Dict[str, str]:
        """Extract npm scripts."""
        return package_json.get('scripts', {})
    
    def _extract_engines(self, package_json: Dict[str, Any]) -> Dict[str, str]:
        """Extract engine requirements."""
        return package_json.get('engines', {})
    
    def _extract_author(self, package_json: Dict[str, Any]) -> Dict[str, Any]:
        """Extract author information."""
        author = package_json.get('author', {})
        
        if isinstance(author, str):
            # Parse string author format
            return {'name': author}
        elif isinstance(author, dict):
            return author
        
        return {}
    
    def _extract_repository(self, package_json: Dict[str, Any]) -> Dict[str, Any]:
        """Extract repository information."""
        repository = package_json.get('repository', {})
        
        if isinstance(repository, str):
            # Parse string repository format
            return {'url': repository}
        elif isinstance(repository, dict):
            return repository
        
        return {}
    
    def _determine_domain(self, name: str, package_json: Dict[str, Any]) -> str:
        """Determine domain from package name and content."""
        name_lower = name.lower()
        description = package_json.get('description', '').lower()
        keywords = [kw.lower() for kw in package_json.get('keywords', [])]
        
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
        
        # Check description and keywords
        all_text = f"{name_lower} {description} {' '.join(keywords)}"
        
        if any(pattern in all_text for pattern in ['access', 'auth', 'gateway', 'proxy']):
            return 'access'
        elif any(pattern in all_text for pattern in ['data', 'database', 'storage', 'etl']):
            return 'data'
        elif any(pattern in all_text for pattern in ['ml', 'ai', 'model', 'training']):
            return 'ml'
        elif any(pattern in all_text for pattern in ['infra', 'platform', 'core']):
            return 'infrastructure'
        elif any(pattern in all_text for pattern in ['security', 'vault', 'secrets']):
            return 'security'
        elif any(pattern in all_text for pattern in ['monitoring', 'logging', 'metrics']):
            return 'observability'
        
        return 'unknown'
    
    def _determine_maturity(self, name: str, package_json: Dict[str, Any]) -> str:
        """Determine maturity level from package indicators."""
        name_lower = name.lower()
        version = package_json.get('version', '1.0.0')
        
        # Maturity indicators
        if any(pattern in name_lower for pattern in ['experimental', 'alpha', 'prototype']):
            return 'experimental'
        elif any(pattern in name_lower for pattern in ['beta', 'preview', 'rc']):
            return 'beta'
        elif any(pattern in name_lower for pattern in ['deprecated', 'legacy', 'old']):
            return 'deprecated'
        elif version.startswith('0.'):
            return 'experimental'
        elif version.startswith('1.'):
            return 'beta'
        elif version.startswith('2.') or version.startswith('3.'):
            return 'stable'
        
        return 'beta'  # Default to beta for unknown services
