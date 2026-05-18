from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.health import check_postgres_health, check_redis_health
from app.models import HealthResponse, ReadinessResponse


router = APIRouter(tags=["Health"])

