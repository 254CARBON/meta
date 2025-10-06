#!/usr/bin/env python3
"""
Cache Manager for 254Carbon Meta Scripts

Provides file-based and in-memory caching to improve performance and reduce
redundant API calls. Implements TTL (time-to-live) and automatic cleanup.

Usage:
    from scripts.utils.cache_manager import CacheManager
    
    cache = CacheManager(cache_dir="/tmp/meta-cache", default_ttl=3600)
    
    # Store data
    cache.set("catalog", catalog_data, ttl=7200)
    
    # Retrieve data
    catalog = cache.get("catalog")
    if catalog is None:
        catalog = load_catalog()  # Expensive operation
        cache.set("catalog", catalog)
"""

import os
import json
import pickle
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Dict
from threading import Lock

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages file-based and in-memory caching with TTL support.
    
    Features:
    - File-based persistent cache
    - In-memory cache for hot data
    - TTL (time-to-live) support
    - Automatic expiration cleanup
    - Thread-safe operations
    """
    
    def __init__(
        self,
        cache_dir: str = None,
        default_ttl: int = 3600,
        max_memory_items: int = 100,
        enable_memory_cache: bool = True
    ):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Directory for file-based cache (default: /tmp/meta-cache)
            default_ttl: Default time-to-live in seconds (default: 1 hour)
            max_memory_items: Maximum items in memory cache
            enable_memory_cache: Whether to use in-memory caching
        """
        # Set up cache directory
        if cache_dir is None:
            cache_dir = os.environ.get('META_CACHE_DIR', '/tmp/meta-cache')
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.default_ttl = default_ttl
        self.max_memory_items = max_memory_items
        self.enable_memory_cache = enable_memory_cache
        
        # In-memory cache
        self._memory_cache: Dict[str, tuple] = {}  # key -> (value, expiry_time)
        self._memory_lock = Lock()
        
        logger.info(
            f"Cache manager initialized: dir={self.cache_dir}, "
            f"ttl={self.default_ttl}s, memory_cache={self.enable_memory_cache}"
        )
    
    def _get_cache_path(self, key: str) -> Path:
        """Get file path for cache key."""
        # Hash the key to create safe filename
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        safe_key = "".join(c if c.isalnum() else "_" for c in key[:32])
        filename = f"{safe_key}_{key_hash}.cache"
        return self.cache_dir / filename
    
    def _get_metadata_path(self, key: str) -> Path:
        """Get metadata file path for cache key."""
        cache_path = self._get_cache_path(key)
        return cache_path.with_suffix('.meta')
    
    def get(self, key: str, default: Any = None) -> Optional[Any]:
        """
        Retrieve value from cache.
        
        Args:
            key: Cache key
            default: Default value if key not found or expired
        
        Returns:
            Cached value or default if not found/expired
        """
        # Try memory cache first
        if self.enable_memory_cache:
            with self._memory_lock:
                if key in self._memory_cache:
                    value, expiry = self._memory_cache[key]
                    
                    # Check if expired
                    if datetime.now(timezone.utc) < expiry:
                        logger.debug(f"Cache HIT (memory): {key}")
                        return value
                    else:
                        # Remove expired entry
                        del self._memory_cache[key]
                        logger.debug(f"Cache EXPIRED (memory): {key}")
        
        # Try file cache
        cache_path = self._get_cache_path(key)
        meta_path = self._get_metadata_path(key)
        
        if not cache_path.exists() or not meta_path.exists():
            logger.debug(f"Cache MISS: {key}")
            return default
        
        try:
            # Load metadata
            with open(meta_path, 'r') as f:
                metadata = json.load(f)
            
            # Check expiry
            expiry_time = datetime.fromisoformat(metadata['expiry'])
            if datetime.now(timezone.utc) >= expiry_time:
                logger.debug(f"Cache EXPIRED (file): {key}")
                self.invalidate(key)
                return default
            
            # Load cached value
            with open(cache_path, 'rb') as f:
                value = pickle.load(f)
            
            logger.debug(f"Cache HIT (file): {key}")
            
            # Populate memory cache if enabled
            if self.enable_memory_cache:
                self._set_memory_cache(key, value, expiry_time)
            
            return value
            
        except Exception as e:
            logger.warning(f"Cache read error for {key}: {e}")
            return default
    
    def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """
        Store value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None = use default)
        
        Returns:
            True if successful, False otherwise
        """
        if ttl is None:
            ttl = self.default_ttl
        
        expiry_time = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        
        try:
            # Store in file cache
            cache_path = self._get_cache_path(key)
            meta_path = self._get_metadata_path(key)
            
            # Write value
            with open(cache_path, 'wb') as f:
                pickle.dump(value, f)
            
            # Write metadata
            metadata = {
                'key': key,
                'created': datetime.now(timezone.utc).isoformat(),
                'expiry': expiry_time.isoformat(),
                'ttl': ttl
            }
            
            with open(meta_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.debug(f"Cache SET (file): {key} (ttl={ttl}s)")
            
            # Store in memory cache if enabled
            if self.enable_memory_cache:
                self._set_memory_cache(key, value, expiry_time)
            
            return True
            
        except Exception as e:
            logger.error(f"Cache write error for {key}: {e}")
            return False
    
    def _set_memory_cache(self, key: str, value: Any, expiry: datetime):
        """Store value in memory cache with LRU eviction."""
        with self._memory_lock:
            # Evict oldest items if at capacity
            if len(self._memory_cache) >= self.max_memory_items:
                # Remove oldest entry (simple FIFO, could be improved to LRU)
                oldest_key = next(iter(self._memory_cache))
                del self._memory_cache[oldest_key]
                logger.debug(f"Cache EVICT (memory): {oldest_key}")
            
            self._memory_cache[key] = (value, expiry)
            logger.debug(f"Cache SET (memory): {key}")
    
    def invalidate(self, key: str) -> bool:
        """
        Invalidate (delete) cache entry.
        
        Args:
            key: Cache key to invalidate
        
        Returns:
            True if entry was found and deleted, False otherwise
        """
        # Remove from memory cache
        if self.enable_memory_cache:
            with self._memory_lock:
                if key in self._memory_cache:
                    del self._memory_cache[key]
                    logger.debug(f"Cache INVALIDATE (memory): {key}")
        
        # Remove from file cache
        cache_path = self._get_cache_path(key)
        meta_path = self._get_metadata_path(key)
        
        found = False
        
        if cache_path.exists():
            cache_path.unlink()
            found = True
        
        if meta_path.exists():
            meta_path.unlink()
            found = True
        
        if found:
            logger.debug(f"Cache INVALIDATE (file): {key}")
        
        return found
    
    def clear_expired(self) -> int:
        """
        Remove all expired cache entries.
        
        Returns:
            Number of entries removed
        """
        removed_count = 0
        now = datetime.now(timezone.utc)
        
        # Clear expired memory cache entries
        if self.enable_memory_cache:
            with self._memory_lock:
                expired_keys = [
                    key for key, (_, expiry) in self._memory_cache.items()
                    if now >= expiry
                ]
                for key in expired_keys:
                    del self._memory_cache[key]
                    removed_count += 1
        
        # Clear expired file cache entries
        for meta_path in self.cache_dir.glob('*.meta'):
            try:
                with open(meta_path, 'r') as f:
                    metadata = json.load(f)
                
                expiry_time = datetime.fromisoformat(metadata['expiry'])
                
                if now >= expiry_time:
                    # Remove cache and metadata files
                    cache_path = meta_path.with_suffix('.cache')
                    
                    if cache_path.exists():
                        cache_path.unlink()
                    
                    meta_path.unlink()
                    removed_count += 1
                    
            except Exception as e:
                logger.warning(f"Error checking expiry for {meta_path}: {e}")
        
        if removed_count > 0:
            logger.info(f"Cleared {removed_count} expired cache entries")
        
        return removed_count
    
    def clear_all(self) -> int:
        """
        Remove all cache entries.
        
        Returns:
            Number of entries removed
        """
        removed_count = 0
        
        # Clear memory cache
        if self.enable_memory_cache:
            with self._memory_lock:
                removed_count += len(self._memory_cache)
                self._memory_cache.clear()
        
        # Clear file cache
        for cache_file in self.cache_dir.glob('*.cache'):
            cache_file.unlink()
            removed_count += 1
        
        for meta_file in self.cache_dir.glob('*.meta'):
            meta_file.unlink()
        
        logger.info(f"Cleared all cache entries ({removed_count} items)")
        
        return removed_count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            'cache_dir': str(self.cache_dir),
            'default_ttl': self.default_ttl,
            'memory_cache_enabled': self.enable_memory_cache,
            'memory_cache_size': 0,
            'file_cache_size': 0,
            'total_size_bytes': 0
        }
        
        # Memory cache stats
        if self.enable_memory_cache:
            with self._memory_lock:
                stats['memory_cache_size'] = len(self._memory_cache)
        
        # File cache stats
        file_count = 0
        total_bytes = 0
        
        for cache_file in self.cache_dir.glob('*.cache'):
            file_count += 1
            total_bytes += cache_file.stat().st_size
        
        stats['file_cache_size'] = file_count
        stats['total_size_bytes'] = total_bytes
        stats['total_size_mb'] = round(total_bytes / (1024 * 1024), 2)
        
        return stats


