#!/usr/bin/env python3
"""
Kubernetes adapter for service manifest generation.

Extracts service information from Kubernetes deployment and service files.
"""

import re
from typing import Dict, List, Any, Optional
from .base_adapter import BaseAdapter, AdapterResult


class KubernetesAdapter(BaseAdapter):
    """Adapter for Kubernetes files."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the Kubernetes adapter."""
        super().__init__(config)
        self.supported_extensions = ['.yml', '.yaml']
        self.supported_files = ['deployment.yaml', 'service.yaml', 'k8s.yaml']
    
    def can_process(self, file_path: str, content: str) -> bool:
        """Check if this adapter can process the file."""
        file_path_lower = file_path.lower()
        
        # Check if it's a Kubernetes file
        if any(pattern in file_path_lower for pattern in ['k8s/', 'kubernetes/', 'deployment.yaml', 'service.yaml']):
            return True
        
        # Check for Kubernetes indicators in content
        try:
            parsed = self._parse_yaml(content)
            if parsed:
                # Check for Kubernetes API version
                if 'apiVersion' in parsed and 'kind' in parsed:
                    api_version = parsed['apiVersion']
                    kind = parsed['kind']
                    
                    # Common Kubernetes resources
                    k8s_resources = [
                        'Deployment', 'Service', 'ConfigMap', 'Secret',
                        'Ingress', 'StatefulSet', 'DaemonSet', 'Job',
                        'CronJob', 'Pod', 'ReplicaSet'
                    ]
                    
                    if any(resource in kind for resource in k8s_resources):
                        return True
        except:
            pass
        
        return False
    
    def extract_manifest(self, file_path: str, content: str, 
                        repo_metadata: Optional[Dict[str, Any]] = None) -> AdapterResult:
        """Extract service manifest from Kubernetes file."""
        try:
            parsed = self._parse_yaml(content)
            if not parsed:
                return AdapterResult(
                    success=False,
                    errors=["Failed to parse YAML content"]
                )
            
            # Handle single document
            if isinstance(parsed, dict):
                parsed = [parsed]
            
            # Find primary deployment/service
            primary_resource = self._find_primary_resource(parsed)
            if not primary_resource:
                return AdapterResult(
                    success=False,
                    errors=["No primary Kubernetes resource found"]
                )
            
            # Extract manifest information
            manifest = self._extract_service_manifest(
                primary_resource, parsed, repo_metadata
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
                    'total_resources': len(parsed),
                    'primary_resource': primary_resource.get('kind'),
                    'extracted_from': 'kubernetes'
                }
            )
            
        except Exception as e:
            return AdapterResult(
                success=False,
                errors=[f"Error processing Kubernetes file: {str(e)}"]
            )
    
    def _find_primary_resource(self, resources: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find the primary Kubernetes resource."""
        if not resources:
            return None
        
        # Priority order for resource types
        priority_order = ['Deployment', 'StatefulSet', 'DaemonSet', 'Service', 'Pod']
        
        # Look for resources in priority order
        for resource_type in priority_order:
            for resource in resources:
                if resource.get('kind') == resource_type:
                    return resource
        
        # Return the first resource if no priority match
        return resources[0]
    
    def _extract_service_manifest(self, primary_resource: Dict[str, Any],
                                 all_resources: List[Dict[str, Any]],
                                 repo_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract service manifest from Kubernetes resource."""
        
        # Extract basic information
        name = self._extract_name(primary_resource)
        version = self._extract_version(primary_resource)
        runtime = self._determine_runtime_from_image(primary_resource)
        domain = self._determine_domain(name, primary_resource)
        maturity = self._determine_maturity(name, primary_resource)
        
        # Extract dependencies
        dependencies = self._extract_dependencies(primary_resource, all_resources)
        
        # Extract additional metadata
        additional_fields = {
            'dependencies': dependencies,
            'replicas': self._extract_replicas(primary_resource),
            'ports': self._extract_ports(primary_resource, all_resources),
            'environment': self._extract_environment(primary_resource),
            'volumes': self._extract_volumes(primary_resource),
            'resources': self._extract_resources(primary_resource),
            'health_checks': self._extract_health_checks(primary_resource)
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
    
    def _extract_name(self, resource: Dict[str, Any]) -> str:
        """Extract service name from Kubernetes resource."""
        name = resource.get('metadata', {}).get('name', '')
        
        # Clean and normalize name
        name = re.sub(r'^254carbon-', '', name)
        name = re.sub(r'-(service|api|app|web|deployment)$', '', name)
        name = re.sub(r'^service-', '', name)
        name = re.sub(r'^api-', '', name)
        
        # Convert to service name format
        name = name.replace('-', '_')
        return name.lower()
    
    def _extract_version(self, resource: Dict[str, Any]) -> str:
        """Extract version from Kubernetes resource."""
        metadata = resource.get('metadata', {})
        
        # Check labels
        labels = metadata.get('labels', {})
        if 'version' in labels:
            version = labels['version']
            if re.match(r'^\d+\.\d+\.\d+', version):
                return version
        
        # Check annotations
        annotations = metadata.get('annotations', {})
        if 'version' in annotations:
            version = annotations['version']
            if re.match(r'^\d+\.\d+\.\d+', version):
                return version
        
        # Check image tag
        image = self._extract_image(resource)
        if image and ':' in image:
            tag = image.split(':')[-1]
            if re.match(r'^\d+\.\d+\.\d+', tag):
                return tag
        
        # Default version
        return '1.0.0'
    
    def _extract_image(self, resource: Dict[str, Any]) -> Optional[str]:
        """Extract container image from Kubernetes resource."""
        spec = resource.get('spec', {})
        
        # Check for containers
        containers = spec.get('containers', [])
        if containers and len(containers) > 0:
            return containers[0].get('image')
        
        # Check for template containers (Deployment, StatefulSet, etc.)
        template = spec.get('template', {})
        template_spec = template.get('spec', {})
        template_containers = template_spec.get('containers', [])
        if template_containers and len(template_containers) > 0:
            return template_containers[0].get('image')
        
        return None
    
    def _determine_runtime_from_image(self, resource: Dict[str, Any]) -> str:
        """Determine runtime from container image."""
        image = self._extract_image(resource)
        if not image:
            return 'unknown'
        
        image_lower = image.lower()
        
        # Common runtime patterns in images
        if any(pattern in image_lower for pattern in ['python', 'django', 'flask', 'fastapi']):
            return 'python'
        elif any(pattern in image_lower for pattern in ['node', 'npm', 'yarn', 'express']):
            return 'nodejs'
        elif any(pattern in image_lower for pattern in ['golang', 'go']):
            return 'go'
        elif any(pattern in image_lower for pattern in ['rust', 'cargo']):
            return 'rust'
        elif any(pattern in image_lower for pattern in ['java', 'openjdk', 'maven']):
            return 'java'
        elif any(pattern in image_lower for pattern in ['dotnet', 'aspnet']):
            return 'dotnet'
        elif any(pattern in image_lower for pattern in ['php', 'apache', 'nginx']):
            return 'php'
        elif any(pattern in image_lower for pattern in ['ruby', 'rails']):
            return 'ruby'
        
        return 'unknown'
    
    def _extract_dependencies(self, primary_resource: Dict[str, Any], 
                             all_resources: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Extract service dependencies."""
        dependencies = {
            'internal': [],
            'external': []
        }
        
        # Check for service dependencies
        for resource in all_resources:
            if resource.get('kind') == 'Service':
                service_name = resource.get('metadata', {}).get('name', '')
                if service_name and service_name != primary_resource.get('metadata', {}).get('name'):
                    dependencies['internal'].append(service_name)
        
        # Check for external dependencies (databases, caches, etc.)
        external_services = ['postgres', 'mysql', 'redis', 'mongodb', 'elasticsearch', 'rabbitmq']
        for resource in all_resources:
            resource_name = resource.get('metadata', {}).get('name', '').lower()
            if any(ext in resource_name for ext in external_services):
                dependencies['external'].append(resource_name)
        
        return dependencies
    
    def _extract_replicas(self, resource: Dict[str, Any]) -> int:
        """Extract replica count."""
        spec = resource.get('spec', {})
        
        # Direct replicas
        if 'replicas' in spec:
            return spec['replicas']
        
        # Template replicas
        template = spec.get('template', {})
        template_spec = template.get('spec', {})
        if 'replicas' in template_spec:
            return template_spec['replicas']
        
        return 1  # Default
    
    def _extract_ports(self, primary_resource: Dict[str, Any], 
                      all_resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract port information."""
        ports = []
        
        # Check primary resource for ports
        spec = primary_resource.get('spec', {})
        containers = spec.get('containers', [])
        
        for container in containers:
            container_ports = container.get('ports', [])
            for port in container_ports:
                ports.append({
                    'container_port': port.get('containerPort'),
                    'protocol': port.get('protocol', 'TCP'),
                    'name': port.get('name')
                })
        
        # Check for Service resources
        for resource in all_resources:
            if resource.get('kind') == 'Service':
                service_spec = resource.get('spec', {})
                service_ports = service_spec.get('ports', [])
                for port in service_ports:
                    ports.append({
                        'service_port': port.get('port'),
                        'target_port': port.get('targetPort'),
                        'protocol': port.get('protocol', 'TCP'),
                        'name': port.get('name')
                    })
        
        return ports
    
    def _extract_environment(self, resource: Dict[str, Any]) -> Dict[str, str]:
        """Extract environment variables."""
        environment = {}
        
        spec = resource.get('spec', {})
        containers = spec.get('containers', [])
        
        for container in containers:
            env_vars = container.get('env', [])
            for env_var in env_vars:
                if isinstance(env_var, dict) and 'name' in env_var and 'value' in env_var:
                    environment[env_var['name']] = str(env_var['value'])
        
        return environment
    
    def _extract_volumes(self, resource: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract volume information."""
        volumes = []
        
        spec = resource.get('spec', {})
        
        # Pod volumes
        pod_volumes = spec.get('volumes', [])
        for volume in pod_volumes:
            volume_info = {'name': volume.get('name')}
            
            # Check volume types
            if 'configMap' in volume:
                volume_info['type'] = 'configMap'
                volume_info['config_map'] = volume['configMap']
            elif 'secret' in volume:
                volume_info['type'] = 'secret'
                volume_info['secret'] = volume['secret']
            elif 'persistentVolumeClaim' in volume:
                volume_info['type'] = 'persistentVolumeClaim'
                volume_info['pvc'] = volume['persistentVolumeClaim']
            elif 'emptyDir' in volume:
                volume_info['type'] = 'emptyDir'
                volume_info['empty_dir'] = volume['emptyDir']
            
            volumes.append(volume_info)
        
        return volumes
    
    def _extract_resources(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Extract resource requirements."""
        resources_info = {}
        
        spec = resource.get('spec', {})
        containers = spec.get('containers', [])
        
        for container in containers:
            resources = container.get('resources', {})
            if resources:
                resources_info[container.get('name', 'default')] = {
                    'requests': resources.get('requests', {}),
                    'limits': resources.get('limits', {})
                }
        
        return resources_info
    
    def _extract_health_checks(self, resource: Dict[str, Any]) -> Dict[str, Any]:
        """Extract health check configuration."""
        health_checks = {}
        
        spec = resource.get('spec', {})
        containers = spec.get('containers', [])
        
        for container in containers:
            container_name = container.get('name', 'default')
            
            # Liveness probe
            liveness_probe = container.get('livenessProbe')
            if liveness_probe:
                health_checks[f'{container_name}_liveness'] = {
                    'type': 'liveness',
                    'initial_delay_seconds': liveness_probe.get('initialDelaySeconds'),
                    'period_seconds': liveness_probe.get('periodSeconds'),
                    'timeout_seconds': liveness_probe.get('timeoutSeconds'),
                    'success_threshold': liveness_probe.get('successThreshold'),
                    'failure_threshold': liveness_probe.get('failureThreshold')
                }
            
            # Readiness probe
            readiness_probe = container.get('readinessProbe')
            if readiness_probe:
                health_checks[f'{container_name}_readiness'] = {
                    'type': 'readiness',
                    'initial_delay_seconds': readiness_probe.get('initialDelaySeconds'),
                    'period_seconds': readiness_probe.get('periodSeconds'),
                    'timeout_seconds': readiness_probe.get('timeoutSeconds'),
                    'success_threshold': readiness_probe.get('successThreshold'),
                    'failure_threshold': readiness_probe.get('failureThreshold')
                }
        
        return health_checks
