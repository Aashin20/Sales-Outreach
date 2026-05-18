from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)
