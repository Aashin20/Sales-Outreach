import asyncio
from typing import Optional
import httpx
import structlog
from tenacity import (retry,stop_after_attempt,wait_exponential_jitter,
                      retry_if_exception_type)
from app.security.ssrf import validate_url, validate_domain_for_fetch, SSRFError
from app.security.sanitizer import strip_html_tags, normalize_whitespace

logger = structlog.get_logger(__name__)

# Retryable HTTP status codes
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """Non-retryable fetch error."""
    pass


class RetryableFetchError(Exception):
    """Retryable fetch error."""
    pass


class WebFetcher:
    """Async web content fetcher with safety and resilience."""

    def __init__(self, timeout_seconds: int = 10, max_retries: int = 3):
        self.timeout = timeout_seconds
        self.max_retries = max_retries

    def _create_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            max_redirects=3,
            headers={
                "User-Agent": "OutreachBot/1.0 (research; +https://outreach-api.example.com)",
                "Accept": "text/html,application/xhtml+xml,text/plain",
            },
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
        retry=retry_if_exception_type(RetryableFetchError),
        reraise=True,
    )
