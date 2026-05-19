import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Optional
import httpx
import structlog
from tenacity import (retry,stop_after_attempt,
                      wait_exponential_jitter,retry_if_exception_type)
from ..models.schemas import WebhookPayload

logger = structlog.get_logger(__name__)


class WebhookDeliveryError(Exception):
    """Retryable webhook delivery error."""
    pass


class WebhookService:
    """Delivers signed webhook payloads to subscriber URLs."""

    def __init__(self, secret: str, timeout: int = 10, max_retries: int = 3):
        self.secret = secret
        self.timeout = timeout
        self.max_retries = max_retries

    def _sign_payload(self, payload_bytes: bytes) -> tuple[str, str]:
        """
        Sign a payload with HMAC-SHA256.
        Returns: (signature, timestamp)
        """
        timestamp = str(int(time.time()))
        # Sign: timestamp + "." + payload
        signing_input = f"{timestamp}.".encode() + payload_bytes
        signature = hmac.new(
            self.secret.encode(),
            signing_input,
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={signature}", timestamp

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=8, jitter=2),
        retry=retry_if_exception_type(WebhookDeliveryError),
        reraise=True,
    )
    async def _deliver(self, url: str, payload_bytes: bytes, signature: str, timestamp: str):
        """Deliver a webhook with retries."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
            try:
                response = await client.post(
                    url,
                    content=payload_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": signature,
                        "X-Webhook-Timestamp": timestamp,
                        "User-Agent": "OutreachAPI-Webhook/1.0",
                    },
                )

                if response.status_code >= 500:
                    raise WebhookDeliveryError(
                        f"Webhook endpoint returned {response.status_code}"
                    )

                if response.status_code >= 400:
                    logger.warning(
                        "webhook_client_error",
                        url=url,
                        status=response.status_code,
                    )
                    # Don't retry 4xx — it's a client problem
                    return False

                return True

            except httpx.TimeoutException:
                raise WebhookDeliveryError(f"Webhook timeout: {url}")
            except httpx.ConnectError:
                raise WebhookDeliveryError(f"Webhook connection error: {url}")

    async def deliver_webhook(
        self, url: str, payload: WebhookPayload
    ) -> bool:
        """
        Sign and deliver a webhook payload.
        Returns True if delivery succeeded, False otherwise.
        """
        try:
            payload_bytes = payload.model_dump_json(indent=None).encode()
            signature, timestamp = self._sign_payload(payload_bytes)

            result = await self._deliver(url, payload_bytes, signature, timestamp)

            logger.info(
                "webhook_delivered",
                url=url,
                job_id=str(payload.job_id),
                success=result,
            )
            return result

        except WebhookDeliveryError as e:
            logger.error(
                "webhook_delivery_failed",
                url=url,
                job_id=str(payload.job_id),
                error=str(e),
            )
            return False
        except Exception as e:
            logger.error(
                "webhook_unexpected_error",
                url=url,
                error=str(e),
            )
            return False
