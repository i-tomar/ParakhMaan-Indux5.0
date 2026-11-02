from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_org_inspection, require
from app.core.config import settings
from app.core.database import get_db
from app.models.all_models import DefectDetection, Image, Inspection, ReviewerAction, ReviewTask, User
from app.schemas.all_schemas import DefectDetectionResponse
from app.services import defect_pipeline as pipeline
from app.services import job_service
from app.services.defect_detection_service import DEFECT_TYPES, grade_severity
from app.services.learning import datasets
from app.services.learning.registry import learning_classes
from app.services.storage_service import storage_service

router = APIRouter(prefix="/review", tags=["Review Queue (learning loop)"])


class AnnotationCreate(BaseModel):
    defect_type: str = Field(..., min_length=2, max_length=50)
    bbox: List[float] = Field(..., min_length=4, max_length=4)
    note: Optional[str] = Field(None, max_length=500)


class CompleteReview(BaseModel):
    accept_pending: bool = True  # unreviewed model detections on the image are confirmed as correct
    note: Optional[str] = Field(None, max_length=500)


class RequestReview(BaseModel):
    reason: Optional[str] = Field(None, max_length=300)


def _org_image(db: Session, image_id: str, user: User) -> tuple[Image, Inspection]:
    row = (db.query(Image, Inspection).join(Inspection, Inspection.id == Image.inspection_id)
           .filter(Image.id == image_id, Inspection.organization_id == user.organization_id).first())
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")
    return row


def _task_summary(task: ReviewTask) -> dict:
    image, insp = task.image, task.inspection
    detections = [d for d in insp.defect_detections if d.image_id == image.id]
    return {
        "id": task.id, "status": task.status, "priority": task.priority, "reasons": task.reasons or [],
        "source": task.source, "created_at": task.created_at, "completed_at": task.completed_at,
        "image_id": image.id, "image_url": storage_service.signed_url(image.file_path),
        "image_review_status": image.review_status, "inspection_id": insp.id,
        "inspection_number": insp.inspection_number, "product_name": insp.product_name,
        "station": insp.location, "batch_code": insp.batch_code,
        "detection_count": sum(1 for d in detections if d.reviewer_status != "REJECTED"),
        "pending_count": sum(1 for d in detections if d.reviewer_status == "PENDING"),
    }


@router.get("/queue")
def get_queue(status: str = "OPEN", reason: Optional[str] = None, limit: int = Query(50, ge=1, le=200),
              db: Session = Depends(get_db), user: User = Depends(require("inspection:read"))):
    query = db.query(ReviewTask).filter(ReviewTask.organization_id == user.organization_id, ReviewTask.status == status)
    tasks = query.order_by(ReviewTask.priority.desc(), ReviewTask.created_at.asc()).limit(500 if reason else limit).all()
    if reason:
        tasks = [t for t in tasks if any(r.get("code") == reason for r in (t.reasons or []))][:limit]
    return [_task_summary(t) for t in tasks]


@router.get("/stats")
def get_stats(db: Session = Depends(get_db), user: User = Depends(require("inspection:read"))):
    org = user.organization_id
    open_tasks = db.query(ReviewTask).filter(ReviewTask.organization_id == org, ReviewTask.status == "OPEN").all()
    by_reason: dict = {}
    for t in open_tasks:
        for r in t.reasons or []:
            by_reason[r.get("code")] = by_reason.get(r.get("code"), 0) + 1
    since = (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)
    done_24h = db.query(func.count(ReviewTask.id)).filter(ReviewTask.organization_id == org, ReviewTask.status == "DONE",
                                                          ReviewTask.completed_at >= since).scalar()
    verified = (db.query(func.count(Image.id)).join(Inspection, Inspection.id == Image.inspection_id)
                .filter(Inspection.organization_id == org, Image.review_status == "VERIFIED").scalar())
    splits = dict(db.query(Image.dataset_split, func.count(Image.id)).join(Inspection, Inspection.id == Image.inspection_id)
                  .filter(Inspection.organization_id == org, Image.review_status == "VERIFIED")
                  .group_by(Image.dataset_split).all())
    return {"open": len(open_tasks), "by_reason": by_reason, "done_last_24h": done_24h, "verified_images": verified,
            "verified_by_split": {k or "unassigned": v for k, v in splits.items()},
            "new_verified_since_last_dataset": datasets.verified_since_last_dataset(db, org),
            "auto_train_threshold": settings.AUTO_TRAIN_MIN_NEW_VERIFIED, "classes": learning_classes()}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(require("inspection:read"))):
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id, ReviewTask.organization_id == user.organization_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found")
    detections = [DefectDetectionResponse.model_validate(d) for d in task.inspection.defect_detections
                  if d.image_id == task.image_id]
    return {**_task_summary(task), "detections": detections,
            "image_size": ((task.image.quality_metadata or {}).get("defect_scan") or {}).get("image_size"),
            "defect_types": DEFECT_TYPES}


