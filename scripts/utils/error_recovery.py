#!/usr/bin/env python3
"""
Error Recovery Utilities for Resilient Operations

Provides comprehensive error recovery strategies including fallback mechanisms,
graceful degradation, retry logic, and circuit breaker integration.

Features:
- Fallback strategies for external service failures
- Graceful degradation patterns
- Retry with exponential backoff
- Circuit breaker integration
- Error classification and handling
- Recovery state management
- Comprehensive logging and monitoring

Usage:
    from scripts.utils.error_recovery import ErrorRecovery, FallbackStrategy

    recovery = ErrorRecovery()
    
    # With fallback
    result = recovery.execute_with_fallback(
        primary_func=fetch_from_api,
        fallback_func=load_from_cache,
        context="catalog_fetch"
    )
    
    # With retry and circuit breaker
    result = recovery.execute_with_retry(
        func=external_api_call,
        max_retries=3,
        backoff_factor=2,
        circuit_breaker_name="external-api"
    )
"""

import time
import logging
import threading
from typing import Callable, Any, Optional, Dict, List, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from functools import wraps

from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenException
from .retry_decorator import retry_with_backoff

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Classification of error types for appropriate handling."""
    TRANSIENT = "transient"           # Temporary, retryable errors
    PERMANENT = "permanent"          # Non-retryable errors
    TIMEOUT = "timeout"              # Timeout errors
    RATE_LIMIT = "rate_limit"        # Rate limiting errors
    AUTHENTICATION = "authentication" # Authentication failures
    AUTHORIZATION = "authorization"   # Authorization failures
    NETWORK = "network"              # Network connectivity issues
    SERVICE_UNAVAILABLE = "service_unavailable"  # Service down
    UNKNOWN = "unknown"              # Unclassified errors


class FallbackStrategy(Enum):
    """Fallback strategies for error recovery."""
    CACHE = "cache"                  # Use cached data
    DEFAULT = "default"              # Use default values
    SKIP = "skip"                    # Skip operation
    RETRY = "retry"                  # Retry with different parameters
    DEGRADE = "degrade"              # Use degraded functionality
    MANUAL = "manual"                # Require manual intervention


@dataclass
class RecoveryContext:
    """Context information for error recovery."""
    operation_name: str
    user: str = "system"
    resource: Optional[str] = None
    parameters: Dict[str, Any] = None
    timeout: float = 30.0
    max_retries: int = 3
    backoff_factor: float = 2.0
    circuit_breaker_name: Optional[str] = None
    fallback_strategy: FallbackStrategy = FallbackStrategy.CACHE
    metadata: Dict[str, Any] = None


@dataclass
class RecoveryResult:
    """Result of a recovery operation."""
    success: bool
    data: Any = None
    error: Optional[Exception] = None
    error_type: ErrorType = ErrorType.UNKNOWN
    attempts: int = 0
    duration: float = 0.0
    fallback_used: bool = False
    circuit_breaker_state: Optional[str] = None
    metadata: Dict[str, Any] = None


class ErrorRecovery:
    """
    Error recovery utility for resilient operations.
    
    Provides comprehensive error handling with fallback strategies,
    retry logic, circuit breaker integration, and graceful degradation.
    """
    
    def __init__(self):
        """Initialize error recovery utility."""
        self.recovery_stats: Dict[str, Dict[str, int]] = {}
        self._lock = threading.Lock()
        
        logger.info("Error recovery utility initialized")
    
    def classify_error(self, error: Exception) -> ErrorType:
        """Classify an error for appropriate handling."""
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # Network and connectivity errors
        if any(keyword in error_str for keyword in ['connection', 'network', 'timeout', 'unreachable']):
            return ErrorType.NETWORK
        
        # Timeout errors
        if 'timeout' in error_str or 'timed out' in error_str:
            return ErrorType.TIMEOUT
        
        # Rate limiting
        if any(keyword in error_str for keyword in ['rate limit', 'too many requests', '429']):
            return ErrorType.RATE_LIMIT
        
        # Authentication errors
        if any(keyword in error_str for keyword in ['unauthorized', '401', 'authentication']):
            return ErrorType.AUTHENTICATION
        
        # Authorization errors
        if any(keyword in error_str for keyword in ['forbidden', '403', 'permission']):
            return ErrorType.AUTHORIZATION
        
        # Service unavailable
        if any(keyword in error_str for keyword in ['service unavailable', '503', 'unavailable']):
            return ErrorType.SERVICE_UNAVAILABLE
        
        # Transient errors (HTTP 5xx, connection errors)
        if any(keyword in error_str for keyword in ['500', '502', '504', 'internal server error']):
            return ErrorType.TRANSIENT
        
        # Permanent errors (HTTP 4xx except auth/rate limit)
        if any(keyword in error_str for keyword in ['400', '404', 'bad request', 'not found']):
            return ErrorType.PERMANENT
        
        return ErrorType.UNKNOWN
    
    def is_retryable(self, error_type: ErrorType) -> bool:
        """Determine if an error type is retryable."""
        retryable_types = {
            ErrorType.TRANSIENT,
            ErrorType.TIMEOUT,
            ErrorType.RATE_LIMIT,
            ErrorType.NETWORK,
            ErrorType.SERVICE_UNAVAILABLE
        }
        return error_type in retryable_types
    
    def execute_with_fallback(
        self,
        primary_func: Callable,
        fallback_func: Callable,
        context: Union[str, RecoveryContext],
        *args,
        **kwargs
    ) -> RecoveryResult:
        """
        Execute function with fallback strategy.
        
        Args:
            primary_func: Primary function to execute
            fallback_func: Fallback function if primary fails
            context: Recovery context or operation name
            *args, **kwargs: Arguments for the functions
        
        Returns:
            RecoveryResult with execution details
        """
        start_time = time.time()
        
        # Normalize context
        if isinstance(context, str):
            context = RecoveryContext(operation_name=context)
        
        attempts = 0
        last_error = None
        
        try:
            # Try primary function
            attempts += 1
            logger.debug(f"Executing primary function for {context.operation_name}")
            
            result = primary_func(*args, **kwargs)
            
            return RecoveryResult(
                success=True,
                data=result,
                attempts=attempts,
                duration=time.time() - start_time,
                fallback_used=False,
                metadata=context.metadata or {}
            )
            
        except Exception as e:
            last_error = e
            error_type = self.classify_error(e)
            
            logger.warning(
                f"Primary function failed for {context.operation_name}: {e} "
                f"(error_type: {error_type.value})"
            )
            
            # Update stats
            self._update_stats(context.operation_name, "primary_failure", error_type.value)
            
            # Try fallback if primary fails
            try:
                attempts += 1
                logger.info(f"Attempting fallback for {context.operation_name}")
                
                result = fallback_func(*args, **kwargs)
                
                return RecoveryResult(
                    success=True,
                    data=result,
                    error=last_error,
                    error_type=error_type,
                    attempts=attempts,
                    duration=time.time() - start_time,
                    fallback_used=True,
                    metadata=context.metadata or {}
                )
                
            except Exception as fallback_error:
                logger.error(
                    f"Fallback also failed for {context.operation_name}: {fallback_error}"
                )
                
                self._update_stats(context.operation_name, "fallback_failure", self.classify_error(fallback_error).value)
                
                return RecoveryResult(
                    success=False,
                    error=fallback_error,
                    error_type=self.classify_error(fallback_error),
                    attempts=attempts,
                    duration=time.time() - start_time,
                    fallback_used=True,
                    metadata=context.metadata or {}
                )
    
    def execute_with_retry(
        self,
        func: Callable,
        context: Union[str, RecoveryContext],
        *args,
        **kwargs
    ) -> RecoveryResult:
        """
        Execute function with retry logic and circuit breaker.
        
        Args:
            func: Function to execute
            context: Recovery context or operation name
            *args, **kwargs: Arguments for the function
        
        Returns:
            RecoveryResult with execution details
        """
        start_time = time.time()
        
        # Normalize context
        if isinstance(context, str):
            context = RecoveryContext(operation_name=context)
        
        attempts = 0
        last_error = None
        
        # Get circuit breaker if specified
        circuit_breaker = None
        if context.circuit_breaker_name:
            try:
                from .circuit_breaker import get_circuit_breaker
                circuit_breaker = get_circuit_breaker(context.circuit_breaker_name)
            except Exception as e:
                logger.warning(f"Failed to get circuit breaker {context.circuit_breaker_name}: {e}")
        
        # Retry loop
        for attempt in range(context.max_retries + 1):
            attempts = attempt + 1
            
            try:
                # Check circuit breaker
                if circuit_breaker:
                    cb_state = circuit_breaker.get_state()
                    if cb_state["state"] == "open":
                        raise CircuitBreakerOpenException(f"Circuit breaker {context.circuit_breaker_name} is open")
                
                # Execute function
                if circuit_breaker:
                    result = circuit_breaker.call(func, *args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Success
                return RecoveryResult(
                    success=True,
                    data=result,
                    attempts=attempts,
                    duration=time.time() - start_time,
                    circuit_breaker_state=circuit_breaker.get_state()["state"] if circuit_breaker else None,
                    metadata=context.metadata or {}
                )
                
            except CircuitBreakerOpenException as e:
                # Circuit breaker is open, don't retry
                logger.warning(f"Circuit breaker open for {context.operation_name}: {e}")
                
                return RecoveryResult(
                    success=False,
                    error=e,
                    error_type=ErrorType.SERVICE_UNAVAILABLE,
                    attempts=attempts,
                    duration=time.time() - start_time,
                    circuit_breaker_state="open",
                    metadata=context.metadata or {}
                )
                
            except Exception as e:
                last_error = e
                error_type = self.classify_error(e)
                
                logger.warning(
                    f"Attempt {attempts} failed for {context.operation_name}: {e} "
                    f"(error_type: {error_type.value})"
                )
                
                # Check if error is retryable
                if not self.is_retryable(error_type):
                    logger.error(f"Non-retryable error for {context.operation_name}: {e}")
                    break
                
                # Check if we've exhausted retries
                if attempt >= context.max_retries:
                    logger.error(f"Max retries exceeded for {context.operation_name}")
                    break
                
                # Calculate backoff delay
                delay = context.backoff_factor ** attempt
                logger.info(f"Retrying {context.operation_name} in {delay}s (attempt {attempts + 1})")
                
                time.sleep(delay)
        
        # All retries failed
        self._update_stats(context.operation_name, "retry_exhausted", error_type.value)
        
        return RecoveryResult(
            success=False,
            error=last_error,
            error_type=error_type,
            attempts=attempts,
            duration=time.time() - start_time,
            circuit_breaker_state=circuit_breaker.get_state()["state"] if circuit_breaker else None,
            metadata=context.metadata or {}
        )
    
    def execute_with_graceful_degradation(
        self,
        primary_func: Callable,
        degraded_func: Callable,
        context: Union[str, RecoveryContext],
        *args,
        **kwargs
    ) -> RecoveryResult:
        """
        Execute with graceful degradation fallback.
        
        Args:
            primary_func: Primary function with full functionality
            degraded_func: Degraded function with reduced functionality
            context: Recovery context or operation name
            *args, **kwargs: Arguments for the functions
        
        Returns:
            RecoveryResult with execution details
        """
        start_time = time.time()
        
        # Normalize context
        if isinstance(context, str):
            context = RecoveryContext(operation_name=context)
        
        try:
            # Try primary function first
            logger.debug(f"Executing primary function for {context.operation_name}")
            result = primary_func(*args, **kwargs)
            
            return RecoveryResult(
                success=True,
                data=result,
                attempts=1,
                duration=time.time() - start_time,
                fallback_used=False,
                metadata=context.metadata or {}
            )
            
        except Exception as e:
            error_type = self.classify_error(e)
            
            logger.warning(
                f"Primary function failed, switching to degraded mode for {context.operation_name}: {e}"
            )
            
            try:
                # Execute degraded function
                result = degraded_func(*args, **kwargs)
                
                return RecoveryResult(
                    success=True,
                    data=result,
                    error=e,
                    error_type=error_type,
                    attempts=2,
                    duration=time.time() - start_time,
                    fallback_used=True,
                    metadata=context.metadata or {}
                )
                
            except Exception as degraded_error:
                logger.error(
                    f"Degraded function also failed for {context.operation_name}: {degraded_error}"
                )
                
                return RecoveryResult(
                    success=False,
                    error=degraded_error,
                    error_type=self.classify_error(degraded_error),
                    attempts=2,
                    duration=time.time() - start_time,
                    fallback_used=True,
                    metadata=context.metadata or {}
                )
    
    def _update_stats(self, operation: str, event: str, error_type: str):
        """Update recovery statistics."""
        with self._lock:
            if operation not in self.recovery_stats:
                self.recovery_stats[operation] = {}
            
            key = f"{event}_{error_type}"
            self.recovery_stats[operation][key] = self.recovery_stats[operation].get(key, 0) + 1
    
    def get_recovery_stats(self) -> Dict[str, Dict[str, int]]:
        """Get recovery statistics."""
        with self._lock:
            return self.recovery_stats.copy()
    
    def reset_stats(self):
        """Reset recovery statistics."""
        with self._lock:
            self.recovery_stats.clear()
            logger.info("Recovery statistics reset")


# Global error recovery instance
error_recovery = ErrorRecovery()


# Convenience decorators
def with_fallback(fallback_func: Callable, context: str = None):
    """Decorator for adding fallback functionality."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_context = context or func.__name__
            result = error_recovery.execute_with_fallback(
                primary_func=func,
                fallback_func=fallback_func,
                context=op_context,
                *args,
                **kwargs
            )
            
            if not result.success:
                raise result.error
            
            return result.data
        
        return wrapper
    return decorator


