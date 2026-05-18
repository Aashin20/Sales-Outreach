from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.health import check_postgres_health, check_redis_health
from app.models import HealthResponse, ReadinessResponse


router = APIRouter(tags=["Health"])


async def check_all_dependencies(db_session: AsyncSession, redis: Redis) -> Dict[str, str]:
    return {
        "postgres": await check_postgres_health(db_session),
        "redis": await check_redis_health(redis),
    }


def is_all_healthy(checks: Dict[str, str]) -> bool:
    return all(result == "healthy" for result in checks.values())


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Health endpoint",
    description="Returns 200 if the process is alive.",
    responses={
        200: {"description": "Process is alive"},
    },
)
async def healthz():
    return HealthResponse(
        status="alive",
        timestamp=datetime.now(timezone.utc),
    )

