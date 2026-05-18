from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


# ── Request Schemas ──────────────────────────────────────────────────

class OutreachRequest(BaseModel):
    """POST /v1/outreach request body."""
    domain: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Company domain (e.g. 'firmable.com')",
        examples=["firmable.com"],
    )
    person_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Full name of the prospect",
        examples=["Jane Smith"],
    )
    webhook_url: Optional[str] = Field(
        None,
        max_length=2048,
        description="URL to receive webhook on completion",
        examples=["https://example.com/webhooks/outreach"],
    )

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Normalize and validate domain format."""
        v = v.strip().lower()
        # Strip protocol if included
        v = re.sub(r"^https?://", "", v)
        # Strip trailing slashes/paths
        v = v.split("/")[0]
        # Basic domain format check
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z]{2,})+$", v):
            raise ValueError(f"Invalid domain format: {v}")
        return v

    @field_validator("person_name")
    @classmethod
    def validate_person_name(cls, v: str) -> str:
        """Basic name plausibility check."""
        v = v.strip()
        # Must contain at least first + last name
        if len(v.split()) < 2:
            raise ValueError("Please provide a full name (first and last)")
        # No obviously invalid characters
        if re.search(r"[<>{}()\[\];]", v):
            raise ValueError("Name contains invalid characters")
        return v


class FeedbackRequest(BaseModel):
    """POST /v1/outreach/{job_id}/feedback request body."""
    rating: str = Field(
        ...,
        description="Thumbs up or down",
        examples=["thumbs_up"],
    )
    comment: Optional[str] = Field(
        None,
        max_length=2000,
        description="Free-text feedback",
    )
    hook_quality: Optional[int] = Field(
        None,
        ge=1, le=5,
        description="Hook quality 1-5",
    )
    message_quality: Optional[int] = Field(
        None,
        ge=1, le=5,
        description="Message quality 1-5",
    )
    evidence_accuracy: Optional[bool] = Field(
        None,
        description="Was the evidence accurate?",
    )

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: str) -> str:
        allowed = {"thumbs_up", "thumbs_down"}
        if v not in allowed:
            raise ValueError(f"Rating must be one of: {allowed}")
        return v