def with_retry(max_retries: int = 3, backoff_factor: float = 2.0, circuit_breaker_name: str = None):
    """Decorator for adding retry functionality."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            context = RecoveryContext(
                operation_name=func.__name__,
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                circuit_breaker_name=circuit_breaker_name
            )
            
            result = error_recovery.execute_with_retry(
                func=func,
                context=context,
                *args,
                **kwargs
            )
            
            if not result.success:
                raise result.error
            
            return result.data
        
        return wrapper
    return decorator


def with_graceful_degradation(degraded_func: Callable, context: str = None):
    """Decorator for adding graceful degradation."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_context = context or func.__name__
            result = error_recovery.execute_with_graceful_degradation(
                primary_func=func,
                degraded_func=degraded_func,
                context=op_context,
                *args,
                **kwargs
            )
            
            if not result.success:
                raise result.error
            
            return result.data
        
        return wrapper
    return decorator


# Example usage and testing
if __name__ == "__main__":
    import logging
    import random
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n=== Error Recovery Demo ===\n")
    
    # Example 1: Fallback strategy
    print("1. Fallback strategy:")
    
    def fetch_from_api():
        """Simulate API call that fails."""
        if random.random() < 0.7:  # 70% failure rate
            raise ConnectionError("API unavailable")
        return {"data": "from_api", "timestamp": time.time()}
    
    def load_from_cache():
        """Simulate cache fallback."""
        return {"data": "from_cache", "timestamp": time.time() - 3600}
    
    result = error_recovery.execute_with_fallback(
        primary_func=fetch_from_api,
        fallback_func=load_from_cache,
        context="data_fetch"
    )
    
    print(f"   Success: {result.success}")
    print(f"   Data: {result.data}")
    print(f"   Fallback used: {result.fallback_used}")
    print(f"   Attempts: {result.attempts}")
    
    # Example 2: Retry strategy
    print("\n2. Retry strategy:")
    
    def flaky_service():
        """Simulate flaky service."""
        if random.random() < 0.8:  # 80% failure rate
            raise TimeoutError("Service timeout")
        return {"status": "success"}
    
    result = error_recovery.execute_with_retry(
        func=flaky_service,
        context=RecoveryContext(
            operation_name="flaky_service",
            max_retries=3,
            backoff_factor=1.5
        )
    )
    
    print(f"   Success: {result.success}")
    print(f"   Attempts: {result.attempts}")
    print(f"   Duration: {result.duration:.2f}s")
    
    # Example 3: Graceful degradation
    print("\n3. Graceful degradation:")
    
    def full_feature_service():
        """Simulate full-feature service."""
        raise ServiceUnavailableError("Service down")
    
    def basic_service():
        """Simulate basic service."""
        return {"features": ["basic"], "status": "degraded"}
    
    result = error_recovery.execute_with_graceful_degradation(
        primary_func=full_feature_service,
        degraded_func=basic_service,
        context="feature_service"
    )
    
    print(f"   Success: {result.success}")
    print(f"   Data: {result.data}")
    print(f"   Fallback used: {result.fallback_used}")
    
    # Example 4: Decorator usage
    print("\n4. Decorator usage:")
    
    @with_fallback(load_from_cache)
    def api_call():
        return fetch_from_api()
    
    @with_retry(max_retries=2, backoff_factor=1.0)
    def retry_service():
        return flaky_service()
    
    try:
        result = api_call()
        print(f"   API call result: {result}")
    except Exception as e:
        print(f"   API call failed: {e}")
    
    try:
        result = retry_service()
        print(f"   Retry service result: {result}")
    except Exception as e:
        print(f"   Retry service failed: {e}")
    
    # Example 5: Statistics
    print("\n5. Recovery statistics:")
    stats = error_recovery.get_recovery_stats()
    for operation, events in stats.items():
        print(f"   {operation}: {events}")
    
    print("\n=== Demo complete ===\n")
    print("Error recovery utility is ready for production use!")
    print("Use error_recovery.execute_with_fallback() for resilient operations.")


class ServiceUnavailableError(Exception):
    """Custom exception for service unavailable errors."""
    pass
