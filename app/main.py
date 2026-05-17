from contextlib import asynccontextmanager
import structlog
from arq import create_pool
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings
from app.models.database import Base
from app.routers import health, outreach, feedback
from app.worker.settings import get_redis_settings
import uuid
