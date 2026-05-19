import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional
import structlog
from groq import AsyncGroq, APIError, RateLimitError, APIConnectionError
from pydantic import BaseModel, ValidationError
from tenacity import (retry,stop_after_attempt,
                      wait_exponential_jitter,retry_if_exception_type,)
from app.config import Settings

logger = structlog.get_logger(__name__)

# ── Pydantic Output Schemas ─────────────────────────────────────────


class HookResult(BaseModel):
    """Output schema for pick_hook LLM call."""
    hook: str
    reasoning: str
    evidence: list[str]
    confidence: float  


class OutreachMessage(BaseModel):
    """Output schema for compose_message LLM call."""
    subject: str
    body: str
    tone: str
    call_to_action: str


# ── Circuit Breaker ──────────────────────────────────────────────────


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    States: CLOSED (normal) → OPEN (blocking) → HALF_OPEN (testing)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
        window_seconds: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.window_seconds = window_seconds
        self.failures: list[float] = []
        self.state = "CLOSED"
        self.opened_at: Optional[float] = None

    def _clean_old_failures(self):
        now = time.monotonic()
        self.failures = [
            t for t in self.failures
            if now - t < self.window_seconds
        ]

    def record_failure(self):
        self.failures.append(time.monotonic())
        self._clean_old_failures()
        if len(self.failures) >= self.failure_threshold:
            self.state = "OPEN"
            self.opened_at = time.monotonic()
            logger.critical(
                "circuit_breaker_opened",
                failures=len(self.failures),
                threshold=self.failure_threshold,
            )

    def record_success(self):
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self.failures.clear()
            logger.info("circuit_breaker_closed")

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if self.opened_at and (time.monotonic() - self.opened_at) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info("circuit_breaker_half_open")
                return True
            return False
        # HALF_OPEN — allow one request through
        return True


# ── Retryable LLM Errors ────────────────────────────────────────────


class RetryableLLMError(Exception):
    """LLM error that should be retried."""
    pass


class NonRetryableLLMError(Exception):
    """LLM error that should NOT be retried."""
    pass


class SchemaViolationError(Exception):
    """LLM output didn't match expected schema."""
    pass


# ── LLM Client ──────────────────────────────────────────────────────


