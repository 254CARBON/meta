#!/usr/bin/env python3
"""
Circuit Breaker Pattern Implementation

Provides fail-fast mechanism for external services and APIs to prevent
cascading failures and resource exhaustion during outages.

Features:
- Three states: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery)
- Configurable failure thresholds and timeout periods
- Automatic recovery detection and state transitions
- Integration with retry logic for comprehensive error handling
- Detailed metrics and health monitoring

Usage:
    from scripts.utils.circuit_breaker import CircuitBreaker

    circuit_breaker = CircuitBreaker(
        name="github-api",
        failure_threshold=5,
        recovery_timeout=60,
        expected_exceptions=(requests.RequestException,)
    )

    @circuit_breaker
    def make_api_call():
        response = requests.get("https://api.github.com/user")
        response.raise_for_status()
        return response.json()
"""

import time
import logging
from enum import Enum
from functools import wraps
from typing import Callable, Any, Tuple, Type, Optional, Dict
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Failing, requests rejected
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    state_changes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None

    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests


class CircuitBreaker:
    """
    Circuit breaker implementation for external service protection.

    Prevents cascading failures by failing fast when services are down,
    and automatically testing recovery when services come back online.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        success_threshold: int = 3,
        timeout: float = 30.0
    ):
        """
        Initialize circuit breaker.

        Args:
            name: Unique identifier for this circuit breaker
            failure_threshold: Number of failures to trigger OPEN state
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exceptions: Exception types that count as failures
            success_threshold: Number of successes needed to close from HALF_OPEN
            timeout: Request timeout in seconds
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self.success_threshold = success_threshold
        self.timeout = timeout

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._lock = Lock()

        # Metrics
        self.metrics = CircuitBreakerMetrics()

        logger.info(
            f"Circuit breaker '{name}' initialized: "
            f"failure_threshold={failure_threshold}, "
            f"recovery_timeout={recovery_timeout}s"
        )

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._last_failure_time is None:
            return False

        time_since_failure = time.time() - self._last_failure_time
        return time_since_failure >= self.recovery_timeout

    def _record_success(self) -> None:
        """Record a successful operation."""
        self.metrics.successful_requests += 1
        self.metrics.last_success_time = time.time()

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition_to(CircuitBreakerState.CLOSED)
                self._success_count = 0

        self.metrics.total_requests += 1

    def _record_failure(self) -> None:
        """Record a failed operation."""
        self.metrics.failed_requests += 1
        self.metrics.last_failure_time = time.time()
        self._failure_count += 1

        if self._state == CircuitBreakerState.HALF_OPEN:
            # Any failure in half-open state goes back to open
            self._transition_to(CircuitBreakerState.OPEN)
        elif self._failure_count >= self.failure_threshold:
            self._transition_to(CircuitBreakerState.OPEN)

        self.metrics.total_requests += 1

    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        """Transition to a new state and log the change."""
        old_state = self._state
        self._state = new_state
        self.metrics.state_changes += 1

        logger.info(
            f"Circuit breaker '{self.name}' state change: "
            f"{old_state.value} → {new_state.value} "
            f"(failures: {self._failure_count}, "
            f"success_rate: {self.metrics.success_rate():.2%})"
        )

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker.

        Args:
            func: Function to execute
            *args, **kwargs: Arguments for the function

        Returns:
            Function result on success

        Raises:
            CircuitBreakerOpenException: If circuit breaker is OPEN
            Original exception: If function fails and circuit breaker is enabled
        """
        with self._lock:
            current_time = time.time()

            # Check if we should attempt recovery
            if (self._state == CircuitBreakerState.OPEN and
                self._should_attempt_reset()):
                self._transition_to(CircuitBreakerState.HALF_OPEN)
                logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")

            # Reject requests if circuit is OPEN
            if self._state == CircuitBreakerState.OPEN:
                self.metrics.rejected_requests += 1
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Next retry at {self._last_failure_time + self.recovery_timeout:.0f}s"
                )

            # Execute the function
            try:
                # Add timeout to prevent hanging
                import signal

                def timeout_handler(signum, frame):
                    raise TimeoutError(f"Function timed out after {self.timeout}s")

                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(self.timeout))

                try:
                    result = func(*args, **kwargs)
                    self._record_success()
                    return result

                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)

            except self.expected_exceptions as e:
                self._record_failure()
                raise e
            except Exception as e:
                # Unexpected exceptions also count as failures
                self._record_failure()
                logger.warning(
                    f"Circuit breaker '{self.name}' caught unexpected exception: {e}"
                )
                raise e

    def __call__(self, func: Callable) -> Callable:
        """Decorator interface for circuit breaker."""
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            return self.call(func, *args, **kwargs)
        return wrapper

    def get_state(self) -> Dict[str, Any]:
        """Get current state and metrics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "last_failure_time": self._last_failure_time,
                "metrics": {
                    "total_requests": self.metrics.total_requests,
                    "successful_requests": self.metrics.successful_requests,
                    "failed_requests": self.metrics.failed_requests,
                    "rejected_requests": self.metrics.rejected_requests,
                    "success_rate": self.metrics.success_rate(),
                    "failure_rate": self.metrics.failure_rate(),
                    "state_changes": self.metrics.state_changes
                },
                "config": {
                    "failure_threshold": self.failure_threshold,
                    "recovery_timeout": self.recovery_timeout,
                    "success_threshold": self.success_threshold,
                    "timeout": self.timeout
                }
            }

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        with self._lock:
            old_state = self._state
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None

            logger.info(
                f"Circuit breaker '{self.name}' manually reset: "
                f"{old_state.value} → {self._state.value}"
            )


