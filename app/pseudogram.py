from __future__ import annotations

import httpx
from dataclasses import dataclass
from typing import Optional


@dataclass
class SendResult:
    kind: str
    dm_id: Optional[str] = None
    retry_after: Optional[float] = None
    error: Optional[str] = None


@dataclass
class StatusResult:
    kind: str
    status: Optional[str] = None
    error: Optional[str] = None


class PseudoGramClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        await self.client.aclose()

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }

        if extra:
            headers.update(extra)

        return headers

    async def send_dm(
        self,
        recipient_user_id: str,
        message: str,
        comment_id: str,
        idempotency_key: str,
    ) -> SendResult:
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/dm/send",
                headers=self._headers(
                    {
                        "Idempotency-Key": idempotency_key,
                    }
                ),
                json={
                    "recipient_user_id": recipient_user_id,
                    "message": message,
                    "comment_id": comment_id,
                },
            )

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return SendResult(
                "retry",
                error=f"network_error:{type(exc).__name__}",
            )

        # Successful request: provider accepted the DM.
        if response.status_code in (200, 202):
            try:
                data = response.json()
            except ValueError:
                return SendResult(
                    "permanent",
                    error=f"invalid_success_response:{response.text[:300]}",
                )

            if data.get("dm_id"):
                return SendResult(
                    "accepted",
                    dm_id=data["dm_id"],
                )

            return SendResult(
                "permanent",
                error=f"invalid_success_response:{response.text[:300]}",
            )

        # Provider rate limit: retry using Retry-After.
        if response.status_code == 429:
            value = response.headers.get("Retry-After", "5")

            try:
                retry_after = float(value)
            except ValueError:
                retry_after = 5.0

            return SendResult(
                "retry",
                retry_after=retry_after,
                error="rate_limited",
            )

        # Provider/server failure: retry.
        if response.status_code >= 500:
            return SendResult(
                "retry",
                error=f"server_error:{response.status_code}",
            )

        # Other 4xx responses are treated as permanent failures.
        return SendResult(
            "permanent",
            error=f"http_{response.status_code}:{response.text[:300]}",
        )

    async def get_dm(self, dm_id: str) -> StatusResult:
        try:
            response = await self.client.get(
                f"{self.base_url}/v1/dm/{dm_id}",
                headers=self._headers(),
            )

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return StatusResult(
                "retry",
                error=f"network_error:{type(exc).__name__}",
            )

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                return StatusResult(
                    "permanent",
                    error=f"invalid_response:{response.text[:300]}",
                )

            return StatusResult(
                "ok",
                status=data.get("status"),
            )

        if response.status_code >= 500:
            return StatusResult(
                "retry",
                error=f"server_error:{response.status_code}",
            )

        return StatusResult(
            "permanent",
            error=f"http_{response.status_code}:{response.text[:300]}",
        )