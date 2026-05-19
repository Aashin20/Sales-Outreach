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
