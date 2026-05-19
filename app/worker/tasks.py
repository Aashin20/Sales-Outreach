import uuid
from typing import Any
import structlog
from arq import ArqRedis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from redis.asyncio import Redis
from app.config import get_settings
from ..services.cache import CacheService
from ..services.cost import CostService
from ..services.fetcher import WebFetcher
from ..services.llm import LLMClient
from ..services.research import ResearchPipeline
from ..services.webhook import WebhookService
from ..tracing.tracer import Tracer
from ..worker.settings import get_redis_settings

logger = structlog.get_logger(__name__)


async def startup(ctx: dict[str, Any]):
    """Initialize worker resources on startup."""
    settings = get_settings()

    # Database
    engine = create_async_engine(settings.database_url, pool_size=5, max_overflow=10)
    ctx["db_session_factory"] = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Redis 
    ctx["redis"] = Redis.from_url(settings.redis_url, decode_responses=False)

    # Services
    ctx["settings"] = settings
    ctx["cache"] = CacheService(ctx["redis"], settings)
    ctx["cost"] = CostService(ctx["redis"], settings)
    ctx["fetcher"] = WebFetcher(
        timeout_seconds=settings.fetch_timeout_seconds,
        max_retries=3,
    )
    ctx["llm"] = LLMClient(settings)
    ctx["webhook"] = WebhookService(
        secret=settings.webhook_secret,
        timeout=settings.webhook_timeout_seconds,
        max_retries=settings.webhook_max_retries,
    )
    ctx["tracer"] = Tracer(settings.trace_file_path)

    logger.info("worker_started")


async def shutdown(ctx: dict[str, Any]):
    """Clean up worker resources on shutdown."""
    if "redis" in ctx:
        await ctx["redis"].close()
    logger.info("worker_stopped")


async def run_research_pipeline(ctx: dict[str, Any], job_id: str):
    """
    ARQ task: execute the research pipeline for a job.
    """
    logger.info("task_started", job_id=job_id)

    settings = ctx["settings"]

    async with ctx["db_session_factory"]() as db:
        pipeline = ResearchPipeline(
            settings=settings,
            db=db,
            cache=ctx["cache"],
            cost=ctx["cost"],
            fetcher=ctx["fetcher"],
            llm=ctx["llm"],
            webhook=ctx["webhook"],
            tracer=ctx["tracer"],
        )

        await pipeline.run(uuid.UUID(job_id))

    logger.info("task_completed", job_id=job_id)

