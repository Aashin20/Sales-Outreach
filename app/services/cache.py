import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


def compute_idempotency_key(domain: str, person_name: str) -> str:
    """
    Compute the idempotency key for a (domain, person, week) triple.
    Uses ISO week number so the key naturally rotates weekly.
    """
    now = datetime.now(timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    raw = f"{domain.lower().strip()}:{person_name.lower().strip()}:{iso_year}:{iso_week}"
    return hashlib.sha256(raw.encode()).hexdigest()


class CacheService:
    """Manages idempotency and partial-result caching via Redis."""

    def __init__(self, redis: Redis, settings):
        self.redis = redis
        self.settings = settings

    #Idempotency Cache 

    async def get_cached_job_id(self, idempotency_key: str) -> Optional[str]:
        """Check if this idempotency key already has a job."""
        result = await self.redis.get(f"idempotency:{idempotency_key}")
        if result:
            logger.info("idempotency_cache_hit", key=idempotency_key[:16])
        return result.decode() if result else None

    async def set_idempotency(self, idempotency_key: str, job_id: str):
        """Store the job_id for this idempotency key."""
        await self.redis.setex(
            f"idempotency:{idempotency_key}",
            self.settings.idempotency_ttl_seconds,
            job_id,
        )

    #  Partial-Result Cache 

    def _signal_cache_key(self, domain: str, signal_type: str) -> str:
        return f"company:{domain.lower()}:{signal_type}"

    def _signal_ttl(self, signal_type: str) -> int:
        """TTL varies by signal type — fresher signals need shorter TTL."""
        ttl_map = {
            "homepage": self.settings.homepage_cache_ttl_seconds,
            "news": self.settings.news_cache_ttl_seconds,
            "profile": self.settings.profile_cache_ttl_seconds,
        }
        return ttl_map.get(signal_type, 3600)  # Default 1h

    async def get_cached_signal(self, domain: str, signal_type: str) -> Optional[str]:
        """
        Get a cached signal for a company domain.
        Returns None if not cached or expired.
        """
        key = self._signal_cache_key(domain, signal_type)
        result = await self.redis.get(key)
        if result:
            logger.info(
                "signal_cache_hit",
                domain=domain,
                signal_type=signal_type,
            )
            return result.decode()
        return None

    async def set_cached_signal(
        self, domain: str, signal_type: str, content: str
    ):
        """Cache a fetched signal for a company domain."""
        key = self._signal_cache_key(domain, signal_type)
        ttl = self._signal_ttl(signal_type)
        await self.redis.setex(key, ttl, content)
        logger.debug(
            "signal_cached",
            domain=domain,
            signal_type=signal_type,
            ttl=ttl,
        )

    # Cache Stats

    async def get_cache_stats(self) -> dict:
        """Get basic cache statistics."""
        info = await self.redis.info("keyspace")
        return {
            "keyspace": info,
        }
