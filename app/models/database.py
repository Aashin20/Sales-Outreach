import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, DateTime,
    JSON, Enum as SAEnum, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    FETCHING = "fetching"
    REASONING = "reasoning"
    COMPOSING = "composing"
    DELIVERING_WEBHOOK = "delivering_webhook"
    COMPLETED = "completed"
    FAILED = "failed"