@router.post("/images/{image_id}/request", status_code=201)
def request_review(image_id: str, req: RequestReview, db: Session = Depends(get_db),
                   user: User = Depends(require("review:write"))):
    image, insp = _org_image(db, image_id, user)
    task = db.query(ReviewTask).filter(ReviewTask.image_id == image.id).first()
    reason = {"code": "MANUAL", "detail": req.reason or f"Requested by {user.full_name}"}
    if task:
        task.status = "OPEN"
        task.priority = max(task.priority or 0, 10)
        task.reasons = [*(task.reasons or []), reason]
    else:
        task = ReviewTask(organization_id=insp.organization_id, inspection_id=insp.id, image_id=image.id,
                          priority=10, reasons=[reason], source="MANUAL", status="OPEN")
        db.add(task)
    db.commit()
    return _task_summary(task)


@router.post("/images/{image_id}/annotations", response_model=DefectDetectionResponse, status_code=201)
def add_annotation(image_id: str, req: AnnotationCreate, db: Session = Depends(get_db),
                   user: User = Depends(require("review:write"))):
    """A reviewer-drawn box for a defect the detectors missed (false negative) — becomes a training label."""
    image, insp = _org_image(db, image_id, user)
    if insp.status == "FINALIZED":
        raise HTTPException(status_code=409, detail="Inspection is finalized")
    x1, y1, x2, y2 = req.bbox
    if x2 - x1 < 2 or y2 - y1 < 2 or min(req.bbox) < 0:
        raise HTTPException(status_code=400, detail="Box must have positive width and height")
    size = ((image.quality_metadata or {}).get("defect_scan") or {}).get("image_size")
    if size and (x2 > size[0] + 1 or y2 > size[1] + 1):
        raise HTTPException(status_code=400, detail="Box lies outside the image")
    defect_type = req.defect_type.upper()
    area = ((x2 - x1) * (y2 - y1)) / (size[0] * size[1]) if size else 0.0
    det = DefectDetection(
        inspection_id=insp.id, image_id=image.id, defect_type=defect_type, confidence=1.0, bbox=[x1, y1, x2, y2],
        area_ratio=round(area, 5), detector="HUMAN", reviewer_status="CONFIRMED", reviewer_note=req.note,
        metrics={"method": "reviewer_annotation", "annotated_by": user.full_name,
                 **({"bbox_norm": [x1 / size[0], y1 / size[1], x2 / size[0], y2 / size[1]]} if size else {})},
        severity=grade_severity({"defect_type": defect_type, "metrics": {}, "area_ratio": area, "confidence": 1.0}),
    )
    db.add(det)
    db.add(ReviewerAction(inspection_id=insp.id, reviewer_id=user.id, action_type="ADD_DEFECT",
                          target_field=f"image:{image.id}", new_value=defect_type, reason=req.note))
    pipeline.audit(db, insp.id, user.id, "REVIEWER_ACTION", f"Missed {defect_type.lower()} drawn by {user.full_name}",
                   {"image_id": image.id})
    db.commit()
    db.refresh(insp)
    pipeline.refresh_outcome(db, insp)
    db.refresh(det)
    return det


