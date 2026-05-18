import uuid
from typing import Optional
import structlog
from arq import ArqRedis
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from ..models.database import ApiKey, Job, JobStatus
from ..models.schemas import OutreachRequest, OutreachResult
from ..services.cache import CacheService, compute_idempotency_key

logger = structlog.get_logger(__name__)

