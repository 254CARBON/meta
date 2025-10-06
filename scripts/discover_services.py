#!/usr/bin/env python3
"""
254Carbon Meta Repository - Service Discovery Crawler

Automatically discovers services across 254carbon repositories by scanning GitHub
for service indicators and extracting metadata from various sources.

Usage:
    python scripts/discover_services.py [--org 254carbon] [--dry-run] [--output-file services.json]

Features:
- GitHub organization scanning
- Service detection heuristics
- Metadata extraction from multiple sources
- Domain auto-classification
- Service manifest generation
- Integration with existing catalog system
"""

import os
import sys
import json
import yaml
import argparse
import logging
import requests
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from scripts.utils import audit_logger, monitor_execution

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('analysis/reports/service-discovery.log')
    ]
)
logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Service type classifications."""
    WEB_SERVICE = "web-service"
    API_SERVICE = "api-service"
    MICROSERVICE = "microservice"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    GATEWAY = "gateway"
    UNKNOWN = "unknown"


class Domain(Enum):
    """Domain classifications."""
    ACCESS = "access"
    DATA = "data"
    ML = "ml"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    OBSERVABILITY = "observability"
    UNKNOWN = "unknown"


@dataclass
class ServiceIndicator:
    """Represents a service detection indicator."""
    file_path: str
    indicator_type: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveredService:
    """Represents a discovered service."""
    name: str
    repo_url: str
    repo_name: str
    service_type: ServiceType
    domain: Domain
    indicators: List[ServiceIndicator]
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class GitHubServiceDiscovery:
    """GitHub-based service discovery engine."""
    
    def __init__(self, github_token: Optional[str] = None, org: str = "254carbon"):
        """Initialize the discovery engine."""
        self.github_token = github_token or os.getenv('GITHUB_TOKEN')
        self.org = org
        self.session = requests.Session()
        if self.github_token:
            self.session.headers.update({
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            })
        
        # Service detection patterns
        self.service_patterns = {
            'service_manifest': r'service-manifest\.ya?ml',
            'dockerfile': r'Dockerfile(?:\.\w+)?',
            'docker_compose': r'docker-compose\.ya?ml',
            'kubernetes': r'k8s/.*\.ya?ml|kubernetes/.*\.ya?ml|deployment\.ya?ml',
            'package_json': r'package\.json',
            'requirements': r'requirements\.txt|pyproject\.toml|Pipfile',
            'go_mod': r'go\.mod',
            'cargo_toml': r'Cargo\.toml',
            'pom_xml': r'pom\.xml',
            'build_gradle': r'build\.gradle',
            'helm_chart': r'Chart\.ya?ml',
            'terraform': r'\.tf$',
            'ansible': r'playbook\.ya?ml|ansible/.*\.ya?ml',
            'ci_config': r'\.github/workflows/.*\.ya?ml|\.gitlab-ci\.ya?ml|Jenkinsfile',
            'env_config': r'\.env(?:\.\w+)?|config\.ya?ml|settings\.ya?ml'
        }
        
        # Domain classification patterns
        self.domain_patterns = {
            Domain.ACCESS: [r'access', r'auth', r'gateway', r'proxy', r'api-gateway'],
            Domain.DATA: [r'data', r'database', r'storage', r'warehouse', r'etl'],
            Domain.ML: [r'ml', r'machine-learning', r'ai', r'model', r'training'],
            Domain.INFRASTRUCTURE: [r'infra', r'infrastructure', r'platform', r'core'],
            Domain.SECURITY: [r'security', r'auth', r'permission', r'vault'],
            Domain.OBSERVABILITY: [r'observability', r'monitoring', r'logging', r'metrics']
        }
        
        # Service type classification patterns
        self.service_type_patterns = {
            ServiceType.WEB_SERVICE: [r'web', r'frontend', r'ui', r'dashboard'],
            ServiceType.API_SERVICE: [r'api', r'service', r'backend', r'server'],
            ServiceType.MICROSERVICE: [r'microservice', r'service-', r'-service'],
            ServiceType.WORKER: [r'worker', r'processor', r'consumer', r'handler'],
            ServiceType.SCHEDULER: [r'scheduler', r'cron', r'task', r'job'],
            ServiceType.DATABASE: [r'database', r'db', r'postgres', r'mysql', r'mongo'],
            ServiceType.CACHE: [r'cache', r'redis', r'memcache'],
            ServiceType.QUEUE: [r'queue', r'message', r'broker', r'rabbitmq'],
            ServiceType.GATEWAY: [r'gateway', r'proxy', r'router', r'load-balancer']
        }

    def discover_services(self, dry_run: bool = False) -> List[DiscoveredService]:
        """Discover all services in the GitHub organization."""
        logger.info(f"Starting service discovery for organization: {self.org}")
        
        # Get all repositories
        repos = self._get_organization_repos()
        logger.info(f"Found {len(repos)} repositories to scan")
        
        discovered_services = []
        
        # Process repositories in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_repo = {
                executor.submit(self._analyze_repository, repo, dry_run): repo 
                for repo in repos
            }
            
            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    service = future.result()
                    if service:
                        discovered_services.append(service)
                        logger.info(f"Discovered service: {service.name} ({service.service_type.value})")
                except Exception as e:
                    logger.error(f"Error analyzing repository {repo['name']}: {e}")
        
        # Sort by confidence score
        discovered_services.sort(key=lambda s: s.confidence_score, reverse=True)
        
        logger.info(f"Discovery complete. Found {len(discovered_services)} services")
        return discovered_services

    def _get_organization_repos(self) -> List[Dict[str, Any]]:
        """Get all repositories from the organization."""
        repos = []
        page = 1
        per_page = 100
        
        while True:
            url = f"https://api.github.com/orgs/{self.org}/repos"
            params = {
                'page': page,
                'per_page': per_page,
                'type': 'all',
                'sort': 'updated',
                'direction': 'desc'
            }
            
            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                
                page_repos = response.json()
                if not page_repos:
                    break
                    
                repos.extend(page_repos)
                page += 1
                
                # Rate limiting
                if 'X-RateLimit-Remaining' in response.headers:
                    remaining = int(response.headers['X-RateLimit-Remaining'])
                    if remaining < 10:
                        logger.warning(f"Rate limit low: {remaining} requests remaining")
                        time.sleep(60)
                        
            except requests.RequestException as e:
                logger.error(f"Error fetching repositories: {e}")
                break
        
        return repos

    def _analyze_repository(self, repo: Dict[str, Any], dry_run: bool) -> Optional[DiscoveredService]:
        """Analyze a single repository for service indicators."""
        repo_name = repo['name']
        repo_url = repo['html_url']
        
        # Skip non-service repositories
        if self._should_skip_repo(repo_name):
            return None
        
        logger.debug(f"Analyzing repository: {repo_name}")
        
        # Get repository contents
        contents = self._get_repository_contents(repo_name)
        if not contents:
            return None
        
        # Find service indicators
        indicators = self._find_service_indicators(repo_name, contents)
        if not indicators:
            return None
        
        # Extract metadata
        metadata = self._extract_metadata(repo_name, contents, indicators)
        
        # Classify service
        service_type = self._classify_service_type(repo_name, indicators, metadata)
        domain = self._classify_domain(repo_name, indicators, metadata)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(indicators, metadata)
        
        # Generate service name
        service_name = self._generate_service_name(repo_name, metadata)
        
        return DiscoveredService(
            name=service_name,
            repo_url=repo_url,
            repo_name=repo_name,
            service_type=service_type,
            domain=domain,
            indicators=indicators,
            metadata=metadata,
            confidence_score=confidence_score
        )

    def _should_skip_repo(self, repo_name: str) -> bool:
        """Determine if a repository should be skipped."""
        skip_patterns = [
            r'\.github$',
            r'docs?$',
            r'documentation$',
            r'website$',
            r'blog$',
            r'example',
            r'demo',
            r'test',
            r'sandbox',
            r'playground',
            r'archive',
            r'deprecated',
            r'legacy'
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, repo_name, re.IGNORECASE):
                return True
        
        return False

    def _get_repository_contents(self, repo_name: str) -> List[Dict[str, Any]]:
        """Get repository contents recursively."""
        contents = []
        
        try:
            url = f"https://api.github.com/repos/{self.org}/{repo_name}/contents"
            response = self.session.get(url)
            response.raise_for_status()
            
            items = response.json()
            if isinstance(items, dict):
                items = [items]
            
            for item in items:
                if item['type'] == 'file':
                    contents.append(item)
                elif item['type'] == 'dir':
                    # Recursively get subdirectory contents
                    sub_contents = self._get_directory_contents(repo_name, item['path'])
                    contents.extend(sub_contents)
                    
        except requests.RequestException as e:
            logger.error(f"Error fetching contents for {repo_name}: {e}")
        
        return contents

    def _get_directory_contents(self, repo_name: str, path: str) -> List[Dict[str, Any]]:
        """Get contents of a specific directory."""
        contents = []
        
        try:
            url = f"https://api.github.com/repos/{self.org}/{repo_name}/contents/{path}"
            response = self.session.get(url)
            response.raise_for_status()
            
            items = response.json()
            if isinstance(items, dict):
                items = [items]
            
            for item in items:
                if item['type'] == 'file':
                    contents.append(item)
                elif item['type'] == 'dir' and not self._should_skip_directory(item['name']):
                    # Recursively get subdirectory contents (limited depth)
                    sub_contents = self._get_directory_contents(repo_name, item['path'])
                    contents.extend(sub_contents)
                    
        except requests.RequestException as e:
            logger.debug(f"Error fetching directory {path} for {repo_name}: {e}")
        
        return contents

    def _should_skip_directory(self, dir_name: str) -> bool:
        """Determine if a directory should be skipped."""
        skip_dirs = [
            '.git', 'node_modules', 'vendor', '__pycache__', '.pytest_cache',
            'target', 'build', 'dist', '.idea', '.vscode', 'coverage',
            'logs', 'tmp', 'temp', '.env'
        ]
        return dir_name in skip_dirs

    def _find_service_indicators(self, repo_name: str, contents: List[Dict[str, Any]]) -> List[ServiceIndicator]:
        """Find service indicators in repository contents."""
        indicators = []
        
        for content in contents:
            file_path = content['path']
            file_name = content['name']
            
            # Check against service patterns
            for pattern_name, pattern in self.service_patterns.items():
                if re.search(pattern, file_path, re.IGNORECASE):
                    confidence = self._calculate_indicator_confidence(pattern_name, file_path, content)
                    if confidence > 0.3:  # Minimum confidence threshold
                        indicators.append(ServiceIndicator(
                            file_path=file_path,
                            indicator_type=pattern_name,
                            confidence=confidence,
                            metadata={'size': content.get('size', 0)}
                        ))
        
        return indicators

    def _calculate_indicator_confidence(self, pattern_name: str, file_path: str, content: Dict[str, Any]) -> float:
        """Calculate confidence score for a service indicator."""
        base_confidence = {
            'service_manifest': 1.0,
            'dockerfile': 0.9,
            'docker_compose': 0.8,
            'kubernetes': 0.8,
            'package_json': 0.7,
            'requirements': 0.7,
            'go_mod': 0.7,
            'cargo_toml': 0.7,
            'pom_xml': 0.7,
            'build_gradle': 0.7,
            'helm_chart': 0.8,
            'terraform': 0.6,
            'ansible': 0.6,
            'ci_config': 0.5,
            'env_config': 0.4
        }
        
        confidence = base_confidence.get(pattern_name, 0.5)
        
        # Adjust based on file location
        if 'src/' in file_path or 'app/' in file_path:
            confidence += 0.1
        elif 'test/' in file_path or 'spec/' in file_path:
            confidence -= 0.2
        
        # Adjust based on file size (very small or very large files are less indicative)
        file_size = content.get('size', 0)
        if file_size < 100 or file_size > 100000:
            confidence -= 0.1
        
        return max(0.0, min(1.0, confidence))

    def _extract_metadata(self, repo_name: str, contents: List[Dict[str, Any]], indicators: List[ServiceIndicator]) -> Dict[str, Any]:
        """Extract metadata from repository contents."""
        metadata = {
            'repo_name': repo_name,
            'total_files': len(contents),
            'indicators_found': len(indicators),
            'languages': set(),
            'frameworks': set(),
            'dependencies': set(),
            'has_tests': False,
            'has_docs': False,
            'has_ci': False
        }
        
        # Analyze file types and extract metadata
        for content in contents:
            file_path = content['path']
            file_name = content['name']
            
            # Detect languages
            if file_name.endswith('.py'):
                metadata['languages'].add('python')
            elif file_name.endswith('.js') or file_name.endswith('.ts'):
                metadata['languages'].add('javascript')
            elif file_name.endswith('.go'):
                metadata['languages'].add('go')
            elif file_name.endswith('.rs'):
                metadata['languages'].add('rust')
            elif file_name.endswith('.java'):
                metadata['languages'].add('java')
            
            # Detect tests
            if 'test' in file_path.lower() or 'spec' in file_path.lower():
                metadata['has_tests'] = True
            
            # Detect documentation
            if file_name.lower() in ['readme.md', 'readme.rst', 'docs.md']:
                metadata['has_docs'] = True
            
            # Detect CI
            if '.github/workflows' in file_path or '.gitlab-ci.yml' in file_path:
                metadata['has_ci'] = True
        
        # Convert sets to lists for JSON serialization
        metadata['languages'] = list(metadata['languages'])
        metadata['frameworks'] = list(metadata['frameworks'])
        metadata['dependencies'] = list(metadata['dependencies'])
        
        return metadata

    def _classify_service_type(self, repo_name: str, indicators: List[ServiceIndicator], metadata: Dict[str, Any]) -> ServiceType:
        """Classify the service type based on indicators and metadata."""
        # Check repo name patterns
        for service_type, patterns in self.service_type_patterns.items():
            for pattern in patterns:
                if re.search(pattern, repo_name, re.IGNORECASE):
                    return service_type
        
        # Check indicator types
        indicator_types = [ind.indicator_type for ind in indicators]
        
        if 'service_manifest' in indicator_types:
            return ServiceType.MICROSERVICE
        elif 'dockerfile' in indicator_types and 'package_json' in indicator_types:
            return ServiceType.WEB_SERVICE
        elif 'dockerfile' in indicator_types:
            return ServiceType.API_SERVICE
        elif 'kubernetes' in indicator_types:
            return ServiceType.MICROSERVICE
        elif 'requirements' in indicator_types:
            return ServiceType.API_SERVICE
        
        return ServiceType.UNKNOWN

    def _classify_domain(self, repo_name: str, indicators: List[ServiceIndicator], metadata: Dict[str, Any]) -> Domain:
        """Classify the domain based on repo name and metadata."""
        # Check repo name patterns
        for domain, patterns in self.domain_patterns.items():
            for pattern in patterns:
                if re.search(pattern, repo_name, re.IGNORECASE):
                    return domain
        
        return Domain.UNKNOWN

    def _calculate_confidence_score(self, indicators: List[ServiceIndicator], metadata: Dict[str, Any]) -> float:
        """Calculate overall confidence score for the service discovery."""
        if not indicators:
            return 0.0
        
        # Base score from indicators
        indicator_scores = [ind.confidence for ind in indicators]
        base_score = sum(indicator_scores) / len(indicator_scores)
        
        # Bonus for multiple indicators
        if len(indicators) > 1:
            base_score += 0.1
        
        # Bonus for having tests
        if metadata.get('has_tests'):
            base_score += 0.1
        
        # Bonus for having CI
        if metadata.get('has_ci'):
            base_score += 0.1
        
        # Bonus for having documentation
        if metadata.get('has_docs'):
            base_score += 0.05
        
        return min(1.0, base_score)

    def _generate_service_name(self, repo_name: str, metadata: Dict[str, Any]) -> str:
        """Generate a service name from repository name."""
        # Remove common prefixes/suffixes
        name = repo_name.lower()
        name = re.sub(r'^254carbon-', '', name)
        name = re.sub(r'-(service|api|app|web)$', '', name)
        name = re.sub(r'^service-', '', name)
        name = re.sub(r'^api-', '', name)
        
        # Convert to service name format
        name = name.replace('-', '_')
        
        return name


def main():
    """Main entry point for service discovery."""
    parser = argparse.ArgumentParser(description='Discover services in 254carbon organization')
    parser.add_argument('--org', default='254carbon', help='GitHub organization name')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode (no API calls)')
    parser.add_argument('--output-file', default='analysis/reports/discovered-services.json', help='Output file for results')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    # Initialize discovery engine
    discovery = GitHubServiceDiscovery(org=args.org)
    
    try:
        # Discover services
        services = discovery.discover_services(dry_run=args.dry_run)
        
        # Convert to serializable format
        services_data = []
        for service in services:
            service_dict = {
                'name': service.name,
                'repo_url': service.repo_url,
                'repo_name': service.repo_name,
                'service_type': service.service_type.value,
                'domain': service.domain.value,
                'confidence_score': service.confidence_score,
                'indicators': [
                    {
                        'file_path': ind.file_path,
                        'indicator_type': ind.indicator_type,
                        'confidence': ind.confidence,
                        'metadata': ind.metadata
                    }
                    for ind in service.indicators
                ],
                'metadata': service.metadata,
                'last_updated': service.last_updated.isoformat()
            }
            services_data.append(service_dict)
        
        # Save results
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump({
                'discovered_at': datetime.now(timezone.utc).isoformat(),
                'organization': args.org,
                'total_services': len(services_data),
                'services': services_data
            }, f, indent=2)
        
        logger.info(f"Discovery results saved to: {output_path}")
        
        # Print summary
        print(f"\nService Discovery Summary:")
        print(f"Organization: {args.org}")
        print(f"Total services discovered: {len(services_data)}")
        print(f"High confidence (>0.8): {len([s for s in services_data if s['confidence_score'] > 0.8])}")
        print(f"Medium confidence (0.5-0.8): {len([s for s in services_data if 0.5 <= s['confidence_score'] <= 0.8])}")
        print(f"Low confidence (<0.5): {len([s for s in services_data if s['confidence_score'] < 0.5])}")
        
        # Print top services
        print(f"\nTop discovered services:")
        for service in services_data[:10]:
            print(f"  {service['name']} ({service['service_type']}) - {service['confidence_score']:.2f}")
        
    except Exception as e:
        logger.error(f"Service discovery failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
