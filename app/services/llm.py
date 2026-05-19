import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional
import structlog
from groq import AsyncGroq, APIError, RateLimitError, APIConnectionError
from pydantic import BaseModel, ValidationError
from tenacity import (retry,stop_after_attempt,
                      wait_exponential_jitter,retry_if_exception_type,)
from app.config import Settings

logger = structlog.get_logger(__name__)

# ── Pydantic Output Schemas ─────────────────────────────────────────


class HookResult(BaseModel):
    """Output schema for pick_hook LLM call."""
    hook: str
    reasoning: str
    evidence: list[str]
    confidence: float  


class OutreachMessage(BaseModel):
    """Output schema for compose_message LLM call."""
    subject: str
    body: str
    tone: str
    call_to_action: str


# ── Circuit Breaker ──────────────────────────────────────────────────


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    States: CLOSED (normal) → OPEN (blocking) → HALF_OPEN (testing)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        window_seconds: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.window_seconds = window_seconds
        self.failures: list[float] = []
        self.state = "CLOSED"
        self.opened_at: Optional[float] = None

    def _clean_old_failures(self):
        now = time.monotonic()
        self.failures = [
            t for t in self.failures
            if now - t < self.window_seconds
        ]

    def record_failure(self):
        self.failures.append(time.monotonic())
        self._clean_old_failures()
        if len(self.failures) >= self.failure_threshold:
            self.state = "OPEN"
            self.opened_at = time.monotonic()
            logger.critical(
                "circuit_breaker_opened",
                failures=len(self.failures),
                threshold=self.failure_threshold,
            )

    def record_success(self):
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failures.clear()
            logger.info("circuit_breaker_closed")

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if self.opened_at and (time.monotonic() - self.opened_at) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("circuit_breaker_half_open")
                return True
            return False
        # HALF_OPEN — allow one request through
        return True


# ── Retryable LLM Errors ────────────────────────────────────────────


class RetryableLLMError(Exception):
    """LLM error that should be retried."""
    pass


class NonRetryableLLMError(Exception):
    """LLM error that should NOT be retried."""
    pass


class SchemaViolationError(Exception):
    """LLM output didn't match expected schema."""
    pass

