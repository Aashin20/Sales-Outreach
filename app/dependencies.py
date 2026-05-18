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
