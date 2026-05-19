import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import Settings
from ..models.database import Job, JobStatus
from ..models.schemas import OutreachResult, WebhookPayload
from ..security.sanitizer import sanitize_fetched_content, validate_llm_output
from ..services.cache import CacheService
from ..services.cost import CostService
from ..services.fetcher import WebFetcher
from ..services.llm import LLMClient, CircuitBreakerOpen, HookResult
from ..services.webhook import WebhookService
from ..tracing.tracer import Tracer

logger = structlog.get_logger(__name__)
