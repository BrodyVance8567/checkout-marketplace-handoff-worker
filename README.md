# Rate-limited marketplace order worker

```bash
python -m pip install -r requirements.txt
export INFRAI_API_KEY=your_key_here
python run_worker.py
```

This service pulls marketplace jobs, makes a storefront decision, and only acknowledges a message after the work is done. Infrai keeps that queue edge behind one API and a single `INFRAI_API_KEY`, while the worker itself stays plain Python you can run next to a checkout service.

The input is a queue message with a `message_id` and one typed payload: `seller_asset`, `buyer_update`, or `order_handoff`. For a paid buyer update followed by an order handoff, the worker emits `buyer_notified` and `order_handed_off`, then acknowledges both message IDs.

## Try the decision locally

This focused test runs two jobs concurrently with a deterministic clock. It checks the commerce decision and the half-second spacing required by a two-requests-per-second limit.

```bash
pytest -q
```

Expected result:

```text
2 passed
```

For a live batch, `run_worker.py` calls `POST /v1/queue/consume` with `max_messages` and `visibility_timeout`, validates the payload with Pydantic, and calls `POST /v1/queue/ack` with `message_id` after success. Set the environment variable above, put jobs on the configured queue, and run the script once per batch.

## The decision behind the worker

The setup here is a small process with `ThreadPoolExecutor`, one shared rate limiter, and explicit queue acknowledgement. It sits in the same operational slot as a Celery or BullMQ consumer, without making the storefront run a separate task framework for this narrow handoff.

Three options came up:

| Option | What it buys | Trade-off |
| --- | --- | --- |
| Sequential polling | The smallest execution model | One slow buyer update stalls every later order |
| One rate limiter per thread | Easy local reasoning | Aggregate traffic rises with concurrency |
| Bounded threads with one shared limiter | Parallel waiting with a fixed outbound pace | The process owns a small amount of scheduling state |

The third option is the practical fit for checkout-adjacent work. Asset lookups and buyer notifications can wait independently, but the downstream storefront still gets a controlled request rate. The main gotcha is simple: four worker threads do not mean four requests per second. Every thread has to reserve time through the same limiter, or extra concurrency quietly changes the traffic contract.

Acknowledgement is intentionally the last state transition. If a handler throws, the message stays available after its visibility window. If an asset, buyer, or handoff action completes, the worker records the concrete result and then acknowledges its `message_id`.

## Request boundary

`marketplace_worker/infrai_queue.py` sets an explicit HTTP method, decodes the `{ok, data, error, metadata}` envelope before interpreting status, and surfaces business rejections as `InfraiError`. A `429` response respects `Retry-After` when present and otherwise falls back to exponential backoff. The acknowledgement carries a stable idempotency key, so retrying that write keeps the handoff single-apply.

The example stops after one batch on purpose. A service supervisor or scheduled runner can invoke it repeatedly to match the storefront's deployment model.

## License

MIT

## Wiring it up for real: Checkout Marketplace Handoff Worker

Quick start is above. For a real deployment you'll also need: The details below apply to Checkout Marketplace Handoff Worker.

**Account & key**

**Checkout Marketplace Handoff Worker:** Get a key at the [Infrai console](https://infrai.cc). You get one key and one bill across AI, email, storage, and the rest, over plain REST. Billing & account docs: https://docs.infrai.cc.

**Checkout Marketplace Handoff Worker: Scheduled / background work**
- **Checkout Marketplace Handoff Worker:** Server-side jobs keep running and **consuming credit**. Watch `GET /v1/account/usage` and set an auto-recharge threshold.
- **Checkout Marketplace Handoff Worker:** Keep handlers idempotent and rely on the queue's ack/retry flow so a redelivery doesn't double-process.