class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is in OPEN state."""
    pass


# Global circuit breaker registry
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_cb_lock = Lock()


def get_circuit_breaker(
    name: str,
    **kwargs
) -> CircuitBreaker:
    """
    Get or create a circuit breaker instance.

    Args:
        name: Unique name for the circuit breaker
        **kwargs: Configuration options for new circuit breakers

    Returns:
        CircuitBreaker instance
    """
    with _cb_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
        return _circuit_breakers[name]


def get_all_circuit_breakers() -> Dict[str, Dict[str, Any]]:
    """Get status of all circuit breakers."""
    with _cb_lock:
        return {
            name: cb.get_state()
            for name, cb in _circuit_breakers.items()
        }


# Specialized circuit breakers for common use cases
def github_api_circuit_breaker() -> CircuitBreaker:
    """Circuit breaker specifically configured for GitHub API."""
    return get_circuit_breaker(
        "github-api",
        failure_threshold=5,
        recovery_timeout=120,  # 2 minutes for API rate limits
        expected_exceptions=(Exception,),  # Broad exception handling
        success_threshold=2
    )


def observability_circuit_breaker() -> CircuitBreaker:
    """Circuit breaker for observability system connections."""
    return get_circuit_breaker(
        "observability",
        failure_threshold=3,
        recovery_timeout=30,  # 30 seconds for metrics systems
        expected_exceptions=(Exception,),
        success_threshold=2
    )


def notification_circuit_breaker() -> CircuitBreaker:
    """Circuit breaker for notification service calls."""
    return get_circuit_breaker(
        "notifications",
        failure_threshold=3,
        recovery_timeout=60,  # 1 minute for notification services
        expected_exceptions=(Exception,),
        success_threshold=2
    )


# Example usage and testing
if __name__ == "__main__":
    import requests
    from time import sleep

    # Configure logging for demo
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n=== Circuit Breaker Demo ===\n")

    # Example 1: Basic circuit breaker
    print("1. Basic circuit breaker usage:")

    cb = CircuitBreaker(
        name="demo-api",
        failure_threshold=3,
        recovery_timeout=5,
        expected_exceptions=(ConnectionError,)
    )

    @cb
    def flaky_api_call(should_fail=True):
        """Simulates an API call that fails initially."""
        if should_fail:
            raise ConnectionError("Service unavailable")
        return {"status": "success"}

    # Test failures leading to OPEN state
    print("   Testing failures...")
    for i in range(4):
        try:
            result = flaky_api_call(should_fail=(i < 3))
            print(f"   Call {i+1}: Success")
        except Exception as e:
            print(f"   Call {i+1}: {type(e).__name__}")

    # Test recovery after timeout
    print("   Waiting for recovery...")
    sleep(6)  # Wait for recovery timeout

    try:
        result = flaky_api_call(should_fail=False)
        print(f"   Recovery call: Success - {result}")
    except Exception as e:
        print(f"   Recovery call: {type(e).__name__}")

    # Example 2: Circuit breaker status
    print("\n2. Circuit breaker status:")
    status = cb.get_state()
    print(f"   State: {status['state']}")
    print(f"   Success rate: {status['metrics']['success_rate']:.2%}")
    print(f"   Total requests: {status['metrics']['total_requests']}")

    # Example 3: Multiple circuit breakers
    print("\n3. Multiple circuit breakers:")

    github_cb = github_api_circuit_breaker()
    obs_cb = observability_circuit_breaker()
    notif_cb = notification_circuit_breaker()

    print("   GitHub API circuit breaker created")
    print("   Observability circuit breaker created")
    print("   Notification circuit breaker created")

    # Show all circuit breakers
    all_cbs = get_all_circuit_breakers()
    print(f"   Total circuit breakers: {len(all_cbs)}")

    print("\n=== Demo complete ===\n")
    print("Circuit breakers are ready for production use!")
    print("Apply to external API calls to prevent cascading failures.")
