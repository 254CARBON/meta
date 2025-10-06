#!/usr/bin/env python3
"""
Requirements adapter for service manifest generation.

Extracts service information from Python requirements files.
"""

import re
from typing import Dict, List, Any, Optional
from .base_adapter import BaseAdapter, AdapterResult


class RequirementsAdapter(BaseAdapter):
    """Adapter for Python requirements files."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the requirements adapter."""
        super().__init__(config)
        self.supported_extensions = ['.txt', '.toml', '.cfg', '.ini']
        self.supported_files = ['requirements.txt', 'pyproject.toml', 'Pipfile', 'setup.py']
    
    def can_process(self, file_path: str, content: str) -> bool:
        """Check if this adapter can process the file."""
        file_path_lower = file_path.lower()
        
        # Check if it's a Python requirements file
        if any(filename in file_path_lower for filename in self.supported_files):
            return True
        
        # Check for Python indicators in content
        if 'requirements.txt' in file_path_lower:
            return True
        
        # Check for pyproject.toml indicators
        if 'pyproject.toml' in file_path_lower:
            return True
        
        # Check for Pipfile indicators
        if 'pipfile' in file_path_lower:
            return True
        
        # Check for setup.py indicators
        if 'setup.py' in file_path_lower:
            return True
        
        return False
    
    def extract_manifest(self, file_path: str, content: str, 
                        repo_metadata: Optional[Dict[str, Any]] = None) -> AdapterResult:
        """Extract service manifest from requirements file."""
        try:
            # Determine file type and parse accordingly
            file_path_lower = file_path.lower()
            
            if 'requirements.txt' in file_path_lower:
                parsed = self._parse_requirements_txt(content)
            elif 'pyproject.toml' in file_path_lower:
                parsed = self._parse_pyproject_toml(content)
            elif 'pipfile' in file_path_lower:
                parsed = self._parse_pipfile(content)
            elif 'setup.py' in file_path_lower:
                parsed = self._parse_setup_py(content)
            else:
                return AdapterResult(
                    success=False,
                    errors=["Unsupported requirements file format"]
                )
            
            if not parsed:
                return AdapterResult(
                    success=False,
                    errors=["Failed to parse requirements file"]
                )
            
            # Extract manifest information
            manifest = self._extract_service_manifest(
                parsed, file_path, repo_metadata
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
                    'extracted_from': 'requirements',
                    'file_type': self._get_file_type(file_path),
                    'total_dependencies': len(parsed.get('dependencies', []))
                }
            )
            
        except Exception as e:
            return AdapterResult(
                success=False,
                errors=[f"Error processing requirements file: {str(e)}"]
            )
    
    def _parse_requirements_txt(self, content: str) -> Dict[str, Any]:
        """Parse requirements.txt file."""
        dependencies = []
        dev_dependencies = []
        
        lines = content.split('\n')
        current_section = 'dependencies'
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Check for section headers
            if line.startswith('# dev') or line.startswith('# development'):
                current_section = 'dev_dependencies'
                continue
            
            # Parse dependency line
            if line:
                if current_section == 'dependencies':
                    dependencies.append(line)
                else:
                    dev_dependencies.append(line)
        
        return {
            'dependencies': dependencies,
            'dev_dependencies': dev_dependencies,
            'file_type': 'requirements.txt'
        }
    
    def _parse_pyproject_toml(self, content: str) -> Dict[str, Any]:
        """Parse pyproject.toml file."""
        try:
            import toml
            parsed = toml.loads(content)
            
            # Extract dependencies
            dependencies = []
            dev_dependencies = []
            
            # Check for poetry configuration
            if 'tool' in parsed and 'poetry' in parsed['tool']:
                poetry = parsed['tool']['poetry']
                dependencies = poetry.get('dependencies', {}).keys()
                dev_dependencies = poetry.get('dev-dependencies', {}).keys()
            
            # Check for pip configuration
            elif 'build-system' in parsed:
                # This is a build system configuration
                pass
            
            return {
                'dependencies': list(dependencies),
                'dev_dependencies': list(dev_dependencies),
                'file_type': 'pyproject.toml',
                'metadata': parsed
            }
        except ImportError:
            # Fallback parsing without toml library
            return self._parse_pyproject_toml_fallback(content)
    
    def _parse_pyproject_toml_fallback(self, content: str) -> Dict[str, Any]:
        """Fallback parsing for pyproject.toml without toml library."""
        dependencies = []
        dev_dependencies = []
        
        lines = content.split('\n')
        in_dependencies = False
        in_dev_dependencies = False
        
        for line in lines:
            line = line.strip()
            
            # Check for section headers
            if '[tool.poetry.dependencies]' in line:
                in_dependencies = True
                in_dev_dependencies = False
                continue
            elif '[tool.poetry.dev-dependencies]' in line:
                in_dependencies = False
                in_dev_dependencies = True
                continue
            elif line.startswith('['):
                in_dependencies = False
                in_dev_dependencies = False
                continue
            
            # Parse dependency lines
            if in_dependencies or in_dev_dependencies:
                if line and not line.startswith('#'):
                    # Extract package name (before = or [)
                    package_name = line.split('=')[0].split('[')[0].strip().strip('"\'')
                    if package_name:
                        if in_dependencies:
                            dependencies.append(package_name)
                        else:
                            dev_dependencies.append(package_name)
        
        return {
            'dependencies': dependencies,
            'dev_dependencies': dev_dependencies,
            'file_type': 'pyproject.toml'
        }
    
    def _parse_pipfile(self, content: str) -> Dict[str, Any]:
        """Parse Pipfile."""
        try:
            import toml
            parsed = toml.loads(content)
            
            dependencies = []
            dev_dependencies = []
            
            # Extract from [packages] section
            if 'packages' in parsed:
                dependencies = list(parsed['packages'].keys())
            
            # Extract from [dev-packages] section
            if 'dev-packages' in parsed:
                dev_dependencies = list(parsed['dev-packages'].keys())
            
            return {
                'dependencies': dependencies,
                'dev_dependencies': dev_dependencies,
                'file_type': 'Pipfile',
                'metadata': parsed
            }
        except ImportError:
            # Fallback parsing without toml library
            return self._parse_pipfile_fallback(content)
    
    def _parse_pipfile_fallback(self, content: str) -> Dict[str, Any]:
        """Fallback parsing for Pipfile without toml library."""
        dependencies = []
        dev_dependencies = []
        
        lines = content.split('\n')
        in_packages = False
        in_dev_packages = False
        
        for line in lines:
            line = line.strip()
            
            # Check for section headers
            if '[packages]' in line:
                in_packages = True
                in_dev_packages = False
                continue
            elif '[dev-packages]' in line:
                in_packages = False
                in_dev_packages = True
                continue
            elif line.startswith('['):
                in_packages = False
                in_dev_packages = False
                continue
            
            # Parse dependency lines
            if in_packages or in_dev_packages:
                if line and not line.startswith('#'):
                    # Extract package name (before = or [)
                    package_name = line.split('=')[0].split('[')[0].strip().strip('"\'')
                    if package_name:
                        if in_packages:
                            dependencies.append(package_name)
                        else:
                            dev_dependencies.append(package_name)
        
        return {
            'dependencies': dependencies,
            'dev_dependencies': dev_dependencies,
            'file_type': 'Pipfile'
        }
    
    def _parse_setup_py(self, content: str) -> Dict[str, Any]:
        """Parse setup.py file."""
        dependencies = []
        dev_dependencies = []
        
        # Simple regex-based parsing for setup.py
        # This is a basic implementation and may not catch all cases
        
        # Look for install_requires
        install_requires_match = re.search(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if install_requires_match:
            deps_str = install_requires_match.group(1)
            deps = re.findall(r'["\']([^"\']+)["\']', deps_str)
            dependencies.extend(deps)
        
        # Look for extras_require
        extras_require_match = re.search(r'extras_require\s*=\s*\{[^}]*dev[^}]*:\s*\[(.*?)\]', content, re.DOTALL)
        if extras_require_match:
            deps_str = extras_require_match.group(1)
            deps = re.findall(r'["\']([^"\']+)["\']', deps_str)
            dev_dependencies.extend(deps)
        
        return {
            'dependencies': dependencies,
            'dev_dependencies': dev_dependencies,
            'file_type': 'setup.py'
        }
    
    def _get_file_type(self, file_path: str) -> str:
        """Get the file type from path."""
        file_path_lower = file_path.lower()
        
        if 'requirements.txt' in file_path_lower:
            return 'requirements.txt'
        elif 'pyproject.toml' in file_path_lower:
            return 'pyproject.toml'
        elif 'pipfile' in file_path_lower:
            return 'Pipfile'
        elif 'setup.py' in file_path_lower:
            return 'setup.py'
        
        return 'unknown'
    
    def _extract_service_manifest(self, parsed: Dict[str, Any], file_path: str,
                                 repo_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract service manifest from parsed requirements."""
        
        # Extract basic information
        name = self._extract_name(file_path, parsed)
        version = self._extract_version(parsed)
        runtime = 'python'
        domain = self._determine_domain(name, parsed)
        maturity = self._determine_maturity(name, parsed)
        
        # Extract dependencies
        dependencies = self._extract_dependencies(parsed)
        
        # Extract additional metadata
        additional_fields = {
            'dependencies': dependencies,
            'python_version': self._extract_python_version(parsed),
            'file_type': parsed.get('file_type', 'unknown'),
            'total_dependencies': len(parsed.get('dependencies', [])),
            'dev_dependencies': parsed.get('dev_dependencies', [])
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
    
    def _extract_name(self, file_path: str, parsed: Dict[str, Any]) -> str:
        """Extract service name from file path and content."""
        # Try to extract from file path
        path_parts = file_path.split('/')
        for part in reversed(path_parts):
            if part and part != 'requirements.txt' and part != 'pyproject.toml':
                name = part
                break
        else:
            name = 'unknown'
        
        # Clean and normalize name
        name = re.sub(r'^254carbon-', '', name)
        name = re.sub(r'-(service|api|app|web)$', '', name)
        name = re.sub(r'^service-', '', name)
        name = re.sub(r'^api-', '', name)
        
        # Convert to service name format
        name = name.replace('-', '_')
        return name.lower()
    
    def _extract_version(self, parsed: Dict[str, Any]) -> str:
        """Extract version from parsed content."""
        # Check metadata for version
        metadata = parsed.get('metadata', {})
        if 'version' in metadata:
            return metadata['version']
        
        # Default version
        return '1.0.0'
    
    def _extract_dependencies(self, parsed: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract dependencies from parsed content."""
        dependencies = {
            'internal': [],
            'external': []
        }
        
        # Extract all dependencies
        all_deps = parsed.get('dependencies', [])
        dev_deps = parsed.get('dev_dependencies', [])
        
        # Categorize dependencies
        for dep in all_deps + dev_deps:
            # Check if it's an internal dependency (starts with 254carbon-)
            if dep.startswith('254carbon-'):
                dependencies['internal'].append(dep)
            else:
                dependencies['external'].append(dep)
        
        return dependencies
    
    def _extract_python_version(self, parsed: Dict[str, Any]) -> Optional[str]:
        """Extract Python version requirement."""
        metadata = parsed.get('metadata', {})
        
        # Check for Python version in metadata
        if 'python' in metadata:
            return metadata['python']
        
        # Check for Python version in dependencies
        dependencies = parsed.get('dependencies', [])
        for dep in dependencies:
            if dep.startswith('python'):
                return dep
        
        return None
    
    def _determine_domain(self, name: str, parsed: Dict[str, Any]) -> str:
        """Determine domain from service name and dependencies."""
        name_lower = name.lower()
        dependencies = parsed.get('dependencies', [])
        all_deps_text = ' '.join(dependencies).lower()
        
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
        
        # Check dependencies for domain indicators
        if any(pattern in all_deps_text for pattern in ['django', 'flask', 'fastapi', 'web']):
            return 'access'
        elif any(pattern in all_deps_text for pattern in ['pandas', 'numpy', 'scipy', 'data']):
            return 'data'
        elif any(pattern in all_deps_text for pattern in ['tensorflow', 'pytorch', 'sklearn', 'ml']):
            return 'ml'
        elif any(pattern in all_deps_text for pattern in ['kubernetes', 'docker', 'infra']):
            return 'infrastructure'
        elif any(pattern in all_deps_text for pattern in ['cryptography', 'security', 'vault']):
            return 'security'
        elif any(pattern in all_deps_text for pattern in ['prometheus', 'grafana', 'monitoring']):
            return 'observability'
        
        return 'unknown'
    
    def _determine_maturity(self, name: str, parsed: Dict[str, Any]) -> str:
        """Determine maturity level from service indicators."""
        name_lower = name.lower()
        
        # Maturity indicators
        if any(pattern in name_lower for pattern in ['experimental', 'alpha', 'prototype']):
            return 'experimental'
        elif any(pattern in name_lower for pattern in ['beta', 'preview', 'rc']):
            return 'beta'
        elif any(pattern in name_lower for pattern in ['deprecated', 'legacy', 'old']):
            return 'deprecated'
        
        return 'beta'  # Default to beta for unknown services
