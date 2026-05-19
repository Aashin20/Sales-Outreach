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


class TraceEntry:
    """A single trace entry for a pipeline stage."""

    def __init__(
        self,
        job_id: UUID,
        stage: str,
        model: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ):
        self.job_id = job_id
        self.stage = stage
        self.model = model
        self.prompt_version = prompt_version
        self.start_time = time.monotonic()
        self.timestamp = datetime.now(timezone.utc)
        self.tokens_in: Optional[int] = None
        self.tokens_out: Optional[int] = None
        self.cost_usd: Optional[float] = None
        self.cache_hit: bool = False
        self.retries: int = 0
        self.decision: Optional[str] = None
        self.error: Optional[str] = None
        self.success: bool = True

    @property
    def latency_ms(self) -> int:
        return int((time.monotonic() - self.start_time) * 1000)

    def set_llm_stats(self, tokens_in: int, tokens_out: int, cost_usd: float):
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.cost_usd = cost_usd

    def set_cache_hit(self):
        self.cache_hit = True

    def set_retries(self, count: int):
        self.retries = count

    def set_decision(self, decision: str):
        self.decision = decision[:500] if decision else None  # Truncate for storage

    def set_error(self, error: str):
        self.error = error[:1000] if error else None
        self.success = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": str(self.job_id),
            "stage": self.stage,
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "prompt_version": self.prompt_version,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "cache_hit": self.cache_hit,
            "retries": self.retries,
            "decision": self.decision,
            "error": self.error,
            "success": self.success,
        }

