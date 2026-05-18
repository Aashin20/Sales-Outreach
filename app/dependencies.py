from typing import Annotated, AsyncGenerator
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from .models.database import ApiKey
from .security.auth import validate_api_key
from .services.cost import CostService
from app.config import get_settings

logger = structlog.get_logger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session from session factory."""
    async with request.app.state.db_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_redis(request: Request) -> Redis:
    """Fetch Redis connection."""
    return request.app.state.redis


async def get_authenticated_key(
    db: Annotated[AsyncSession, Depends(get_db)],
    api_key: Annotated[str | None, Depends(api_key_header)],
) -> ApiKey:
    """Validate the API key and return the key record."""
    return await validate_api_key(db, api_key)


async def check_cost_budget(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
    api_key: Annotated[ApiKey, Depends(get_authenticated_key)],
) -> ApiKey:
    """
    Check cost budget before processing.
    Returns the API key if within budget, raises 429 if exceeded.
    """
    settings = get_settings()
    cost_service = CostService(redis, settings)

    budget = await cost_service.check_key_budget(
        api_key.id, api_key.daily_cost_limit_usd
    )

    if budget["blocked"]:
        retry_after = cost_service.seconds_until_midnight_utc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Daily cost limit exceeded",
                "spent_usd": budget["spent_usd"],
                "limit_usd": budget["limit_usd"],
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )

    return api_key
