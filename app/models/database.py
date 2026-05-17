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

class Job(Base):

    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = Column(String(64), unique=True, nullable=False, index=True)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False)


    domain = Column(String(255), nullable=False, index=True)
    person_name = Column(String(255), nullable=False)


    status = Column(SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True)
    error_message = Column(Text, nullable=True)

    company_homepage_content = Column(Text, nullable=True)
    news_content = Column(Text, nullable=True)
    profile_content = Column(Text, nullable=True)


    hook = Column(Text, nullable=True)
    hook_reasoning = Column(Text, nullable=True)
    evidence = Column(JSON, nullable=True)  
    confidence = Column(Float, nullable=True)

 
    subject = Column(Text, nullable=True)
    message_body = Column(Text, nullable=True)
    tone = Column(String(50), nullable=True)
    call_to_action = Column(Text, nullable=True)


    total_tokens_in = Column(Integer, default=0)
    total_tokens_out = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)


    pick_hook_prompt_version = Column(String(20), nullable=True)
    compose_message_prompt_version = Column(String(20), nullable=True)
    pick_hook_model = Column(String(100), nullable=True)
    compose_message_model = Column(String(100), nullable=True)

    webhook_url = Column(String(2048), nullable=True)
    webhook_delivered = Column(Boolean, default=False)


    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


    feedback_entries = relationship("Feedback", back_populates="job", lazy="selectin")

    __table_args__ = (
        Index("ix_jobs_domain_person", "domain", "person_name"),
        Index("ix_jobs_created_at", "created_at"),
    )


class Feedback(Base):

    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False)

    rating = Column(String(20), nullable=False) 
    comment = Column(Text, nullable=True)


    hook_quality = Column(Integer, nullable=True)  # 1-5
    message_quality = Column(Integer, nullable=True)  # 1-5
    evidence_accuracy = Column(Boolean, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


    job = relationship("Job", back_populates="feedback_entries")

