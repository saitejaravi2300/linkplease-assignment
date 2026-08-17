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
        h = {"X-API-Key": self.api_key, "Accept": "application/json"}
        if extra:
            h.update(extra)
        return h

    async def send_dm(self, recipient_user_id: str, message: str, comment_id: str, idempotency_key: str) -> SendResult:
        try:
            r = await self.client.post(
                f"{self.base_url}/v1/dm/send",
                headers=self._headers({"Idempotency-Key": idempotency_key}),
                json={"recipient_user_id": recipient_user_id, "message": message, "comment_id": comment_id},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return SendResult("retry", error=f"network_error:{type(exc).__name__}")
        if r.status_code in (200, 202):
            data = r.json()
            if data.get("dm_id"):
                return SendResult("accepted", dm_id=data["dm_id"])
        return SendResult("permanent", error=f"invalid_success_response:{r.text[:300]}")
        if r.status_code == 429:
            value = r.headers.get("Retry-After", "5")
            try: retry_after = float(value)
            except ValueError: retry_after = 5.0
            return SendResult("retry", retry_after=retry_after, error="rate_limited")
        if r.status_code >= 500:
            return SendResult("retry", error=f"server_error:{r.status_code}")
        return SendResult("permanent", error=f"http_{r.status_code}:{r.text[:300]}")

    async def get_dm(self, dm_id: str) -> StatusResult:
        try:
            r = await self.client.get(f"{self.base_url}/v1/dm/{dm_id}", headers=self._headers())
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return StatusResult("retry", error=f"network_error:{type(exc).__name__}")
        if r.status_code == 200:
            data = r.json()
            return StatusResult("ok", status=data.get("status"))
        if r.status_code >= 500:
            return StatusResult("retry", error=f"server_error:{r.status_code}")
        return StatusResult("permanent", error=f"http_{r.status_code}:{r.text[:300]}")
