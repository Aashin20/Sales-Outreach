import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


def compute_idempotency_key(domain: str, person_name: str) -> str:
    """
    Compute the idempotency key for a (domain, person, week) triple.
    Uses ISO week number so the key naturally rotates weekly.
    """
    now = datetime.now(timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    raw = f"{domain.lower().strip()}:{person_name.lower().strip()}:{iso_year}:{iso_week}"
    return hashlib.sha256(raw.encode()).hexdigest()

