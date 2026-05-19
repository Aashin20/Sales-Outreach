"""
Pytest configuration and shared fixtures.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import Settings
from app.models.database import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings():
    """Test settings with safe defaults."""
    return Settings(
        groq_api_key="test-key-not-real",
        database_url="sqlite+aiosqlite:///test.db",
        redis_url="redis://localhost:6379/1",
        per_key_daily_cost_limit_usd=10.0,
        global_daily_cost_limit_usd=100.0,
        webhook_secret="test-secret",
        trace_file_path="./test_traces.jsonl",
    )


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.incrby = AsyncMock()
    redis.expire = AsyncMock()
    redis.ping = AsyncMock()
    redis.info = AsyncMock(return_value={})
    return redis


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.close = AsyncMock()
    return db


@pytest.fixture
def sample_api_key():
    """Sample API key record."""
    from app.models.database import ApiKey
    key = MagicMock(spec=ApiKey)
    key.id = uuid.uuid4()
    key.key_hash = "test_hash"
    key.key_prefix = "oai_test"
    key.name = "Test Key"
    key.rate_limit_per_minute = 60
    key.daily_cost_limit_usd = 10.0
    key.webhook_url = None
    key.is_active = True
    return key


@pytest.fixture
def sample_job_id():
    return uuid.uuid4()
