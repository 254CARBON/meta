#!/usr/bin/env python3
"""
Example integration of retry_decorator and cache_manager into existing scripts.

This file demonstrates how to apply the utilities to scripts that make
GitHub API calls or load catalog data repeatedly.

To integrate into actual scripts:
1. Add imports at the top of the script
2. Wrap GitHub API calls with @retry_with_backoff
3. Use cache_manager for catalog loads and API responses
"""

import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional

# Import our utilities
from scripts.utils.retry_decorator import retry_with_backoff, retry_on_rate_limit
from scripts.utils.cache_manager import CacheManager, get_cache


# ============================================================================
# Example 1: GitHub API calls with retry logic
# ============================================================================

@retry_with_backoff(
    max_attempts=3,
    backoff_factor=2,
    initial_delay=1.0,
    exceptions=(requests.RequestException, ConnectionError)
)
def fetch_github_repos(org: str, token: str) -> list:
    """
    Fetch repositories from GitHub with automatic retry.
    
    This replaces direct requests.get() calls in scripts like:
    - collect_manifests.py
    - generate_upgrade_pr.py
    - monitor_upgrade_prs.py
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    response = requests.get(
        f"https://api.github.com/orgs/{org}/repos",
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    
    return response.json()


@retry_on_rate_limit(max_attempts=5, initial_delay=60)
def fetch_github_file_content(repo: str, path: str, token: str) -> str:
    """
    Fetch file content from GitHub with rate limit handling.
    
    This is useful for:
    - collect_manifests.py (fetching service-manifest.yaml)
    - spec_version_check.py (fetching spec registry)
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw"
    }
    
    response = requests.get(
        f"https://api.github.com/repos/{repo}/contents/{path}",
        headers=headers,
        timeout=30
    )
    
    if response.status_code == 429:
        raise Exception("GitHub API rate limit exceeded")
    
    response.raise_for_status()
    return response.text


# ============================================================================
# Example 2: Catalog loading with caching
# ============================================================================

def load_catalog_with_cache(catalog_file: str = None) -> Dict[str, Any]:
    """
    Load catalog with automatic caching.
    
    This replaces direct json.load() calls in scripts like:
    - compute_quality.py
    - detect_drift.py
    - validate_graph.py
    - analyze_impact.py
    - assess_risk.py
    - And 10+ other scripts
    """
    cache = get_cache()
    
    # Try cache first
    cache_key = f"catalog:{catalog_file or 'default'}"
    cached_catalog = cache.get(cache_key)
    
    if cached_catalog is not None:
        return cached_catalog
    
    # Load from file if not cached
    if catalog_file is None:
        catalog_file = "catalog/service-index.yaml"
    
    catalog_path = Path(catalog_file)
    
    with open(catalog_path, 'r') as f:
        if catalog_path.suffix in ['.yaml', '.yml']:
            import yaml
            catalog = yaml.safe_load(f)
        else:
            catalog = json.load(f)
    
    # Cache for 1 hour
    cache.set(cache_key, catalog, ttl=3600)
    
    return catalog


def load_quality_snapshot_with_cache() -> Dict[str, Any]:
    """
    Load quality snapshot with caching.
    
    Used by multiple scripts that need quality data:
    - post_quality_summary.py
    - comment_quality_changes.py
    - create_quality_issues.py
    - generate_agent_context.py
    """
    cache = get_cache()
    
    cache_key = "quality:snapshot:latest"
    cached_snapshot = cache.get(cache_key)
    
    if cached_snapshot is not None:
        return cached_snapshot
    
    # Load from file
    snapshot_file = Path("catalog/latest_quality_snapshot.json")
    
    if not snapshot_file.exists():
        return {}
    
    with open(snapshot_file, 'r') as f:
        snapshot = json.load(f)
    
    # Cache for 30 minutes (quality data changes frequently)
    cache.set(cache_key, snapshot, ttl=1800)
    
    return snapshot


# ============================================================================
# Example 3: Combined usage in a typical script
# ============================================================================

