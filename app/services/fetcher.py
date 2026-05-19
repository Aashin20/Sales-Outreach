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

