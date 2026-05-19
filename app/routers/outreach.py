import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from ..core.outreach import create_outreach_job, get_outreach_job_with_result
from ..dependencies import check_cost_budget, get_db, get_redis
from ..models import ErrorResponse, JobStatusResponse, OutreachJobCreated, OutreachRequest
from ..models.database import ApiKey, Job
from ..services.cost import CostService


router = APIRouter(prefix="/v1/outreach", tags=["Outreach"])


@router.post(
    "",
    response_model=OutreachJobCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a prospect for outreach research",
    description=(
        "Submits a prospect (domain + person name) for async research. "
        "Returns a job ID immediately (<500ms). Poll GET /v1/outreach/{job_id} for results, "
        "or provide a webhook_url to be notified on completion."
    ),
    responses={
        200: {"description": "Cached result returned (idempotency hit)", "model": OutreachJobCreated},
        202: {"description": "Job created and queued for processing", "model": OutreachJobCreated},
        400: {"description": "Invalid input", "model": ErrorResponse},
        401: {"description": "Missing or invalid API key", "model": ErrorResponse},
        429: {"description": "Rate limit or cost limit exceeded", "model": ErrorResponse},
    },
)
async def create_outreach(
    request: Request,
    body: OutreachRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    api_key: ApiKey = Depends(check_cost_budget),
):
    """
    Submit a prospect for outreach research.
    """
    cost_service = CostService(redis, get_settings())

    arq_redis = request.app.state.arq_redis
    job, idemp_key, is_cached = await create_outreach_job(
        body, api_key, db, redis, arq_redis
    )

    cost_headers = await cost_service.get_cost_headers(
        api_key.id, api_key.daily_cost_limit_usd
    )

    response_data = OutreachJobCreated(
        job_id=job.id,
        status=job.status.value,
        idempotency_key=idemp_key,
        message="Returning cached result (idempotency hit)" if is_cached else "Job submitted for processing",
        poll_url=f"/v1/outreach/{job.id}",
    )

    status_code = status.HTTP_200_OK if is_cached else status.HTTP_202_ACCEPTED
    return JSONResponse(
        status_code=status_code,
        content=response_data.model_dump(mode="json"),
        headers=cost_headers,
    )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status and result",
    description="Fetch the current status of an outreach job. Returns the full result when completed.",
    responses={
        200: {"description": "Job status (and result if completed)"},
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Job not found"},
    },
)
async def get_outreach_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(check_cost_budget),
):
    """Get the status and result of an outreach job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    outreach_result = await get_outreach_job_with_result(job)

    return JobStatusResponse(
        job_id=job.id,
        status=job.status.value,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        result=outreach_result,
        total_tokens_in=job.total_tokens_in,
        total_tokens_out=job.total_tokens_out,
        total_cost_usd=job.total_cost_usd,
        pick_hook_prompt_version=job.pick_hook_prompt_version,
        compose_message_prompt_version=job.compose_message_prompt_version,
        pick_hook_model=job.pick_hook_model,
        compose_message_model=job.compose_message_model,
    )