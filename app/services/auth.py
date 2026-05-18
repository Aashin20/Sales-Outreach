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


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns: (plaintext_key, key_hash, key_prefix)
    The plaintext is shown once and never stored.
    """
    random_part = secrets.token_urlsafe(KEY_LENGTH)
    plaintext = f"{KEY_PREFIX}{random_part}"
    key_hash = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt()).decode()
    prefix = plaintext[:8]
    return plaintext, key_hash, prefix

