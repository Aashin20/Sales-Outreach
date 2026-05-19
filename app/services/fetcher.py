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
    async def _fetch_url(self, url: str) -> str:
        """Fetch a URL with retry logic for transient failures."""
        # Validate URL against SSRF before every attempt (handles redirects)
        try:
            validate_url(url)
        except SSRFError as e:
            raise FetchError(f"SSRF blocked: {e}")

        async with self._create_client() as client:
            try:
                response = await client.get(url)

                # Check for redirect to blocked IPs
                if response.history:
                    for redirect in response.history:
                        try:
                            validate_url(str(redirect.url))
                        except SSRFError as e:
                            raise FetchError(f"SSRF blocked redirect: {e}")

                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise RetryableFetchError(
                        f"Retryable status {response.status_code} from {url}"
                    )

                if response.status_code >= 400:
                    raise FetchError(
                        f"Non-retryable status {response.status_code} from {url}"
                    )

                return response.text

            except httpx.TimeoutException:
                raise RetryableFetchError(f"Timeout fetching {url}")
            except httpx.ConnectError:
                raise RetryableFetchError(f"Connection error for {url}")
            except (FetchError, RetryableFetchError):
                raise
            except Exception as e:
                raise FetchError(f"Unexpected error fetching {url}: {e}")

    async def fetch_homepage(self, domain: str) -> Optional[str]:
        """Fetch and clean a company homepage."""
        try:
            url = validate_domain_for_fetch(domain)
            raw = await self._fetch_url(url)
            # Strip HTML, normalize whitespace, truncate
            text = strip_html_tags(raw)
            text = normalize_whitespace(text)
            return text[:10000]  # Reasonable limit
        except (FetchError, SSRFError) as e:
            logger.warning("homepage_fetch_failed", domain=domain, error=str(e))
            return None
        except RetryableFetchError as e:
            logger.warning("homepage_fetch_exhausted_retries", domain=domain, error=str(e))
            return None

    async def fetch_news(self, domain: str) -> Optional[str]:
        """
        Fetch recent news about a company.
        """
        news_paths = ["/news", "/press", "/blog", "/newsroom"]
        for path in news_paths:
            try:
                url = f"https://{domain}{path}"
                validate_url(url)
                raw = await self._fetch_url(url)
                text = strip_html_tags(raw)
                text = normalize_whitespace(text)
                if len(text) > 100:  # Has meaningful content
                    return text[:8000]
            except (FetchError, RetryableFetchError, SSRFError):
                continue

        # Fallback: try a DuckDuckGo-style search (simplified)
        logger.info("news_no_dedicated_page", domain=domain)
        return None
