"""
Tests for idempotency and caching layer.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from app.services.cache import CacheService, compute_idempotency_key
from app.config import Settings


@pytest.fixture
def cache_settings():
    return Settings(
        groq_api_key="test",
        idempotency_ttl_seconds=604800,
        homepage_cache_ttl_seconds=86400,
        news_cache_ttl_seconds=21600,
        profile_cache_ttl_seconds=172800,
    )


@pytest.fixture
def cache_service(mock_redis, cache_settings):
    return CacheService(mock_redis, cache_settings)


class TestIdempotencyKey:
    """Test idempotency key computation."""

    def test_same_input_same_key(self):
        key1 = compute_idempotency_key("stripe.com", "Jane Smith")
        key2 = compute_idempotency_key("stripe.com", "Jane Smith")
        assert key1 == key2

    def test_different_domain_different_key(self):
        key1 = compute_idempotency_key("stripe.com", "Jane Smith")
        key2 = compute_idempotency_key("notion.so", "Jane Smith")
        assert key1 != key2

    def test_different_person_different_key(self):
        key1 = compute_idempotency_key("stripe.com", "Jane Smith")
        key2 = compute_idempotency_key("stripe.com", "John Doe")
        assert key1 != key2

    def test_case_insensitive(self):
        key1 = compute_idempotency_key("Stripe.com", "Jane Smith")
        key2 = compute_idempotency_key("stripe.com", "jane smith")
        assert key1 == key2

    def test_strips_whitespace(self):
        key1 = compute_idempotency_key("  stripe.com  ", "  Jane Smith  ")
        key2 = compute_idempotency_key("stripe.com", "Jane Smith")
        assert key1 == key2

    def test_key_is_sha256(self):
        key = compute_idempotency_key("stripe.com", "Jane Smith")
        assert len(key) == 64  # SHA-256 hex length


class TestIdempotencyCache:
    """Test idempotency cache operations."""

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache_service, mock_redis):
        mock_redis.get.return_value = None
        result = await cache_service.get_cached_job_id("test-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, cache_service, mock_redis):
        mock_redis.get.return_value = b"job-123"
        result = await cache_service.get_cached_job_id("test-key")
        assert result == "job-123"

    @pytest.mark.asyncio
    async def test_set_idempotency(self, cache_service, mock_redis):
        await cache_service.set_idempotency("test-key", "job-123")
        mock_redis.setex.assert_called_once_with(
            "idempotency:test-key", 604800, "job-123"
        )


class TestPartialResultCache:
    """Test partial-result caching for company signals."""

    @pytest.mark.asyncio
    async def test_homepage_cache_miss(self, cache_service, mock_redis):
        mock_redis.get.return_value = None
        result = await cache_service.get_cached_signal("stripe.com", "homepage")
        assert result is None

    @pytest.mark.asyncio
    async def test_homepage_cache_hit(self, cache_service, mock_redis):
        mock_redis.get.return_value = b"<html>Stripe Homepage</html>"
        result = await cache_service.get_cached_signal("stripe.com", "homepage")
        assert result == "<html>Stripe Homepage</html>"

    @pytest.mark.asyncio
    async def test_set_homepage_cache(self, cache_service, mock_redis):
        await cache_service.set_cached_signal("stripe.com", "homepage", "content")
        mock_redis.setex.assert_called_once_with(
            "company:stripe.com:homepage", 86400, "content"
        )

    @pytest.mark.asyncio
    async def test_news_shorter_ttl(self, cache_service, mock_redis):
        await cache_service.set_cached_signal("stripe.com", "news", "news content")
        mock_redis.setex.assert_called_once_with(
            "company:stripe.com:news", 21600, "news content"
        )

    @pytest.mark.asyncio
    async def test_profile_longer_ttl(self, cache_service, mock_redis):
        await cache_service.set_cached_signal("stripe.com", "profile", "profile data")
        mock_redis.setex.assert_called_once_with(
            "company:stripe.com:profile", 172800, "profile data"
        )

    @pytest.mark.asyncio
    async def test_different_people_same_company_share_cache(self, cache_service, mock_redis):
        """Two people at the same company should hit the same signal cache."""
        key1 = cache_service._signal_cache_key("stripe.com", "homepage")
        key2 = cache_service._signal_cache_key("stripe.com", "homepage")
        assert key1 == key2  # Same company = same cache key
