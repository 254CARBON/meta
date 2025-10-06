#!/usr/bin/env python3
"""
Retry Decorator with Exponential Backoff

Provides resilient retry logic for external API calls and network operations.
Implements exponential backoff to avoid overwhelming failing services.

Usage:
    from scripts.utils.retry_decorator import retry_with_backoff
    
    @retry_with_backoff(max_attempts=3, backoff_factor=2)
    def make_api_call():
        response = requests.get("https://api.example.com/data")
        response.raise_for_status()
        return response.json()
"""

import time
import logging
from functools import wraps
from typing import Callable, Tuple, Type, Any

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int, float], None] = None
):
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_attempts: Maximum number of attempts (including initial call)
        backoff_factor: Multiplier for delay between retries (e.g., 2.0 doubles delay)
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay in seconds between retries
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback function called on each retry
                  Signature: on_retry(exception, attempt, delay)
    
    Returns:
        Decorated function that implements retry logic
    
    Example:
        @retry_with_backoff(max_attempts=5, backoff_factor=2)
        def fetch_data():
            return requests.get("https://api.example.com/data").json()
        
        # Will retry up to 5 times with delays: 1s, 2s, 4s, 8s, 16s
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempt = 1
            delay = initial_delay
            
            while attempt <= max_attempts:
                try:
                    # Attempt the function call
                    result = func(*args, **kwargs)
                    
                    # Success - log if this wasn't the first attempt
                    if attempt > 1:
                        logger.info(
                            f"✅ {func.__name__} succeeded on attempt {attempt}/{max_attempts}"
                        )
                    
                    return result
                    
                except exceptions as e:
                    # Check if we should retry
                    if attempt >= max_attempts:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_attempts} attempts. "
                            f"Last error: {type(e).__name__}: {str(e)}"
                        )
                        raise
                    
                    # Log the retry
                    logger.warning(
                        f"⚠️  {func.__name__} failed on attempt {attempt}/{max_attempts}. "
                        f"Error: {type(e).__name__}: {str(e)}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    # Call optional retry callback
                    if on_retry:
                        try:
                            on_retry(e, attempt, delay)
                        except Exception as callback_error:
                            logger.warning(
                                f"Retry callback failed: {callback_error}"
                            )
                    
                    # Wait before retrying
                    time.sleep(delay)
                    
                    # Increment attempt and calculate next delay
                    attempt += 1
                    delay = min(delay * backoff_factor, max_delay)
            
            # Should never reach here, but just in case
            raise RuntimeError(f"{func.__name__} exhausted all retry attempts")
        
        return wrapper
    return decorator


def retry_on_rate_limit(
    max_attempts: int = 5,
    initial_delay: float = 60.0,
    backoff_factor: float = 2.0
):
    """
    Specialized retry decorator for API rate limit errors.
    
    Implements longer delays suitable for rate limit recovery.
    
    Args:
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds (default 60s for rate limits)
        backoff_factor: Multiplier for delay between retries
    
    Example:
        @retry_on_rate_limit(max_attempts=3, initial_delay=60)
        def fetch_github_data():
            response = requests.get(
                "https://api.github.com/repos/org/repo",
                headers={"Authorization": f"token {token}"}
            )
            if response.status_code == 429:  # Rate limit exceeded
                raise RateLimitError("GitHub API rate limit exceeded")
            return response.json()
    """
    def is_rate_limit_error(e: Exception) -> bool:
        """Check if exception is a rate limit error."""
        error_str = str(e).lower()
        return any(phrase in error_str for phrase in [
            'rate limit',
            '429',
            'too many requests',
            'quota exceeded'
        ])
    
    def on_rate_limit_retry(e: Exception, attempt: int, delay: float):
        """Custom callback for rate limit retries."""
        logger.warning(
            f"🚦 Rate limit encountered. Waiting {delay:.0f}s before retry "
            f"(attempt {attempt}/{max_attempts})"
        )
    
    return retry_with_backoff(
        max_attempts=max_attempts,
        backoff_factor=backoff_factor,
        initial_delay=initial_delay,
        max_delay=300.0,  # Cap at 5 minutes
        exceptions=(Exception,),
        on_retry=on_rate_limit_retry
    )


class RetryableError(Exception):
    """Base exception for errors that should trigger retries."""
    pass


class NonRetryableError(Exception):
    """Exception for errors that should NOT trigger retries."""
    pass


# Example usage and testing
if __name__ == "__main__":
    import requests
    
    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Example 1: Simple retry
    @retry_with_backoff(max_attempts=3, backoff_factor=2)
    def flaky_function(fail_count: int = 2):
        """Simulates a function that fails a few times then succeeds."""
        if not hasattr(flaky_function, 'attempts'):
            flaky_function.attempts = 0
        
        flaky_function.attempts += 1
        
        if flaky_function.attempts <= fail_count:
            raise ConnectionError(f"Simulated failure #{flaky_function.attempts}")
        
        return f"Success after {flaky_function.attempts} attempts!"
    
    # Example 2: HTTP request with retry
    @retry_with_backoff(
        max_attempts=3,
        backoff_factor=2,
        exceptions=(requests.RequestException,)
    )
    def fetch_data(url: str):
        """Fetch data from URL with automatic retry."""
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    
    # Example 3: Custom retry callback
    retry_count = {'value': 0}
    
    def count_retries(e: Exception, attempt: int, delay: float):
        """Track retry attempts."""
        retry_count['value'] += 1
        logger.info(f"Custom callback: Retry #{retry_count['value']}")
    
    @retry_with_backoff(
        max_attempts=3,
        on_retry=count_retries
    )
    def function_with_callback():
        if retry_count['value'] < 2:
            raise ValueError("Not ready yet")
        return "Success!"
    
    # Run examples
    print("\n=== Example 1: Simple Retry ===")
    try:
        result = flaky_function(fail_count=2)
        print(f"Result: {result}")
    except Exception as e:
        print(f"Failed: {e}")
    
    print("\n=== Example 3: Custom Callback ===")
    try:
        result = function_with_callback()
        print(f"Result: {result}")
        print(f"Total retries: {retry_count['value']}")
    except Exception as e:
        print(f"Failed: {e}")
    
    print("\n=== Retry decorator examples complete ===")
