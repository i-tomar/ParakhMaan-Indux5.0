from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.database import get_db
from app.models.all_models import Job, User
from app.schemas.all_schemas import JobResponse

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(require("inspection:read"))):
    job = db.query(Job).filter(Job.id == job_id, Job.organization_id == user.organization_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=List[JobResponse])
def list_jobs(
    inspection_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require("inspection:read")),
):
    query = db.query(Job).filter(Job.organization_id == user.organization_id)
    if inspection_id:
        query = query.filter(Job.inspection_id == inspection_id)
    if status:
        query = query.filter(Job.status == status)
    return query.order_by(Job.created_at.desc()).limit(limit).all()
