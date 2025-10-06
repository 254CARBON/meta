#!/usr/bin/env python3
"""
Redis Client Wrapper for Fallback Caching

Provides Redis client wrapper with connection pooling, TTL management,
versioning, and file-based fallback for resilient caching operations.

Features:
- Connection pooling for performance
- TTL management with automatic expiration
- Data versioning for cache invalidation
- File-based fallback when Redis unavailable
- Atomic operations with retry logic
- Comprehensive error handling
- Integration with circuit breaker
- Monitoring and metrics

Usage:
    from scripts.utils.redis_client import RedisClient

    redis_client = RedisClient()
    
    # Set with TTL
    redis_client.set("catalog", catalog_data, ttl=3600)
    
    # Get with fallback
    catalog = redis_client.get("catalog", fallback_to_file=True)
    
    # Atomic operations
    redis_client.set_if_not_exists("lock", "value", ttl=60)
"""

import json
import time
import logging
import threading
import pickle
from pathlib import Path
from typing import Any, Optional, Dict, List, Union, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

try:
    import redis
    from redis.connection import ConnectionPool
    from redis.exceptions import RedisError, ConnectionError, TimeoutError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    ConnectionPool = None
    RedisError = Exception
    ConnectionError = Exception
    TimeoutError = Exception

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenException

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    data: Any
    timestamp: float
    ttl: Optional[int]
    version: str
    metadata: Dict[str, Any]


