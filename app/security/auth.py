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


def hash_key_for_lookup(plaintext: str) -> str:
    """
    Create a fast lookup hash (SHA-256) for the API key
    """
    return hashlib.sha256(plaintext.encode()).hexdigest()


def generate_api_key_v2() -> tuple[str, str, str]:
    """
    Generate a new API key with SHA-256 hash for fast lookup.
    Returns: (plaintext_key, sha256_hash, key_prefix)
    """
    random_part = secrets.token_urlsafe(KEY_LENGTH)
    plaintext = f"{KEY_PREFIX}{random_part}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    prefix = plaintext[:8]
    return plaintext, key_hash, prefix


async def validate_api_key(
    db: AsyncSession,
    api_key: Optional[str],
) -> ApiKey:
    """
    Validate an API key against the database.
    Returns the ApiKey record or raises 401/403.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
        )

    # Fast lookup via SHA-256 hash
    key_hash = hash_key_for_lookup(api_key)

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    )
    db_key = result.scalar_one_or_none()

    if not db_key:
        logger.warning("auth_failed", reason="key_not_found", prefix=api_key[:8] if len(api_key) >= 8 else "???")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    if not db_key.is_active:
        logger.warning("auth_failed", reason="key_revoked", key_prefix=db_key.key_prefix)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key has been revoked.",
        )

    # Update last used timestamp
    db_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return db_key


async def revoke_api_key(db: AsyncSession, key_id: UUID) -> bool:
    """Revoke an API key by marking it inactive."""
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    db_key = result.scalar_one_or_none()
    if not db_key:
        return False

    db_key.is_active = False
    db_key.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("api_key_revoked", key_prefix=db_key.key_prefix, key_id=str(key_id))
    return True
