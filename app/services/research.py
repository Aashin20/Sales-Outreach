import asyncio
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import Settings
from ..models.database import Job, JobStatus
from ..models.schemas import OutreachResult, WebhookPayload
from ..security.sanitizer import sanitize_fetched_content, validate_llm_output
from ..services.cache import CacheService
from ..services.cost import CostService
from ..services.fetcher import WebFetcher
from ..services.llm import LLMClient, CircuitBreakerOpen, HookResult
from ..services.webhook import WebhookService
from ..tracing.tracer import Tracer

logger = structlog.get_logger(__name__)


class PipelineError(Exception):
    """Fatal pipeline error — job should be marked failed."""
    pass


class ResearchPipeline:
    """
    Flow:
    1. Validate inputs
    2. Fetch signals 
    3. pick_hook LLM call 
    4. compose_message LLM call 
    5. Validate output
    6. Persist result
    7. Emit webhook
    8. Mark complete
    """

    def __init__(
        self,
        settings: Settings,
        db: AsyncSession,
        cache: CacheService,
        cost: CostService,
        fetcher: WebFetcher,
        llm: LLMClient,
        webhook: WebhookService,
        tracer: Tracer,
    ):
        self.settings = settings
        self.db = db
        self.cache = cache
        self.cost = cost
        self.fetcher = fetcher
        self.llm = llm
        self.webhook = webhook
        self.tracer = tracer

    async def _update_job_status(self, job: Job, status: JobStatus, error: Optional[str] = None):
        """Update job status in DB."""
        job.status = status
        if error:
            job.error_message = error
        if status == JobStatus.COMPLETED:
            job.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

    async def run(self, job_id: UUID):
        """
        Execute the full research pipeline for a job.
        """
        try:
            await asyncio.wait_for(
                self._run_pipeline(job_id),
                timeout=self.settings.job_overall_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error("pipeline_timeout", job_id=str(job_id))
            result = await self.db.execute(select(Job).where(Job.id == job_id))
            job = result.scalar_one_or_none()
            if job:
                await self._update_job_status(
                    job, JobStatus.FAILED,
                    error="Pipeline timed out after "
                          f"{self.settings.job_overall_timeout_seconds}s"
                )

    async def _run_pipeline(self, job_id: UUID):
        """The actual pipeline logic."""
        # Load the job
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            logger.error("job_not_found", job_id=str(job_id))
            return

        job.started_at = datetime.now(timezone.utc)

        try:
            # ── Stage 1: Validate ────────────────────────────────────
            async with self.tracer.trace_stage(job_id, "validate", self.db) as trace:
                await self._update_job_status(job, JobStatus.VALIDATING)
                # Domain was already validated by Pydantic on input
                # Person name was already validated
                trace.set_decision(f"Valid: {job.domain} / {job.person_name}")

            # ── Stage 2: Fetch Signals ───────────────────────────────
            await self._update_job_status(job, JobStatus.FETCHING)
            signals = await self._fetch_with_cache(job)

            # ── Stage 3: Pick Hook (LLM) ─────────────────────────────
            await self._update_job_status(job, JobStatus.REASONING)

            # Check cost budget before LLM calls
            budget = await self.cost.check_key_budget(
                job.api_key_id, self.settings.per_key_daily_cost_limit_usd
            )
            if budget["blocked"]:
                raise PipelineError("API key daily cost limit exceeded")

            # Check global budget
            global_budget = await self.cost.check_global_budget()
            if global_budget["degraded"]:
                logger.warning("global_budget_degraded", job_id=str(job_id))
                # Still process but log the degradation

            # Sanitize signals for LLM consumption
            sanitized_signals = {}
            for signal_name, content in signals.items():
                if content:
                    sanitized_signals[signal_name] = sanitize_fetched_content(
                        content, source=f"{job.domain}/{signal_name}"
                    )
                else:
                    sanitized_signals[signal_name] = None

            async with self.tracer.trace_stage(
                job_id, "pick_hook", self.db,
                model=self.settings.groq_model_pick_hook,
                prompt_version="v1",
            ) as trace:
                hook_result, hook_stats = await self.llm.pick_hook(
                    company_signals=sanitized_signals,
                    person_name=job.person_name,
                    domain=job.domain,
                )
                trace.set_llm_stats(
                    hook_stats["tokens_in"],
                    hook_stats["tokens_out"],
                    hook_stats["cost_usd"],
                )
                trace.set_retries(hook_stats.get("retries", 0))
                trace.set_decision(f"Hook: {hook_result.hook[:100]}")

            # Record cost
            await self.cost.record_cost(job.api_key_id, hook_stats["cost_usd"])

            # Update job with hook results
            job.hook = hook_result.hook
            job.hook_reasoning = hook_result.reasoning
            job.evidence = hook_result.evidence
            job.confidence = hook_result.confidence
            job.pick_hook_prompt_version = "v1"
            job.pick_hook_model = hook_stats["model"]
            job.total_tokens_in += hook_stats["tokens_in"]
            job.total_tokens_out += hook_stats["tokens_out"]
            job.total_cost_usd += hook_stats["cost_usd"]
            await self.db.commit()

            # ── Stage 4: Compose Message (LLM) ──────────────────────
            await self._update_job_status(job, JobStatus.COMPOSING)

            async with self.tracer.trace_stage(
                job_id, "compose_message", self.db,
                model=self.settings.groq_model_compose_message,
                prompt_version="v1",
            ) as trace:
                message_result, msg_stats = await self.llm.compose_message(
                    hook_result=hook_result,
                    person_name=job.person_name,
                    domain=job.domain,
                )
                trace.set_llm_stats(
                    msg_stats["tokens_in"],
                    msg_stats["tokens_out"],
                    msg_stats["cost_usd"],
                )
                trace.set_retries(msg_stats.get("retries", 0))
                trace.set_decision(f"Subject: {message_result.subject[:100]}")

            # Record cost
            await self.cost.record_cost(job.api_key_id, msg_stats["cost_usd"])

            # ── Stage 5: Validate Output ─────────────────────────────
            async with self.tracer.trace_stage(job_id, "validate_output", self.db) as trace:
                violations = validate_llm_output(
                    output_text=f"{message_result.subject} {message_result.body}",
                    allowed_names=[job.person_name],
                    evidence_list=hook_result.evidence,
                )
                if violations:
                    trace.set_decision(f"Violations: {violations}")
                    logger.warning(
                        "output_validation_issues",
                        job_id=str(job_id),
                        violations=violations,
                    )
                    # Don't fail the job — log and continue
                else:
                    trace.set_decision("Output validated clean")

            # Update job with message results
            job.subject = message_result.subject
            job.message_body = message_result.body
            job.tone = message_result.tone
            job.call_to_action = message_result.call_to_action
            job.compose_message_prompt_version = "v1"
            job.compose_message_model = msg_stats["model"]
            job.total_tokens_in += msg_stats["tokens_in"]
            job.total_tokens_out += msg_stats["tokens_out"]
            job.total_cost_usd += msg_stats["cost_usd"]
            await self.db.commit()

            # ── Stage 6: Deliver Webhook ─────────────────────────────
            if job.webhook_url:
                await self._update_job_status(job, JobStatus.DELIVERING_WEBHOOK)
                async with self.tracer.trace_stage(job_id, "webhook", self.db) as trace:
                    outreach_result = OutreachResult(
                        hook=hook_result.hook,
                        hook_reasoning=hook_result.reasoning,
                        evidence=hook_result.evidence,
                        confidence=hook_result.confidence,
                        subject=message_result.subject,
                        message_body=message_result.body,
                        tone=message_result.tone,
                        call_to_action=message_result.call_to_action,
                    )
                    payload = WebhookPayload(
                        event="outreach.completed",
                        job_id=job_id,
                        status="completed",
                        timestamp=datetime.now(timezone.utc),
                        result=outreach_result,
                    )
                    delivered = await self.webhook.deliver_webhook(
                        job.webhook_url, payload
                    )
                    job.webhook_delivered = delivered
                    trace.set_decision(f"Delivered: {delivered}")

            # ── Stage 7: Mark Complete ───────────────────────────────
            await self._update_job_status(job, JobStatus.COMPLETED)
            logger.info(
                "pipeline_completed",
                job_id=str(job_id),
                total_cost=job.total_cost_usd,
                confidence=job.confidence,
            )

        except CircuitBreakerOpen as e:
            logger.error("pipeline_circuit_breaker", job_id=str(job_id), error=str(e))
            await self._update_job_status(
                job, JobStatus.FAILED, error="LLM provider unavailable (circuit breaker open)"
            )
        except PipelineError as e:
            logger.error("pipeline_error", job_id=str(job_id), error=str(e))
            await self._update_job_status(job, JobStatus.FAILED, error=str(e))
        except Exception as e:
            logger.exception("pipeline_unexpected_error", job_id=str(job_id))
            await self._update_job_status(
                job, JobStatus.FAILED, error=f"Unexpected error: {str(e)[:500]}"
            )

    async def _fetch_with_cache(self, job: Job) -> dict[str, Optional[str]]:
        """
        Fetch signals with partial-result caching.
        """
        domain = job.domain
        person_name = job.person_name
        job_id = job.id

        async def fetch_or_cache(signal_type: str, fetch_coro):
            """Try cache first, then fetch, then cache the result."""
            async with self.tracer.trace_stage(
                job_id, f"fetch_{signal_type}", self.db
            ) as trace:
                # Check partial cache
                cached = await self.cache.get_cached_signal(domain, signal_type)
                if cached:
                    trace.set_cache_hit()
                    trace.set_decision(f"Cache hit ({len(cached)} chars)")
                    return cached

                # Fetch fresh
                try:
                    content = await asyncio.wait_for(
                        fetch_coro,
                        timeout=self.settings.fetch_timeout_seconds,
                    )
                    if content:
                        await self.cache.set_cached_signal(domain, signal_type, content)
                        trace.set_decision(f"Fetched ({len(content)} chars)")
                    else:
                        trace.set_decision("No content returned")
                    return content
                except asyncio.TimeoutError:
                    trace.set_error(f"Timeout after {self.settings.fetch_timeout_seconds}s")
                    return None
                except Exception as e:
                    trace.set_error(str(e))
                    return None

        # Run all fetches concurrently — they are independent
        homepage, news, profile = await asyncio.gather(
            fetch_or_cache("homepage", self.fetcher.fetch_homepage(domain)),
            fetch_or_cache("news", self.fetcher.fetch_news(domain)),
            fetch_or_cache("profile", self.fetcher.fetch_profile(person_name, domain)),
        )

        # Store raw signals on job for reference
        job.company_homepage_content = homepage[:5000] if homepage else None
        job.news_content = news[:5000] if news else None
        job.profile_content = profile[:2000] if profile else None
        await self.db.commit()

        return {
            "homepage": homepage,
            "news": news,
            "profile": profile,
        }
