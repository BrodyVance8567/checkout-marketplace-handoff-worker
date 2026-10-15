from marketplace_worker.infrai_queue import InfraiQueue


class FakeResponse:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, data: dict) -> None:
        self.data = data

    def json(self) -> dict:
        return {"ok": True, "data": self.data}


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requests: list[dict] = []

    def request(self, **kwargs: object) -> FakeResponse:
        self.requests.append(kwargs)
        return self.responses.pop(0)


def test_consume_includes_queue_in_body() -> None:
    session = FakeSession([FakeResponse({"messages": []})])
    queue = InfraiQueue(api_key="test", queue="marketplace-orders", session=session)

    queue.consume(max_messages=4, visibility_timeout=60)

    assert session.requests[0]["json"] == {
        "queue": "marketplace-orders",
        "max_messages": 4,
        "visibility_timeout": 60,
    }


def test_ack_includes_queue_and_idempotency_key_in_body() -> None:
    session = FakeSession([FakeResponse({})])
    queue = InfraiQueue(api_key="test", queue="marketplace-orders", session=session)

    queue.ack("msg-101")

    body = session.requests[0]["json"]
    assert body["queue"] == "marketplace-orders"
    assert body["message_id"] == "msg-101"
    assert body["idempotency_key"].startswith("ack-msg-101-")
    assert "Idempotency-Key" not in session.requests[0]["headers"]