# Global cache instance
_global_cache = None


def get_cache() -> CacheManager:
    """Get global cache instance (singleton pattern)."""
    global _global_cache
    
    if _global_cache is None:
        _global_cache = CacheManager()
    
    return _global_cache


# Example usage and testing
if __name__ == "__main__":
    import time
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n=== Cache Manager Demo ===\n")
    
    # Create cache manager
    cache = CacheManager(
        cache_dir="/tmp/meta-cache-demo",
        default_ttl=5,  # 5 seconds for demo
        enable_memory_cache=True
    )
    
    # Example 1: Basic caching
    print("1. Basic caching:")
    cache.set("user_data", {"name": "Alice", "role": "admin"})
    result = cache.get("user_data")
    print(f"   Retrieved: {result}")
    
    # Example 2: Custom TTL
    print("\n2. Custom TTL:")
    cache.set("temp_data", "This expires in 2 seconds", ttl=2)
    print(f"   Immediate get: {cache.get('temp_data')}")
    time.sleep(3)
    print(f"   After 3 seconds: {cache.get('temp_data', 'EXPIRED')}")
    
    # Example 3: Cache invalidation
    print("\n3. Cache invalidation:")
    cache.set("to_invalidate", "This will be deleted")
    print(f"   Before: {cache.get('to_invalidate')}")
    cache.invalidate("to_invalidate")
    print(f"   After: {cache.get('to_invalidate', 'NOT FOUND')}")
    
    # Example 4: Cache statistics
    print("\n4. Cache statistics:")
    cache.set("stat_test_1", "data1")
    cache.set("stat_test_2", "data2")
    stats = cache.get_stats()
    print(f"   Memory cache size: {stats['memory_cache_size']}")
    print(f"   File cache size: {stats['file_cache_size']}")
    print(f"   Total size: {stats['total_size_mb']} MB")
    
    # Example 5: Clear expired
    print("\n5. Clear expired entries:")
    cache.set("expires_soon", "data", ttl=1)
    time.sleep(2)
    removed = cache.clear_expired()
    print(f"   Removed {removed} expired entries")
    
    # Example 6: Clear all
    print("\n6. Clear all cache:")
    removed = cache.clear_all()
    print(f"   Removed {removed} total entries")
    
    print("\n=== Demo complete ===\n")
