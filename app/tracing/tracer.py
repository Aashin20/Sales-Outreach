import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.database import TraceLog

logger = structlog.get_logger(__name__)

