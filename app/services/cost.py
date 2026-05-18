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

    # Record Cost

    async def record_cost(self, api_key_id: UUID, cost_usd: float):
        """
        Record LLM spend for both per-key and global counters.
        Costs are stored as integer micro-dollars for precision.
        """
        micro_dollars = int(cost_usd * 1_000_000)

        # Per-key counter
        per_key = self._per_key_redis_key(api_key_id)
        await self.redis.incrby(per_key, micro_dollars)
        await self.redis.expire(per_key, 86400 + 3600)  # TTL: 25 hours

        # Global counter
        global_key = self._global_redis_key()
        await self.redis.incrby(global_key, micro_dollars)
        await self.redis.expire(global_key, 86400 + 3600)

        logger.debug(
            "cost_recorded",
            api_key_id=str(api_key_id),
            cost_usd=cost_usd,
        )

    # Check Budget

    async def get_key_spend_today(self, api_key_id: UUID) -> float:
        """Get today's spend for an API key in USD."""
        raw = await self.redis.get(self._per_key_redis_key(api_key_id))
        if raw is None:
            return 0.0
        return int(raw) / 1_000_000

    async def get_global_spend_today(self) -> float:
        """Get today's total global spend in USD."""
        raw = await self.redis.get(self._global_redis_key())
        if raw is None:
            return 0.0
        return int(raw) / 1_000_000

    async def check_key_budget(
        self, api_key_id: UUID, key_limit: float
    ) -> dict:
        """
        Check if an API key is within budget.
        Returns status info including warning/blocked state.
        """
        spent = await self.get_key_spend_today(api_key_id)
        ratio = spent / key_limit if key_limit > 0 else 0

        result = {
            "spent_usd": spent,
            "limit_usd": key_limit,
            "ratio": ratio,
            "blocked": ratio >= 1.0,
            "warning": ratio >= self.settings.cost_warning_threshold,
        }

        if result["blocked"]:
            logger.warning(
                "key_budget_exceeded",
                api_key_id=str(api_key_id),
                spent=spent,
                limit=key_limit,
            )
        elif result["warning"]:
            logger.info(
                "key_budget_warning",
                api_key_id=str(api_key_id),
                spent=spent,
                limit=key_limit,
                ratio=ratio,
            )

        return result
