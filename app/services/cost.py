from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class CostService:
    """Tracks and enforces LLM spend budgets."""

    def __init__(self, redis: Redis, settings):
        self.redis = redis
        self.settings = settings

    def _today_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _per_key_redis_key(self, api_key_id: UUID) -> str:
        return f"cost:{api_key_id}:{self._today_key()}"

    def _global_redis_key(self) -> str:
        return f"cost:global:{self._today_key()}"
