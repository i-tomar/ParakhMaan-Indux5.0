from app.services import job_service


def run_job(job_id: str) -> None:
    """RQ entry point; the job's handler, status and progress are resolved from the database."""
    job_service.run_job(job_id)
