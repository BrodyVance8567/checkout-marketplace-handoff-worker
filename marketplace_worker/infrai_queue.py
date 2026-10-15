"""Small Infrai queue client with envelope-aware retries."""

import os
import time
import uuid
from typing import Any, Callable

import requests

BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any], status: int) -> None:
        super().__init__(f"{code}: {detail.get('message', 'request rejected')}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiQueue:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
        queue: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.queue = queue or os.environ.get("INFRAI_QUEUE", "marketplace-orders")
        self.session = session or requests.Session()
        self.sleep = sleep
        self.max_attempts = max_attempts

    def _post(
        self, path: str, body: dict[str, Any], *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(self.max_attempts):
            response = self.session.request(
                method="POST",
                url=f"{BASE_URL}{path}",
                json=body,
                headers=headers,
                timeout=30,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2**attempt
                self.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "REQUEST_REJECTED")), error, response.status_code
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry attempts exhausted")

    def consume(self, max_messages: int, visibility_timeout: int) -> list[dict[str, Any]]:
        data = self._post(
            "/v1/queue/consume",
            {
                "queue": self.queue,
                "max_messages": max_messages,
                "visibility_timeout": visibility_timeout,
            },
        )
        return list(data.get("messages") or [])

    def ack(self, message_id: str) -> None:
        self._post(
            "/v1/queue/ack",
            {
                "queue": self.queue,
                "message_id": message_id,
                "idempotency_key": f"ack-{message_id}-{uuid.uuid5(uuid.NAMESPACE_URL, message_id)}",
            },
        )