@router.delete("/annotations/{detection_id}", status_code=204)
def delete_annotation(detection_id: str, db: Session = Depends(get_db), user: User = Depends(require("review:write"))):
    det = (db.query(DefectDetection).join(Inspection, Inspection.id == DefectDetection.inspection_id)
           .filter(DefectDetection.id == detection_id, Inspection.organization_id == user.organization_id).first())
    if not det:
        raise HTTPException(status_code=404, detail="Annotation not found")
    if det.detector != "HUMAN":
        raise HTTPException(status_code=400, detail="Only reviewer-drawn boxes can be deleted; reject model detections instead")
    insp = det.inspection
    db.delete(det)
    db.commit()
    db.refresh(insp)
    pipeline.refresh_outcome(db, insp)


@router.post("/images/{image_id}/complete")
def complete_review(image_id: str, req: CompleteReview, db: Session = Depends(get_db),
                    user: User = Depends(require("review:write"))):
    """
    Marks the image VERIFIED: every defect on it has been confirmed, rejected, relabelled or drawn, so its
    labels (and its unlabelled areas, as negatives) can be used for training.
    """
    image, insp = _org_image(db, image_id, user)
    pending = db.query(DefectDetection).filter(DefectDetection.image_id == image.id,
                                               DefectDetection.reviewer_status == "PENDING").all()
    if pending and not req.accept_pending:
        raise HTTPException(status_code=409, detail=f"{len(pending)} detection(s) are still unreviewed")
    for d in pending:
        d.reviewer_status = "CONFIRMED"
    now = datetime.now(timezone.utc)
    image.review_status = "VERIFIED"
    image.reviewed_by_id = user.id
    image.reviewed_at = now
    split = datasets.assign_split(image, insp)
    task = db.query(ReviewTask).filter(ReviewTask.image_id == image.id).first()
    if not task:
        task = ReviewTask(organization_id=insp.organization_id, inspection_id=insp.id, image_id=image.id,
                          priority=0, reasons=[{"code": "MANUAL", "detail": "Verified from the inspection page"}],
                          source="MANUAL")
        db.add(task)
    task.status = "DONE"
    task.completed_by_id = user.id
    task.completed_at = now
    db.add(ReviewerAction(inspection_id=insp.id, reviewer_id=user.id, action_type="VERIFY_IMAGE",
                          target_field=f"image:{image.id}", new_value=f"VERIFIED ({split})",
                          reason=req.note or (f"{len(pending)} pending detection(s) accepted" if pending else None)))
    pipeline.audit(db, insp.id, user.id, "IMAGE_VERIFIED",
                   f"Image verified by {user.full_name} for training ({split} split)"
                   + (f"; {len(pending)} pending detection(s) accepted" if pending else ""),
                   {"image_id": image.id, "split": split})
    db.commit()
    db.refresh(insp)
    pipeline.refresh_outcome(db, insp)
    queued = _maybe_auto_train(db, insp.organization_id, user)
    return {"image_id": image.id, "review_status": image.review_status, "dataset_split": split,
            "accepted_pending": len(pending), "auto_training_job_id": queued}


@router.post("/tasks/{task_id}/skip")
def skip_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(require("review:write"))):
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id, ReviewTask.organization_id == user.organization_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found")
    task.status = "SKIPPED"
    task.completed_by_id = user.id
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": task.id, "status": task.status}


def _maybe_auto_train(db: Session, organization_id: str, user: User) -> Optional[str]:
    """Queues dataset build + training once enough new verified images exist (if the policy is enabled)."""
    threshold = settings.AUTO_TRAIN_MIN_NEW_VERIFIED
    if threshold <= 0 or datasets.verified_since_last_dataset(db, organization_id) < threshold:
        return None
    from app.models.all_models import Job, ModelVersion
    from app.services.learning.training import TRAINING_JOB, create_training_candidate

    busy = db.query(Job).filter(Job.organization_id == organization_id, Job.job_type == TRAINING_JOB,
                                Job.status.in_(("QUEUED", "RUNNING"))).first()
    if busy:
        return None
    mv = create_training_candidate(db, organization_id, None, notes="Auto-triggered by new verified images")
    job = job_service.enqueue(db, TRAINING_JOB, {"model_version_id": mv.id}, organization_id=organization_id,
                              created_by_id=None)
    return job.id
