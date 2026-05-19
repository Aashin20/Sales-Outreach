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


class Tracer:
    """
    Manages trace emission to both JSONL file and database.
    """

    def __init__(self, trace_file_path: str):
        self.trace_file_path = trace_file_path
        os.makedirs(os.path.dirname(trace_file_path), exist_ok=True)

    @asynccontextmanager
    async def trace_stage(
        self,
        job_id: UUID,
        stage: str,
        db: Optional[AsyncSession] = None,
        model: Optional[str] = None,
        prompt_version: Optional[str] = None,
    ):
        """
        Context manager that automatically records timing and errors for a stage.
        """
        entry = TraceEntry(
            job_id=job_id,
            stage=stage,
            model=model,
            prompt_version=prompt_version,
        )
        try:
            yield entry
        except Exception as e:
            entry.set_error(str(e))
            raise
        finally:
            # Write to JSONL file
            await self._write_jsonl(entry)
            # Write to database if session provided
            if db:
                await self._write_db(entry, db)

    async def _write_jsonl(self, entry: TraceEntry):
        """Append trace entry to JSONL file."""
        try:
            line = json.dumps(entry.to_dict()) + "\n"
            with open(self.trace_file_path, "a") as f:
                f.write(line)
        except Exception as e:
            logger.error("trace_write_failed", error=str(e), stage=entry.stage)

    async def _write_db(self, entry: TraceEntry, db: AsyncSession):
        """Write trace entry to database."""
        try:
            trace_log = TraceLog(
                job_id=entry.job_id,
                stage=entry.stage,
                timestamp=entry.timestamp,
                model=entry.model,
                prompt_version=entry.prompt_version,
                tokens_in=entry.tokens_in,
                tokens_out=entry.tokens_out,
                cost_usd=entry.cost_usd,
                latency_ms=entry.latency_ms,
                cache_hit=entry.cache_hit,
                retries=entry.retries,
                decision=entry.decision,
                error=entry.error,
                success=entry.success,
            )
            db.add(trace_log)
            await db.commit()
        except Exception as e:
            logger.error("trace_db_write_failed", error=str(e), stage=entry.stage)
