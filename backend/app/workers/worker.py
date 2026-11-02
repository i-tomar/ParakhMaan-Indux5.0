"""
Background worker:  python -m app.workers.worker

Consumes the Redis queue (REDIS_URL) that the API enqueues video-analysis and future training jobs on.
Run several workers (or containers) to scale processing independently of the API.
"""
import logging
import os

from redis import Redis
from rq import Queue, SimpleWorker, Worker
from rq.timeouts import TimerDeathPenalty

from app.core.config import settings
from app.services.job_service import _load_handlers


class _WindowsWorker(SimpleWorker):
    # Windows has no fork() or SIGALRM: run jobs in-process with a timer-based timeout.
    death_penalty_class = TimerDeathPenalty


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not settings.REDIS_URL:
        raise SystemExit("REDIS_URL is not set; without Redis the API runs jobs in-process.")
    _load_handlers()
    connection = Redis.from_url(settings.REDIS_URL)
    worker_cls = _WindowsWorker if os.name == "nt" else Worker
    worker = worker_cls([Queue(settings.JOB_QUEUE_NAME, connection=connection)], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