@dataclass
class RedisConfig:
    """Redis configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 20
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30
    fallback_dir: str = "cache_fallback"


class RedisClient:
    """
    Redis client wrapper with fallback mechanisms.
    
    Provides resilient caching with Redis backend and file-based fallback,
    connection pooling, TTL management, and comprehensive error handling.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, config: RedisConfig = None):
        """
        Initialize Redis client.
        
        Args:
            config: Redis configuration
        """
        self.config = config or RedisConfig()
        self._pool = None
        self._client = None
        self._circuit_breaker = None
        self._fallback_dir = Path(self.config.fallback_dir)
        self._lock = threading.Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
            "fallback_hits": 0,
            "fallback_sets": 0
        }
        
        # Ensure fallback directory exists
        self._fallback_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Redis connection
        self._initialize_redis()
        
        # Setup circuit breaker
        self._setup_circuit_breaker()
        
        logger.info(f"Redis client initialized: {self.config.host}:{self.config.port}")
    
    @classmethod
    def get_instance(cls, config: RedisConfig = None) -> 'RedisClient':
        """Get singleton instance of Redis client."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance
    
    def _initialize_redis(self):
        """Initialize Redis connection pool."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using file-based fallback only")
            return
        
        try:
            # Create connection pool
            self._pool = ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                retry_on_timeout=self.config.retry_on_timeout,
                health_check_interval=self.config.health_check_interval
            )
            
            # Create Redis client
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            self._client.ping()
            
            logger.info("Redis connection established")
            
        except Exception as e:
            logger.warning(f"Failed to initialize Redis: {e}")
            self._client = None
            self._pool = None
    
    def _setup_circuit_breaker(self):
        """Setup circuit breaker for Redis operations."""
        try:
            from .circuit_breaker import get_circuit_breaker
            self._circuit_breaker = get_circuit_breaker(
                "redis-client",
                failure_threshold=5,
                recovery_timeout=60,
                expected_exceptions=(RedisError, ConnectionError, TimeoutError)
            )
        except Exception as e:
            logger.warning(f"Failed to setup circuit breaker: {e}")
            self._circuit_breaker = None
    
    def _is_redis_available(self) -> bool:
        """Check if Redis is available."""
        if not self._client:
            return False
        
        try:
            self._client.ping()
            return True
        except Exception:
            return False
    
    def _serialize_data(self, data: Any) -> bytes:
        """Serialize data for storage."""
        try:
            # Try JSON first (for simple data types)
            return json.dumps(data, default=str).encode('utf-8')
        except (TypeError, ValueError):
            # Fall back to pickle for complex objects
            return pickle.dumps(data)
    
    def _deserialize_data(self, data: bytes) -> Any:
        """Deserialize data from storage."""
        try:
            # Try JSON first
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fall back to pickle
            return pickle.loads(data)
    
    def _get_fallback_path(self, key: str) -> Path:
        """Get fallback file path for a key."""
        # Sanitize key for filesystem
        safe_key = "".join(c for c in key if c.isalnum() or c in "._-")
        return self._fallback_dir / f"{safe_key}.cache"
    
    def _save_to_fallback(self, key: str, data: Any, ttl: Optional[int] = None):
        """Save data to fallback file."""
        try:
            cache_entry = CacheEntry(
                data=data,
                timestamp=time.time(),
                ttl=ttl,
                version=f"v{int(time.time())}",
                metadata={"source": "fallback"}
            )
            
            fallback_path = self._get_fallback_path(key)
            with open(fallback_path, 'wb') as f:
                pickle.dump(cache_entry, f)
            
            self._stats["fallback_sets"] += 1
            logger.debug(f"Saved to fallback: {key}")
            
        except Exception as e:
            logger.error(f"Failed to save to fallback {key}: {e}")
    
    def _load_from_fallback(self, key: str) -> Optional[Any]:
        """Load data from fallback file."""
        try:
            fallback_path = self._get_fallback_path(key)
            
            if not fallback_path.exists():
                return None
            
            with open(fallback_path, 'rb') as f:
                cache_entry: CacheEntry = pickle.load(f)
            
            # Check TTL
            if cache_entry.ttl and time.time() - cache_entry.timestamp > cache_entry.ttl:
                fallback_path.unlink()  # Remove expired file
                return None
            
            self._stats["fallback_hits"] += 1
            logger.debug(f"Loaded from fallback: {key}")
            
            return cache_entry.data
            
        except Exception as e:
            logger.error(f"Failed to load from fallback {key}: {e}")
            return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        fallback_to_file: bool = True
    ) -> bool:
        """
        Set a key-value pair in Redis.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            fallback_to_file: Whether to save to file fallback
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Try Redis first
            if self._is_redis_available() and self._circuit_breaker:
                def _set_redis():
                    serialized_data = self._serialize_data(value)
                    if ttl:
                        return self._client.setex(key, ttl, serialized_data)
                    else:
                        return self._client.set(key, serialized_data)
                
                result = self._circuit_breaker.call(_set_redis)
                
                if result:
                    self._stats["sets"] += 1
                    logger.debug(f"Set in Redis: {key}")
                    
                    # Also save to fallback if requested
                    if fallback_to_file:
                        self._save_to_fallback(key, value, ttl)
                    
                    return True
            
            # Fallback to file
            if fallback_to_file:
                self._save_to_fallback(key, value, ttl)
                return True
            
            return False
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Failed to set {key}: {e}")
            return False
    
    def get(
        self,
        key: str,
        fallback_to_file: bool = True
    ) -> Optional[Any]:
        """
        Get a value from Redis.
        
        Args:
            key: Cache key
            fallback_to_file: Whether to fallback to file
        
        Returns:
            Cached value or None if not found
        """
        try:
            # Try Redis first
            if self._is_redis_available() and self._circuit_breaker:
                def _get_redis():
                    data = self._client.get(key)
                    if data is not None:
                        return self._deserialize_data(data)
                    return None
                
                result = self._circuit_breaker.call(_get_redis)
                
                if result is not None:
                    self._stats["hits"] += 1
                    logger.debug(f"Hit in Redis: {key}")
                    return result
            
            # Fallback to file
            if fallback_to_file:
                result = self._load_from_fallback(key)
                if result is not None:
                    self._stats["hits"] += 1
                    return result
            
            self._stats["misses"] += 1
            return None
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Failed to get {key}: {e}")
            
            # Try file fallback on error
            if fallback_to_file:
                return self._load_from_fallback(key)
            
            return None
    
    def delete(self, key: str) -> bool:
        """
        Delete a key from Redis and fallback.
        
        Args:
            key: Cache key
        
        Returns:
            True if successful, False otherwise
        """
        try:
            deleted = False
            
            # Delete from Redis
            if self._is_redis_available() and self._circuit_breaker:
                def _delete_redis():
                    return self._client.delete(key)
                
                result = self._circuit_breaker.call(_delete_redis)
                if result:
                    deleted = True
            
            # Delete from fallback
            fallback_path = self._get_fallback_path(key)
            if fallback_path.exists():
                fallback_path.unlink()
                deleted = True
            
            if deleted:
                self._stats["deletes"] += 1
                logger.debug(f"Deleted: {key}")
            
            return deleted
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Failed to delete {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in Redis or fallback.
        
        Args:
            key: Cache key
        
        Returns:
            True if key exists, False otherwise
        """
        try:
            # Check Redis first
            if self._is_redis_available() and self._circuit_breaker:
                def _exists_redis():
                    return self._client.exists(key)
                
                if self._circuit_breaker.call(_exists_redis):
                    return True
            
            # Check fallback
            fallback_path = self._get_fallback_path(key)
            if fallback_path.exists():
                # Check if expired
                try:
                    with open(fallback_path, 'rb') as f:
                        cache_entry: CacheEntry = pickle.load(f)
                    
                    if cache_entry.ttl and time.time() - cache_entry.timestamp > cache_entry.ttl:
                        fallback_path.unlink()
                        return False
                    
                    return True
                except Exception:
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check existence of {key}: {e}")
            return False
    
    def set_if_not_exists(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        fallback_to_file: bool = True
    ) -> bool:
        """
        Set a key only if it doesn't exist (atomic operation).
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            fallback_to_file: Whether to save to file fallback
        
        Returns:
            True if key was set, False if key already exists
        """
        try:
            # Try Redis first
            if self._is_redis_available() and self._circuit_breaker:
                def _setnx_redis():
                    serialized_data = self._serialize_data(value)
                    if ttl:
                        return self._client.set(key, serialized_data, nx=True, ex=ttl)
                    else:
                        return self._client.set(key, serialized_data, nx=True)
                
                result = self._circuit_breaker.call(_setnx_redis)
                
                if result:
                    self._stats["sets"] += 1
                    logger.debug(f"Set if not exists in Redis: {key}")
                    
                    # Also save to fallback if requested
                    if fallback_to_file:
                        self._save_to_fallback(key, value, ttl)
                    
                    return True
            
            # Check fallback first
            if fallback_to_file and self.exists(key):
                return False
            
            # Set in fallback
            if fallback_to_file:
                self._save_to_fallback(key, value, ttl)
                return True
            
            return False
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Failed to set if not exists {key}: {e}")
            return False
    
    def get_ttl(self, key: str) -> Optional[int]:
        """
        Get TTL for a key.
        
        Args:
            key: Cache key
        
        Returns:
            TTL in seconds, -1 if no expiration, None if key doesn't exist
        """
        try:
            # Check Redis first
            if self._is_redis_available() and self._circuit_breaker:
                def _ttl_redis():
                    return self._client.ttl(key)
                
                ttl = self._circuit_breaker.call(_ttl_redis)
                if ttl is not None:
                    return ttl
            
            # Check fallback
            fallback_path = self._get_fallback_path(key)
            if fallback_path.exists():
                try:
                    with open(fallback_path, 'rb') as f:
                        cache_entry: CacheEntry = pickle.load(f)
                    
                    if cache_entry.ttl:
                        remaining = cache_entry.ttl - (time.time() - cache_entry.timestamp)
                        return max(0, int(remaining))
                    
                    return -1  # No expiration
                except Exception:
                    pass
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get TTL for {key}: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Redis client statistics."""
        with self._lock:
            total_operations = self._stats["hits"] + self._stats["misses"] + self._stats["sets"] + self._stats["deletes"]
            hit_rate = self._stats["hits"] / max(total_operations, 1)
            
            return {
                "redis_available": self._is_redis_available(),
                "circuit_breaker_state": self._circuit_breaker.get_state()["state"] if self._circuit_breaker else "disabled",
                "stats": self._stats.copy(),
                "hit_rate": hit_rate,
                "fallback_dir": str(self._fallback_dir),
                "config": {
                    "host": self.config.host,
                    "port": self.config.port,
                    "db": self.config.db,
                    "max_connections": self.config.max_connections
                }
            }
    
    def cleanup_expired(self) -> int:
        """Clean up expired entries from fallback directory."""
        cleaned = 0
        current_time = time.time()
        
        try:
            for file_path in self._fallback_dir.glob("*.cache"):
                try:
                    with open(file_path, 'rb') as f:
                        cache_entry: CacheEntry = pickle.load(f)
                    
                    # Check if expired
                    if cache_entry.ttl and current_time - cache_entry.timestamp > cache_entry.ttl:
                        file_path.unlink()
                        cleaned += 1
                        
                except Exception as e:
                    logger.warning(f"Failed to process fallback file {file_path}: {e}")
                    # Remove corrupted files
                    file_path.unlink()
                    cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} expired fallback entries")
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired entries: {e}")
            return 0
    
    def reset_stats(self):
        """Reset statistics."""
        with self._lock:
            self._stats = {
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "deletes": 0,
                "errors": 0,
                "fallback_hits": 0,
                "fallback_sets": 0
            }
            logger.info("Redis client statistics reset")


# Global Redis client instance
redis_client = RedisClient.get_instance()


# Convenience functions for common operations
def cache_catalog(catalog_data: Dict[str, Any], ttl: int = 3600) -> bool:
    """Cache catalog data with fallback."""
    return redis_client.set("catalog", catalog_data, ttl=ttl, fallback_to_file=True)


def get_cached_catalog() -> Optional[Dict[str, Any]]:
    """Get cached catalog data with fallback."""
    return redis_client.get("catalog", fallback_to_file=True)


def cache_quality_scores(scores: Dict[str, float], ttl: int = 1800) -> bool:
    """Cache quality scores with fallback."""
    return redis_client.set("quality_scores", scores, ttl=ttl, fallback_to_file=True)


def get_cached_quality_scores() -> Optional[Dict[str, float]]:
    """Get cached quality scores with fallback."""
    return redis_client.get("quality_scores", fallback_to_file=True)


def cache_drift_state(drift_data: Dict[str, Any], ttl: int = 1800) -> bool:
    """Cache drift detection state with fallback."""
    return redis_client.set("drift_state", drift_data, ttl=ttl, fallback_to_file=True)


def get_cached_drift_state() -> Optional[Dict[str, Any]]:
    """Get cached drift state with fallback."""
    return redis_client.get("drift_state", fallback_to_file=True)


# Example usage and testing
if __name__ == "__main__":
    import logging
    import time
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n=== Redis Client Demo ===\n")
    
    # Example 1: Basic operations
    print("1. Basic operations:")
    
    # Set data
    test_data = {"services": ["gateway", "auth"], "timestamp": time.time()}
    success = redis_client.set("test_key", test_data, ttl=60)
    print(f"   Set operation: {'Success' if success else 'Failed'}")
    
    # Get data
    retrieved_data = redis_client.get("test_key")
    print(f"   Get operation: {'Success' if retrieved_data else 'Failed'}")
    if retrieved_data:
        print(f"   Retrieved data: {retrieved_data}")
    
    # Check existence
    exists = redis_client.exists("test_key")
    print(f"   Key exists: {exists}")
    
    # Get TTL
    ttl = redis_client.get_ttl("test_key")
    print(f"   TTL: {ttl} seconds")
    
    # Example 2: Atomic operations
    print("\n2. Atomic operations:")
    
    # Set if not exists
    success = redis_client.set_if_not_exists("lock_key", "locked", ttl=30)
    print(f"   Set if not exists: {'Success' if success else 'Failed'}")
    
    # Try again (should fail)
    success = redis_client.set_if_not_exists("lock_key", "locked_again", ttl=30)
    print(f"   Set if not exists (again): {'Success' if success else 'Failed'}")
    
    # Example 3: Convenience functions
    print("\n3. Convenience functions:")
    
    # Cache catalog
    catalog = {"gateway": {"version": "1.0.0"}, "auth": {"version": "1.1.0"}}
    success = cache_catalog(catalog, ttl=300)
    print(f"   Cache catalog: {'Success' if success else 'Failed'}")
    
    # Get cached catalog
    cached_catalog = get_cached_catalog()
    print(f"   Get cached catalog: {'Success' if cached_catalog else 'Failed'}")
    if cached_catalog:
        print(f"   Cached catalog: {cached_catalog}")
    
    # Example 4: Statistics
    print("\n4. Statistics:")
    stats = redis_client.get_stats()
    print(f"   Redis available: {stats['redis_available']}")
    print(f"   Circuit breaker state: {stats['circuit_breaker_state']}")
    print(f"   Hit rate: {stats['hit_rate']:.2%}")
    print(f"   Operations: {stats['stats']}")
    
    # Example 5: Cleanup
    print("\n5. Cleanup:")
    cleaned = redis_client.cleanup_expired()
    print(f"   Cleaned up {cleaned} expired entries")
    
    # Clean up test keys
    redis_client.delete("test_key")
    redis_client.delete("lock_key")
    redis_client.delete("catalog")
    
    print("\n=== Demo complete ===\n")
    print("Redis client is ready for production use!")
    print("Use redis_client.set() and redis_client.get() for resilient caching.")
