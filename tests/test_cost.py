"""
Tests for cost tracking and budget enforcement.
"""

import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from app.services.cost import CostService
from app.config import Settings


@pytest.fixture
def cost_settings():
    return Settings(
        groq_api_key="test",
        per_key_daily_cost_limit_usd=10.0,
        global_daily_cost_limit_usd=100.0,
        cost_warning_threshold=0.90,
    )


@pytest.fixture
def cost_service(mock_redis, cost_settings):
    return CostService(mock_redis, cost_settings)


@pytest.fixture
def api_key_id():
    return uuid.uuid4()


class TestCostRecording:
    """Test cost recording to Redis."""

    @pytest.mark.asyncio
    async def test_record_cost(self, cost_service, mock_redis, api_key_id):
        await cost_service.record_cost(api_key_id, 0.001)
        # Should record to both per-key and global counters
        assert mock_redis.incrby.call_count == 2
        # First call = per-key, second = global
        per_key_call = mock_redis.incrby.call_args_list[0]
        assert per_key_call[0][1] == 1000  # 0.001 USD = 1000 micro-dollars

    @pytest.mark.asyncio
    async def test_record_cost_precision(self, cost_service, mock_redis, api_key_id):
        """Micro-dollar precision should handle small costs correctly."""
        await cost_service.record_cost(api_key_id, 0.000123)
        per_key_call = mock_redis.incrby.call_args_list[0]
        assert per_key_call[0][1] == 123  # 123 micro-dollars


class TestBudgetChecks:
    """Test per-key and global budget enforcement."""

    @pytest.mark.asyncio
    async def test_under_budget(self, cost_service, mock_redis, api_key_id):
        mock_redis.get.return_value = b"1000000"  # $1.00 spent
        result = await cost_service.check_key_budget(api_key_id, 10.0)
        assert result["blocked"] is False
        assert result["warning"] is False
        assert result["spent_usd"] == 1.0

    @pytest.mark.asyncio
    async def test_warning_threshold(self, cost_service, mock_redis, api_key_id):
        mock_redis.get.return_value = b"9500000"  # $9.50 of $10 limit
        result = await cost_service.check_key_budget(api_key_id, 10.0)
        assert result["blocked"] is False
        assert result["warning"] is True
        assert result["ratio"] == 0.95

    @pytest.mark.asyncio
    async def test_budget_exceeded(self, cost_service, mock_redis, api_key_id):
        mock_redis.get.return_value = b"10000000"  # $10.00 = at limit
        result = await cost_service.check_key_budget(api_key_id, 10.0)
        assert result["blocked"] is True

    @pytest.mark.asyncio
    async def test_over_budget(self, cost_service, mock_redis, api_key_id):
        mock_redis.get.return_value = b"15000000"  # $15 > $10 limit
        result = await cost_service.check_key_budget(api_key_id, 10.0)
        assert result["blocked"] is True
        assert result["ratio"] == 1.5

    @pytest.mark.asyncio
    async def test_no_spend(self, cost_service, mock_redis, api_key_id):
        mock_redis.get.return_value = None  # No spend recorded
        result = await cost_service.check_key_budget(api_key_id, 10.0)
        assert result["blocked"] is False
        assert result["spent_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_global_budget_normal(self, cost_service, mock_redis):
        mock_redis.get.return_value = b"50000000"  # $50 of $100
        result = await cost_service.check_global_budget()
        assert result["degraded"] is False

    @pytest.mark.asyncio
    async def test_global_budget_degraded(self, cost_service, mock_redis):
        mock_redis.get.return_value = b"100000000"  # $100 = at limit
        result = await cost_service.check_global_budget()
        assert result["degraded"] is True

    @pytest.mark.asyncio
    async def test_cost_headers_normal(self, cost_service, mock_redis, api_key_id):
        mock_redis.get.return_value = b"5000000"  # $5.00
        headers = await cost_service.get_cost_headers(api_key_id, 10.0)
        assert "X-Cost-Spent-Today" in headers
        assert "X-Cost-Limit-Today" in headers
        assert "X-Cost-Warning" not in headers

    @pytest.mark.asyncio
    async def test_cost_headers_warning(self, cost_service, mock_redis, api_key_id):
        mock_redis.get.return_value = b"9200000"  # $9.20 = 92% of $10
        headers = await cost_service.get_cost_headers(api_key_id, 10.0)
        assert headers["X-Cost-Warning"] == "approaching-limit"


class TestRetryAfter:
    """Test Retry-After calculation."""

    def test_seconds_until_midnight(self, cost_service):
        seconds = cost_service.seconds_until_midnight_utc()
        assert 0 < seconds <= 86400
