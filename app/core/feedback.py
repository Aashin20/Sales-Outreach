import uuid
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.database import ApiKey, Feedback
from ..models.schemas import FeedbackRequest

logger = structlog.get_logger(__name__)


async def submit_outreach_feedback(
    job_id: uuid.UUID,
    body: FeedbackRequest,
    api_key: ApiKey,
    db: AsyncSession,
) -> Feedback:
    """
    Record user feedback on an outreach result.
    
    Args:
        job_id: The job ID being rated
        body: Feedback details (rating, comment, quality scores)
        api_key: The API key making the request
        db: Database session
        
    Returns:
        The created Feedback record
    """
    feedback = Feedback(
        job_id=job_id,
        api_key_id=api_key.id,
        rating=body.rating,
        comment=body.comment,
        hook_quality=body.hook_quality,
        message_quality=body.message_quality,
        evidence_accuracy=body.evidence_accuracy,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    logger.info(
        "feedback_recorded",
        feedback_id=str(feedback.id),
        job_id=str(job_id),
        rating=body.rating,
    )

    return feedback
