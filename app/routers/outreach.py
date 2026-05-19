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