class ServiceAnalyzer:
    """
    Example class showing how to integrate both utilities.
    
    This pattern can be applied to:
    - analyze_impact.py
    - analyze_architecture.py
    - assess_risk.py
    """
    
    def __init__(self, github_token: str):
        self.github_token = github_token
        self.cache = get_cache()
    
    def analyze_service(self, service_name: str) -> Dict[str, Any]:
        """Analyze a service with caching and retry logic."""
        # Load catalog with cache
        catalog = load_catalog_with_cache()
        
        if service_name not in catalog.get("services", {}):
            raise ValueError(f"Service {service_name} not found in catalog")
        
        service = catalog["services"][service_name]
        
        # Fetch additional data from GitHub with retry
        repo = service.get("repository")
        if repo:
            repo_data = self._fetch_repo_data_cached(repo)
        else:
            repo_data = {}
        
        # Perform analysis
        analysis = {
            "service": service_name,
            "quality_score": service.get("quality", {}).get("coverage", 0) * 100,
            "dependencies": len(service.get("dependencies", {}).get("internal", [])),
            "repo_data": repo_data
        }
        
        return analysis
    
    def _fetch_repo_data_cached(self, repo: str) -> Dict[str, Any]:
        """Fetch repository data with caching and retry."""
        cache_key = f"github:repo:{repo}"
        
        # Try cache first
        cached_data = self.cache.get(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Fetch with retry
        repo_data = self._fetch_repo_data_with_retry(repo)
        
        # Cache for 1 hour
        self.cache.set(cache_key, repo_data, ttl=3600)
        
        return repo_data
    
    @retry_with_backoff(max_attempts=3, backoff_factor=2)
    def _fetch_repo_data_with_retry(self, repo: str) -> Dict[str, Any]:
        """Fetch repository data from GitHub with retry."""
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(
            f"https://api.github.com/repos/{repo}",
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        return response.json()


# ============================================================================
# Integration Instructions for Existing Scripts
# ============================================================================

"""
To integrate these utilities into existing scripts:

1. collect_manifests.py:
   - Add: from scripts.utils.retry_decorator import retry_with_backoff
   - Wrap: fetch_manifest() method with @retry_with_backoff
   - Add: Cache for repository lists

2. compute_quality.py:
   - Add: from scripts.utils.cache_manager import get_cache
   - Replace: Direct catalog loading with load_catalog_with_cache()
   - Add: Cache quality computation results

3. detect_drift.py:
   - Add: Both retry and cache imports
   - Wrap: Spec registry fetching with @retry_with_backoff
   - Cache: Spec registry data (TTL: 1 hour)

4. generate_upgrade_pr.py:
   - Add: from scripts.utils.retry_decorator import retry_with_backoff
   - Wrap: All GitHub API calls (create PR, add labels, etc.)
   - Add: Exponential backoff for rate limits

5. monitor_upgrade_prs.py:
   - Add: Both utilities
   - Wrap: PR status checks with retry
   - Cache: PR status data (TTL: 5 minutes)

6. analyze_impact.py:
   - Add: Cache manager
   - Cache: Dependency graph (TTL: 30 minutes)
   - Cache: Impact radius calculations

7. assess_risk.py:
   - Add: Cache manager
   - Cache: Risk assessments (TTL: 15 minutes)
   - Load: Catalog with cache

8. generate_agent_context.py:
   - Add: Cache manager
   - Cache: Generated context bundles (TTL: 10 minutes)
   - Load: All data sources with cache

9. ingest_observability.py:
   - Add: Retry decorator
   - Wrap: Prometheus/Datadog API calls
   - Add: Circuit breaker for failing endpoints

10. post_quality_summary.py:
    - Add: Retry decorator
    - Wrap: Slack/notification API calls
    - Add: Fallback for notification failures

Example integration pattern:

    # Before (in any script):
    with open('catalog/service-index.yaml', 'r') as f:
        catalog = yaml.safe_load(f)
    
    response = requests.get(github_url, headers=headers)
    data = response.json()
    
    # After (with utilities):
    from scripts.utils.cache_manager import get_cache
    from scripts.utils.retry_decorator import retry_with_backoff
    
    cache = get_cache()
    catalog = cache.get('catalog') or load_and_cache_catalog()
    
    @retry_with_backoff(max_attempts=3)
    def fetch_data():
        response = requests.get(github_url, headers=headers)
        response.raise_for_status()
        return response.json()
    
    data = fetch_data()
"""


# ============================================================================
# Testing the integration
# ============================================================================

if __name__ == "__main__":
    import os
    
    print("\n=== Utility Integration Examples ===\n")
    
    # Example 1: Retry decorator
    print("1. Testing retry decorator:")
    try:
        # This will fail but demonstrate retry logic
        @retry_with_backoff(max_attempts=2, initial_delay=0.5)
        def test_retry():
            print("   Attempting operation...")
            raise ConnectionError("Simulated network error")
        
        test_retry()
    except ConnectionError as e:
        print(f"   Final failure after retries: {e}")
    
    # Example 2: Cache manager
    print("\n2. Testing cache manager:")
    cache = get_cache()
    
    # Store and retrieve
    cache.set("test_key", {"data": "test_value"}, ttl=60)
    result = cache.get("test_key")
    print(f"   Cached data: {result}")
    
    # Cache stats
    stats = cache.get_stats()
    print(f"   Cache stats: {stats['file_cache_size']} files, {stats['memory_cache_size']} in memory")
    
    # Example 3: Combined usage
    print("\n3. Testing combined usage:")
    print("   See ServiceAnalyzer class above for production example")
    
    print("\n=== Examples complete ===\n")
    print("To integrate into your scripts, follow the patterns shown above.")
