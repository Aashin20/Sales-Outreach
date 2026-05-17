from datetime import datetime, timezone
from typing import Dict
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


async def check_postgres_health(db_session: AsyncSession) -> str:
    """
    Check PostgreSQL connection health.
    
    Returns:
        "healthy" if OK, else error message
    """
    try:
        from sqlalchemy import text
        await db_session.execute(text("SELECT 1"))
        return "healthy"
    except Exception as e:
        error_msg = f"unhealthy: {str(e)[:100]}"
        logger.error("health_postgres_failed", error=str(e))
        return error_msg


async def check_redis_health(redis: Redis) -> str:
    """
    Check Redis connection health.
    
    Returns:
        "healthy" if OK, else error message
    """
    try:
        await redis.ping()
        return "healthy"
    except Exception as e:
        error_msg = f"unhealthy: {str(e)[:100]}"
        logger.error("health_redis_failed", error=str(e))
        return error_msg


async def is_all_healthy(
    db_session: AsyncSession,
    redis: Redis,
) -> Dict[str, str]:
    """
    Check all critical dependencies.
    
    Returns:
        Healthy if all are healthy, else dict of service -> error message
    """
    checks = {
        "postgres": await check_postgres_health(db_session),
        "redis": await check_redis_health(redis),
    }
    return (v == "healthy" for v in checks.values())
