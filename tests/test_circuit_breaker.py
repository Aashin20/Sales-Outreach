"""
Tests for circuit breaker logic.
"""

import time
import pytest
from app.services.llm import CircuitBreaker


class TestCircuitBreaker:
    """Test circuit breaker state transitions."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5)
        assert cb.state == "CLOSED"
        assert cb.can_execute() is True

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "CLOSED"
        assert cb.can_execute() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, window_seconds=60)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.can_execute() is False

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)  # 0s recovery
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        # With 0s recovery, should immediately go half-open
        cb.opened_at = time.monotonic() - 1  # Opened 1s ago
        assert cb.can_execute() is True
        assert cb.state == "HALF_OPEN"

    def test_closes_on_success_after_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
        cb.record_failure()
        cb.record_failure()
        cb.opened_at = time.monotonic() - 1
        cb.can_execute()  # Transitions to HALF_OPEN
        cb.record_success()
        assert cb.state == "CLOSED"

    def test_old_failures_expire(self):
        cb = CircuitBreaker(failure_threshold=3, window_seconds=1)
        cb.record_failure()
        cb.record_failure()
        # Simulate time passing beyond window
        cb.failures = [time.monotonic() - 2, time.monotonic() - 2]
        cb.record_failure()  # Only 1 recent failure
        assert cb.state == "CLOSED"  # Old ones expired

    def test_success_resets_on_half_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0)
        cb.record_failure()
        cb.record_failure()
        cb.opened_at = time.monotonic() - 1
        cb.can_execute()
        cb.record_success()
        assert cb.state == "CLOSED"
        assert len(cb.failures) == 0

    def test_multiple_failures_keep_open(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        # Still within recovery timeout
        assert cb.can_execute() is False
