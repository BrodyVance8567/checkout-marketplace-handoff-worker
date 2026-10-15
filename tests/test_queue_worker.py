from marketplace_worker.queue_worker import MarketplaceWorker, SharedRateLimiter


class FakeQueue:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = messages
        self.acked: list[str] = []

    def consume(self, max_messages: int, visibility_timeout: int) -> list[dict]:
        assert max_messages == 2
        assert visibility_timeout == 60
        return self.messages

    def ack(self, message_id: str) -> None:
        self.acked.append(message_id)


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_paid_buyer_update_is_notified_then_acknowledged_at_shared_rate() -> None:
    queue = FakeQueue(
        [
            {
                "message_id": "msg-101",
                "payload": {"kind": "buyer_update", "order_id": "ord-7", "status": "paid"},
            },
            {
                "message_id": "msg-102",
                "payload": {
                    "kind": "order_handoff",
                    "order_id": "ord-7",
                    "buyer_id": "buyer-3",
                    "asset_ids": ["asset-cover"],
                },
            },
        ]
    )
    fake_time = FakeTime()
    limiter = SharedRateLimiter(2, clock=fake_time.clock, sleep=fake_time.sleep)
    worker = MarketplaceWorker(queue, concurrency=2, limiter=limiter)

    results = worker.run_batch()

    assert [result.action for result in results] == ["buyer_notified", "order_handed_off"]
    assert sorted(queue.acked) == ["msg-101", "msg-102"]
    assert fake_time.sleeps == [0.5]


def test_failed_storefront_action_is_left_unacknowledged() -> None:
    queue = FakeQueue(
        [{"message_id": "msg-103", "payload": {"kind": "buyer_update", "order_id": "ord-8", "status": "paid"}}]
    )

    def fail_action(job: object) -> str:
        raise RuntimeError("storefront update rejected")

    worker = MarketplaceWorker(queue, concurrency=2, handle=fail_action)

    try:
        worker.run_batch()
    except RuntimeError:
        pass

    assert queue.acked == []
