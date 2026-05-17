from contextlib import asynccontextmanager
import structlog
from arq import create_pool
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings
from .models.database import Base
from .routers import health, outreach, feedback
from .worker.settings import get_redis_settings
import uuid

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):

    settings = get_settings()

    #Startup
    logger.info("app_starting", debug=settings.debug)

    engine = create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        echo=settings.debug,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app.state.db_engine = engine
    app.state.db_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    app.state.redis = Redis.from_url(
        settings.redis_url, decode_responses=False
    )

    app.state.arq_redis = await create_pool(get_redis_settings())

    logger.info("app_started")

    yield

    # Shutdown
    logger.info("app_stopping")

    await app.state.arq_redis.close()
    await app.state.redis.close()
    await engine.dispose()

    logger.info("app_stopped")



app = FastAPI(
    title="Sales Outreach API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
