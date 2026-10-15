"""Rate-limited, concurrent marketplace queue consumer."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Protocol

from pydantic import TypeAdapter

from .models import BuyerUpdate, MarketplaceJob, OrderHandoff, QueueMessage, SellerAsset, WorkResult


class QueuePort(Protocol):
    def consume(self, max_messages: int, visibility_timeout: int) -> list[dict]:
        """Reserve a batch for processing."""

    def ack(self, message_id: str) -> None:
        """Confirm a completed message."""


class SharedRateLimiter:
    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.interval = 1 / requests_per_second
        self.clock = clock
        self.sleep = sleep
        self.next_slot = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = self.clock()
            delay = max(0.0, self.next_slot - now)
            if delay:
                self.sleep(delay)
                now = self.clock()
            self.next_slot = max(now, self.next_slot) + self.interval


class MarketplaceWorker:
    def __init__(
        self,
        queue: QueuePort,
        *,
        concurrency: int = 4,
        requests_per_second: float = 2,
        handle: Callable[[MarketplaceJob], str] | None = None,
        limiter: SharedRateLimiter | None = None,
    ) -> None:
        self.queue = queue
        self.concurrency = concurrency
        self.handle = handle or self._handle_storefront_job
        self.limiter = limiter or SharedRateLimiter(requests_per_second)

    @staticmethod
    def _handle_storefront_job(job: MarketplaceJob) -> str:
        if isinstance(job, SellerAsset):
            return "asset_recorded"
        if isinstance(job, BuyerUpdate):
            return "buyer_notified"
        if isinstance(job, OrderHandoff):
            return "order_handed_off"
        raise TypeError("unknown marketplace job")

    def _process(self, raw: dict) -> WorkResult:
        message = QueueMessage.model_validate(raw)
        self.limiter.wait()
        action = self.handle(message.payload)
        result = WorkResult(
            message_id=message.message_id,
            order_id=message.payload.order_id,
            action=action,
        )
        self.queue.ack(message.message_id)
        return result

    def run_batch(self) -> list[WorkResult]:
        messages = self.queue.consume(
            max_messages=self.concurrency,
            visibility_timeout=60,
        )
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            return list(pool.map(self._process, messages))
