"""
254Carbon Meta Repository - Service Manifest Adapters

This package contains adapters for converting various service formats
into standardized service manifests for the catalog system.

Adapters:
- DockerComposeAdapter: Extract service info from docker-compose.yml
- KubernetesAdapter: Parse k8s deployments/services
- PackageJsonAdapter: Node.js service detection
- RequirementsAdapter: Python service analysis
- GenericAdapter: Fallback heuristic-based extraction
"""

from .base_adapter import BaseAdapter, AdapterResult
from .docker_compose_adapter import DockerComposeAdapter
from .kubernetes_adapter import KubernetesAdapter
from .package_json_adapter import PackageJsonAdapter
from .requirements_adapter import RequirementsAdapter
from .generic_adapter import GenericAdapter

__all__ = [
    'BaseAdapter',
    'AdapterResult',
    'DockerComposeAdapter',
    'KubernetesAdapter',
    'PackageJsonAdapter',
    'RequirementsAdapter',
    'GenericAdapter'
]
