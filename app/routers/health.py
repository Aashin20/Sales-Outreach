from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.health import check_postgres_health, check_redis_health
from app.models import HealthResponse, ReadinessResponse


router = APIRouter(tags=["Health"],prefix="/v1")


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


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Returns 200 only if all services are reachable.",
    responses={
        200: {"description": "Service is ready to accept traffic"},
        503: {"description": "Service is not ready — dependencies unhealthy"},
    },
)
async def readyz(request: Request):
    async with request.app.state.db_session_factory() as session:
        checks = await check_all_dependencies(session, request.app.state.redis)

    all_healthy = is_all_healthy(checks)

    response = ReadinessResponse(
        status="ready" if all_healthy else "not_ready",
        timestamp=datetime.now(timezone.utc),
        checks=checks,
    )

    if not all_healthy:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json"),
        )

    return response