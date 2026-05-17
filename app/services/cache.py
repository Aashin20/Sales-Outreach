import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
import structlog
from redis.asyncio import Redis
