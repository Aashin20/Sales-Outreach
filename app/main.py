from contextlib import asynccontextmanager
import structlog
from arq import create_pool
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from .config import get_settings
from .models.database import Base
from .routers.health import router as health
from .routers.outreach import router as outreach
from .routers.feedback import router as feedback
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

#Middlewares

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": None},
    )


#Routers

app.include_router(health)
app.include_router(outreach)
app.include_router(feedback)



@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Sales Outreach API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/v1/healthz",
    }
