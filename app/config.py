from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):

    # LLM
    groq_api_key: str = Field(..., description="Groq API key")
    groq_model_pick_hook: str = Field(..., description="Model for hook selection")
    groq_model_compose_message: str = Field(..., description="Model for message composition")
    groq_timeout_seconds: int = Field(..., description="Timeout per LLM call")
    groq_max_retries: int = Field(..., description="Max retries per LLM call")

    # DB
    database_url: str = Field(..., description="Database connection URL")

    # Redis
    redis_url: str = Field(..., description="Redis connection URL")

    # Server
    api_host: str = Field(..., description="API server host")
    api_port: int = Field(..., description="API server port")
    api_workers: int = Field(..., description="Number of API workers")
    debug: bool = Field(..., description="Debug mode flag")

    # Cost
    per_key_daily_cost_limit_usd: float = Field(..., description="Per-key daily cost limit in USD")
    global_daily_cost_limit_usd: float = Field(..., description="Global daily cost limit in USD")
    cost_warning_threshold: float = Field(..., description="Fraction of budget that triggers warning header")

    # Caching
    idempotency_ttl_seconds: int = Field(..., description="Idempotency cache TTL (7 days)")
    homepage_cache_ttl_seconds: int = Field(..., description="Homepage cache TTL (24 hours)")
    news_cache_ttl_seconds: int = Field(..., description="News cache TTL (6 hours)")
    profile_cache_ttl_seconds: int = Field(..., description="Profile cache TTL (48 hours)")

    # Breaker
    cb_failure_threshold: int = Field(..., description="Failures before circuit opens")
    cb_recovery_timeout_seconds: int = Field(..., description="Seconds before half-open")
    cb_expected_exception_window_seconds: int = Field(..., description="Window for counting failures")

    # Webhook
    webhook_secret: str = Field(..., description="HMAC signing secret")
    webhook_max_retries: int = Field(..., description="Max webhook retries")
    webhook_timeout_seconds: int = Field(..., description="Webhook timeout in seconds")

    # Timeouts
    job_overall_timeout_seconds: int = Field(..., description="Job overall timeout in seconds")
    fetch_timeout_seconds: int = Field(..., description="Fetch timeout in seconds")
    llm_call_timeout_seconds: int = Field(..., description="LLM call timeout in seconds")

    # Tracing
    trace_file_path: str = Field(..., description="Path to traces file")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
