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
