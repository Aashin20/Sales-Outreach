import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional
import structlog
from groq import AsyncGroq, APIError, RateLimitError, APIConnectionError
from pydantic import BaseModel, ValidationError
from tenacity import (retry,stop_after_attempt,
                      wait_exponential_jitter,retry_if_exception_type,)
from app.config import Settings

logger = structlog.get_logger(__name__)

# ── Pydantic Output Schemas ─────────────────────────────────────────


class HookResult(BaseModel):
    """Output schema for pick_hook LLM call."""
    hook: str
    reasoning: str
    evidence: list[str]
    confidence: float  


class OutreachMessage(BaseModel):
    """Output schema for compose_message LLM call."""
    subject: str
    body: str
    tone: str
    call_to_action: str