class LLMClient:

    # Groq pricing (approximate, per 1M tokens)
    PRICING = {
        "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
        "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
        "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
        "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
        "gemma2-9b-it": {"input": 0.20, "output": 0.20},
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=settings.cb_failure_threshold,
            recovery_timeout=settings.cb_recovery_timeout_seconds,
            window_seconds=settings.cb_expected_exception_window_seconds,
        )
        self._prompts_cache: dict[str, str] = {}

    def _load_prompt(self, prompt_name: str, version: str) -> str:
        """Load a prompt from file with caching."""
        cache_key = f"{prompt_name}.{version}"
        if cache_key not in self._prompts_cache:
            # Look in prompts/ directory
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            prompt_path = os.path.join(base_dir, "prompts", f"{prompt_name}.{version}.md")
            try:
                with open(prompt_path, "r") as f:
                    self._prompts_cache[cache_key] = f.read()
            except FileNotFoundError:
                raise NonRetryableLLMError(f"Prompt file not found: {prompt_path}")
        return self._prompts_cache[cache_key]

    def _estimate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost in USD for a completion."""
        pricing = self.PRICING.get(model, {"input": 1.0, "output": 1.0})
        cost = (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000
        return cost

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=15, jitter=3),
        retry=retry_if_exception_type(RetryableLLMError),
        reraise=True,
    )
    async def _call_llm(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """
        Raw LLM call with circuit breaker and retries.
        Returns: {content, tokens_in, tokens_out, cost_usd, model}
        """
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpen("LLM circuit breaker is OPEN — provider may be down")

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
                max_tokens=2000,
            )

            self.circuit_breaker.record_success()

            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0
            cost = self._estimate_cost(model, tokens_in, tokens_out)

            return {
                "content": response.choices[0].message.content,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost,
                "model": model,
            }

        except RateLimitError as e:
            self.circuit_breaker.record_failure()
            raise RetryableLLMError(f"Rate limited: {e}")
        except APIConnectionError as e:
            self.circuit_breaker.record_failure()
            raise RetryableLLMError(f"Connection error: {e}")
        except APIError as e:
            if e.status_code and e.status_code >= 500:
                self.circuit_breaker.record_failure()
                raise RetryableLLMError(f"Server error: {e}")
            raise NonRetryableLLMError(f"API error: {e}")

    async def _call_with_schema_validation(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema_class: type[BaseModel],
        max_schema_retries: int = 2,
        temperature: float = 0.3,
    ) -> tuple[BaseModel, dict]:
        """
        Call LLM and validate output against Pydantic schema.
        Retries on schema violation with error feedback.
        Returns: (validated_object, raw_llm_stats)
        """
        total_stats = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "retries": 0}
        last_error = None

        for attempt in range(max_schema_retries + 1):
            prompt = user_prompt
            if last_error and attempt > 0:
                prompt += (
                    f"\n\n[SCHEMA VALIDATION ERROR on previous attempt: {last_error}. "
                    f"Please fix your output to match the required JSON schema exactly.]"
                )
                total_stats["retries"] += 1

            result = await self._call_llm(model, system_prompt, prompt, temperature)
            total_stats["tokens_in"] += result["tokens_in"]
            total_stats["tokens_out"] += result["tokens_out"]
            total_stats["cost_usd"] += result["cost_usd"]

            try:
                content = result["content"]
                parsed = json.loads(content)
                validated = schema_class.model_validate(parsed)
                return validated, total_stats
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = str(e)
                logger.warning(
                    "schema_validation_failed",
                    attempt=attempt + 1,
                    error=last_error,
                    schema=schema_class.__name__,
                )

        raise SchemaViolationError(
            f"Failed to get valid {schema_class.__name__} after {max_schema_retries + 1} attempts: {last_error}"
        )

    # ── Named Tool Calls ─────────────────────────────────────────────

    async def pick_hook(
        self,
        company_signals: dict[str, Optional[str]],
        person_name: str,
        domain: str,
    ) -> tuple[HookResult, dict]:
        """
        Named tool: pick_hook (v1)
        Analyzes fetched signals to pick the best outreach hook.
        """
        prompt_version = "v1"
        model = self.settings.groq_model_pick_hook
        system_prompt = self._load_prompt("pick_hook", prompt_version)

        user_content_parts = [
            f"Target person: {person_name}",
            f"Company domain: {domain}",
        ]
        for signal_name, content in company_signals.items():
            if content:
                user_content_parts.append(f"\n--- {signal_name.upper()} ---\n{content}")
            else:
                user_content_parts.append(f"\n--- {signal_name.upper()} ---\n[Not available]")

        user_prompt = "\n".join(user_content_parts)

        result, stats = await self._call_with_schema_validation(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_class=HookResult,
            temperature=0.3,
        )

        stats["model"] = model
        stats["prompt_version"] = prompt_version
        return result, stats

    async def compose_message(
        self,
        hook_result: HookResult,
        person_name: str,
        domain: str,
    ) -> tuple[OutreachMessage, dict]:
        """
        Named tool: compose_message (v1)
        Composes a personalized outreach message using the selected hook.
        """
        prompt_version = "v1"
        model = self.settings.groq_model_compose_message
        system_prompt = self._load_prompt("compose_message", prompt_version)

        user_prompt = (
            f"Target person: {person_name}\n"
            f"Company domain: {domain}\n"
            f"Selected hook: {hook_result.hook}\n"
            f"Hook reasoning: {hook_result.reasoning}\n"
            f"Evidence: {json.dumps(hook_result.evidence)}\n"
            f"Confidence: {hook_result.confidence}\n"
        )

        result, stats = await self._call_with_schema_validation(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_class=OutreachMessage,
            temperature=0.5, 
        )

        stats["model"] = model
        stats["prompt_version"] = prompt_version
        return result, stats
