"""Run one marketplace queue batch."""

import json

from marketplace_worker.infrai_queue import InfraiQueue
from marketplace_worker.queue_worker import MarketplaceWorker


def main() -> None:
    worker = MarketplaceWorker(InfraiQueue(), concurrency=4, requests_per_second=2)
    for result in worker.run_batch():
        print(json.dumps(result.model_dump(), sort_keys=True))


if __name__ == "__main__":
    main()
