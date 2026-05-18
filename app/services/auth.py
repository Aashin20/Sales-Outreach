import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import bcrypt
import structlog
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.database import ApiKey

logger = structlog.get_logger(__name__)

# API key header scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Key format: "oai_" prefix + 48 random chars
KEY_PREFIX = "oai_"
KEY_LENGTH = 48

