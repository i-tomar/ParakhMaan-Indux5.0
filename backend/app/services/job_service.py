"""
Background jobs with persisted status/progress.

The Job row is the source of truth (clients poll /api/v1/jobs/{id}); Redis/RQ is only the transport.
Without REDIS_URL, jobs run on a small in-process thread pool so local development needs no extra
services. JOB_MODE=eager runs them inline (tests).
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.all_models import Job

log = logging.getLogger(__name__)

ProgressFn = Callable[[float, Optional[str]], None]
Handler = Callable[[Session, Job, ProgressFn], Dict[str, Any]]

_HANDLERS: Dict[str, Handler] = {}
_executor: Optional[ThreadPoolExecutor] = None


def register(job_type: str) -> Callable[[Handler], Handler]:
    def decorator(fn: Handler) -> Handler:
        _HANDLERS[job_type] = fn
        return fn
    return decorator


def _load_handlers() -> None:
    # Handlers live next to the domain code; importing registers them.
    import app.services.defect_pipeline  # noqa: F401
    import app.services.learning.datasets  # noqa: F401
    import app.services.learning.training  # noqa: F401


def enqueue(
    db: Session,
    job_type: str,
    payload: Dict[str, Any],
    organization_id: Optional[str],
    created_by_id: Optional[str] = None,
    inspection_id: Optional[str] = None,
) -> Job:
    job = Job(
        job_type=job_type,
        payload=payload,
        organization_id=organization_id,
        created_by_id=created_by_id,
        inspection_id=inspection_id,
        status="QUEUED",
        progress=0.0,
        message="Queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _dispatch(job.id)
    db.refresh(job)
    return job


def _dispatch(job_id: str) -> None:
    mode = settings.JOB_MODE.lower()
    if mode == "eager":
        run_job(job_id)
    elif settings.REDIS_URL:
        from redis import Redis
        from rq import Queue

        queue = Queue(settings.JOB_QUEUE_NAME, connection=Redis.from_url(settings.REDIS_URL))
        queue.enqueue("app.workers.tasks.run_job", job_id, job_id=job_id, job_timeout=settings.JOB_TIMEOUT_SECONDS)
    else:
        global _executor
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")
        _executor.submit(run_job, job_id)


def run_job(job_id: str) -> None:
    _load_handlers()
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job or job.status in ("SUCCEEDED", "FAILED"):
            return
        job.status = "RUNNING"
        job.started_at = datetime.now(timezone.utc)
        job.message = "Running"
        db.commit()

        def progress(fraction: float, message: Optional[str] = None) -> None:
            job.progress = round(min(max(fraction, 0.0), 1.0), 3)
            if message:
                job.message = message[:500]
            db.commit()

        handler = _HANDLERS.get(job.job_type)
        if handler is None:
            raise ValueError(f"No handler registered for job type {job.job_type}")
        result = handler(db, job, progress)
        job.status = "SUCCEEDED"
        job.result = result
        job.progress = 1.0
        job.message = "Completed"
    except Exception as e:
        log.exception("Job %s failed", job_id)
        db.rollback()
        job = db.get(Job, job_id)
        if job:
            job.status = "FAILED"
            job.error = str(getattr(e, "detail", e))[:2000]
            job.message = "Failed"
    finally:
        if job:
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        db.close()
