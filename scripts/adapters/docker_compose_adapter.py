#!/usr/bin/env python3
"""
Docker Compose adapter for service manifest generation.

Extracts service information from docker-compose.yml files.
"""

import re
from typing import Dict, List, Any, Optional
from .base_adapter import BaseAdapter, AdapterResult


class DockerComposeAdapter(BaseAdapter):
    """Adapter for Docker Compose files."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the Docker Compose adapter."""
        super().__init__(config)
        self.supported_extensions = ['.yml', '.yaml']
        self.supported_files = ['docker-compose.yml', 'docker-compose.yaml']
    
    def can_process(self, file_path: str, content: str) -> bool:
        """Check if this adapter can process the file."""
        file_path_lower = file_path.lower()
        
        # Check if it's a docker-compose file
        if any(filename in file_path_lower for filename in self.supported_files):
            return True
        
        # Check for docker-compose indicators in content
        if 'docker-compose' in content.lower() or 'version:' in content:
            try:
                parsed = self._parse_yaml(content)
                if parsed and 'services' in parsed:
                    return True
            except:
                pass
        
        return False
    
    def extract_manifest(self, file_path: str, content: str, 
                        repo_metadata: Optional[Dict[str, Any]] = None) -> AdapterResult:
        """Extract service manifest from Docker Compose file."""
        try:
            parsed = self._parse_yaml(content)
            if not parsed:
                return AdapterResult(
                    success=False,
                    errors=["Failed to parse YAML content"]
                )
            
            # Extract services
            services = parsed.get('services', {})
            if not services:
                return AdapterResult(
                    success=False,
                    errors=["No services found in docker-compose file"]
                )
            
            # Process the first service (or primary service)
            primary_service = self._find_primary_service(services)
            if not primary_service:
                return AdapterResult(
                    success=False,
                    errors=["No primary service identified"]
                )
            
            service_name, service_config = primary_service
            
            # Extract manifest information
            manifest = self._extract_service_manifest(
                service_name, service_config, parsed, repo_metadata
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
                confidence=0.8,
                metadata={
                    'total_services': len(services),
                    'primary_service': service_name,
                    'extracted_from': 'docker-compose'
                }
            )
            
        except Exception as e:
            return AdapterResult(
                success=False,
                errors=[f"Error processing docker-compose file: {str(e)}"]
            )
    
    def _find_primary_service(self, services: Dict[str, Any]) -> Optional[tuple]:
        """Find the primary service in the compose file."""
        if not services:
            return None
        
        # Look for common primary service names
        primary_patterns = [
            'app', 'web', 'api', 'server', 'main', 'primary',
            'gateway', 'service', 'backend', 'frontend'
        ]
        
        # Check for exact matches first
        for pattern in primary_patterns:
            for service_name in services.keys():
                if service_name.lower() == pattern:
                    return (service_name, services[service_name])
        
        # Check for partial matches
        for pattern in primary_patterns:
            for service_name in services.keys():
                if pattern in service_name.lower():
                    return (service_name, services[service_name])
        
        # Return the first service if no pattern matches
        first_service = list(services.items())[0]
        return first_service
    
    def _extract_service_manifest(self, service_name: str, service_config: Dict[str, Any],
                                 compose_config: Dict[str, Any],
                                 repo_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract service manifest from service configuration."""
        
        # Extract basic information
        name = self._clean_service_name(service_name)
        version = self._extract_version(service_config, compose_config)
        runtime = self._determine_runtime_from_image(service_config)
        domain = self._determine_domain(name, service_config)
        maturity = self._determine_maturity(name, service_config)
        
        # Extract dependencies
        dependencies = self._extract_dependencies(service_config, compose_config)
        
        # Extract additional metadata
        additional_fields = {
            'dependencies': dependencies,
            'ports': self._extract_ports(service_config),
            'environment': self._extract_environment(service_config),
            'volumes': self._extract_volumes(service_config),
            'networks': self._extract_networks(service_config),
            'health_check': self._extract_health_check(service_config)
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
    
    def _clean_service_name(self, name: str) -> str:
        """Clean and normalize service name."""
        # Remove common prefixes/suffixes
        name = re.sub(r'^254carbon-', '', name)
        name = re.sub(r'-(service|api|app|web)$', '', name)
        name = re.sub(r'^service-', '', name)
        name = re.sub(r'^api-', '', name)
        
        # Convert to service name format
        name = name.replace('-', '_')
        return name.lower()
    
    def _extract_version(self, service_config: Dict[str, Any], 
                        compose_config: Dict[str, Any]) -> str:
        """Extract version from service configuration."""
        # Check for version in image tag
        image = service_config.get('image', '')
        if ':' in image:
            tag = image.split(':')[-1]
            if re.match(r'^\d+\.\d+\.\d+', tag):
                return tag
        
        # Check for version in environment variables
        environment = service_config.get('environment', {})
        if isinstance(environment, dict):
            for key, value in environment.items():
                if 'version' in key.lower() and isinstance(value, str):
                    if re.match(r'^\d+\.\d+\.\d+', value):
                        return value
        
        # Check for version in labels
        labels = service_config.get('labels', {})
        if isinstance(labels, dict):
            for key, value in labels.items():
                if 'version' in key.lower() and isinstance(value, str):
                    if re.match(r'^\d+\.\d+\.\d+', value):
                        return value
        
        # Default version
        return '1.0.0'
    
    def _determine_runtime_from_image(self, service_config: Dict[str, Any]) -> str:
        """Determine runtime from Docker image."""
        image = service_config.get('image', '').lower()
        
        # Common runtime patterns in images
        if any(pattern in image for pattern in ['python', 'django', 'flask', 'fastapi']):
            return 'python'
        elif any(pattern in image for pattern in ['node', 'npm', 'yarn', 'express']):
            return 'nodejs'
        elif any(pattern in image for pattern in ['golang', 'go']):
            return 'go'
        elif any(pattern in image for pattern in ['rust', 'cargo']):
            return 'rust'
        elif any(pattern in image for pattern in ['java', 'openjdk', 'maven']):
            return 'java'
        elif any(pattern in image for pattern in ['dotnet', 'aspnet']):
            return 'dotnet'
        elif any(pattern in image for pattern in ['php', 'apache', 'nginx']):
            return 'php'
        elif any(pattern in image for pattern in ['ruby', 'rails']):
            return 'ruby'
        
        return 'unknown'
    
    def _extract_dependencies(self, service_config: Dict[str, Any], 
                             compose_config: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract service dependencies."""
        dependencies = {
            'internal': [],
            'external': []
        }
        
        # Check for depends_on
        depends_on = service_config.get('depends_on', [])
        if isinstance(depends_on, list):
            for dep in depends_on:
                if isinstance(dep, str):
                    dependencies['internal'].append(dep)
        
        # Check for external services (databases, caches, etc.)
        external_services = ['postgres', 'mysql', 'redis', 'mongodb', 'elasticsearch', 'rabbitmq']
        for service_name in compose_config.get('services', {}).keys():
            if any(ext in service_name.lower() for ext in external_services):
                dependencies['external'].append(service_name)
        
        # Check for external dependencies in environment
        environment = service_config.get('environment', {})
        if isinstance(environment, dict):
            for key, value in environment.items():
                if any(ext in str(value).lower() for ext in external_services):
                    dependencies['external'].append(str(value))
        
        return dependencies
    
    def _extract_ports(self, service_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract port information."""
        ports = []
        port_config = service_config.get('ports', [])
        
        if isinstance(port_config, list):
            for port in port_config:
                if isinstance(port, str):
                    # Parse "host:container" format
                    if ':' in port:
                        host_port, container_port = port.split(':', 1)
                        ports.append({
                            'host_port': int(host_port),
                            'container_port': int(container_port)
                        })
                    else:
                        ports.append({
                            'container_port': int(port)
                        })
        
        return ports
    
    def _extract_environment(self, service_config: Dict[str, Any]) -> Dict[str, str]:
        """Extract environment variables."""
        environment = service_config.get('environment', {})
        
        if isinstance(environment, dict):
            return {k: str(v) for k, v in environment.items()}
        elif isinstance(environment, list):
            env_dict = {}
            for item in environment:
                if isinstance(item, str) and '=' in item:
                    key, value = item.split('=', 1)
                    env_dict[key] = value
            return env_dict
        
        return {}
    
    def _extract_volumes(self, service_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract volume information."""
        volumes = []
        volume_config = service_config.get('volumes', [])
        
        if isinstance(volume_config, list):
            for volume in volume_config:
                if isinstance(volume, str):
                    # Parse "host:container" format
                    if ':' in volume:
                        host_path, container_path = volume.split(':', 1)
                        volumes.append({
                            'host_path': host_path,
                            'container_path': container_path
                        })
                    else:
                        volumes.append({
                            'container_path': volume
                        })
        
        return volumes
    
    def _extract_networks(self, service_config: Dict[str, Any]) -> List[str]:
        """Extract network information."""
        networks = service_config.get('networks', [])
        
        if isinstance(networks, list):
            return networks
        elif isinstance(networks, dict):
            return list(networks.keys())
        
        return []
    
    def _extract_health_check(self, service_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract health check configuration."""
        healthcheck = service_config.get('healthcheck', {})
        
        if healthcheck:
            return {
                'test': healthcheck.get('test'),
                'interval': healthcheck.get('interval'),
                'timeout': healthcheck.get('timeout'),
                'retries': healthcheck.get('retries'),
                'start_period': healthcheck.get('start_period')
            }
        
        return None
