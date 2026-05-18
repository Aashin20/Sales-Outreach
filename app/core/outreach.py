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


async def create_outreach_job(
    body: OutreachRequest,
    api_key: ApiKey,
    db: AsyncSession,
    redis: Redis,
    arq_redis: ArqRedis,
) -> tuple[Job, str, bool]:
    """
    Create a new outreach job or return cached result.
    
    Returns:
        (job, idempotency_key, is_cached): Job object, idempotency key, whether it's cached
    """
    settings = get_settings()
    cache = CacheService(redis, settings)

    # Compute idempotency key
    idemp_key = compute_idempotency_key(body.domain, body.person_name)

    # Check idempotency cache
    cached_job_id = await cache.get_cached_job_id(idemp_key)
    if cached_job_id:
        result = await db.execute(
            select(Job).where(Job.id == uuid.UUID(cached_job_id))
        )
        cached_job = result.scalar_one_or_none()
        if cached_job:
            return cached_job, idemp_key, True

    # Create new job
    webhook_url = body.webhook_url or api_key.webhook_url
    job = Job(
        idempotency_key=idemp_key,
        api_key_id=api_key.id,
        domain=body.domain,
        person_name=body.person_name,
        status=JobStatus.PENDING,
        webhook_url=webhook_url,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Store in idempotency cache
    await cache.set_idempotency(idemp_key, str(job.id))

    # Enqueue ARQ task
    await arq_redis.enqueue_job(
        "run_research_pipeline",
        str(job.id),
        _job_id=f"research:{job.id}",
    )

    logger.info(
        "job_created",
        job_id=str(job.id),
        domain=body.domain,
        person_name=body.person_name,
    )

    return job, idemp_key, False

