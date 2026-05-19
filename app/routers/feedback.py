import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.feedback import submit_outreach_feedback
from ..dependencies import get_authenticated_key, get_db
from ..models import FeedbackRequest, FeedbackResponse
from ..models.database import ApiKey, Job, JobStatus


router = APIRouter(prefix="/v1/feedback", tags=["Feedback"])


@router.post(
    "/{job_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit feedback on an outreach result",
    description=(
        "Submit thumbs up/down and optional free-text feedback on a completed outreach result. "
        "This data feeds the eval set for prompt improvement."
    ),
    responses={
        201: {"description": "Feedback recorded"},
        400: {"description": "Invalid feedback or job not completed"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Job not found"},
    },
)
async def submit_feedback(
    job_id: uuid.UUID,
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_authenticated_key),
):
    """Submit feedback on a completed outreach result."""

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit feedback for job in status '{job.status.value}'. "
                   f"Job must be completed.",
        )

    feedback = await submit_outreach_feedback(job_id, body, api_key, db)

    return FeedbackResponse(
        feedback_id=feedback.id,
        job_id=job_id,
        message="Feedback recorded — thank you!",
    )