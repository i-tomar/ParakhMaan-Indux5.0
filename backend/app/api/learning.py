"""Review queue, dataset versions, training jobs, model registry, promotion and rollback."""
import os
from typing import Any, Dict, List, Optional

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_roles
from app.core.database import get_db
from app.models.all_models import DefectDetection, User
from app.models.industrial import DatasetSample, DatasetVersion, ModelVersion, Product, ProductionUnit, TrainingJob
from app.services.learning import service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/learning", tags=["Continuous Learning"])


class TrainRequest(BaseModel):
    product_key: str
    coreset: int = 3000


class RollbackRequest(BaseModel):
    kind: str = "ANOMALY"
    product_key: Optional[str] = None


class UnitLabel(BaseModel):
    label: str  # GOOD, or a defect class


def _version(m: ModelVersion) -> Dict[str, Any]:
    return {"id": m.id, "kind": m.kind, "product_key": m.product_key, "version": m.version, "status": m.status, "metrics": m.metrics,
            "gate_result": m.gate_result, "parent_version": m.parent_version, "notes": m.notes, "created_at": m.created_at,
            "promoted_at": m.promoted_at, "dataset_version_id": m.dataset_version_id}


def _job(j: TrainingJob) -> Dict[str, Any]:
    return {"id": j.id, "kind": j.kind, "product_key": j.product_key, "status": j.status, "candidate_version": j.candidate_version,
            "error": j.error, "created_at": j.created_at, "finished_at": j.finished_at}


@router.get("/review-queue")
def review_queue(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    units = (db.query(ProductionUnit).filter(ProductionUnit.decision == "MANUAL_REVIEW", ProductionUnit.final_decision.is_(None))
             .order_by(ProductionUnit.inspected_at.desc()).limit(limit).all())
    pending = db.query(func.count(DefectDetection.id)).filter(DefectDetection.reviewer_status == "PENDING").scalar()
    from app.api.production import unit_dict
    return {"pending_detections": pending, "units": [unit_dict(u) for u in units]}


@router.post("/units/{unit_id}/label")
def label_unit(unit_id: str, req: UnitLabel, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Stores a reviewed full image as a training sample. GOOD samples extend the anomaly model."""
    unit = db.get(ProductionUnit, unit_id)
    if not unit or not unit.product or not unit.image_path or not os.path.exists(unit.image_path):
        raise HTTPException(404, "Unit, product or stored image not found")
    sample = service.add_sample(db, unit.product.key, req.label, unit.image_path, source="REVIEW", reviewer_id=user.id)
    return {"added": sample is not None, "split": sample.split if sample else None}


@router.post("/samples")
async def upload_sample(
    product_key: str = Form(...), label: str = Form("GOOD"), files: List[UploadFile] = File(...), db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not db.query(Product).filter(Product.key == product_key).first():
        raise HTTPException(404, "Product not found")
    added, duplicate, unreadable = 0, 0, 0
    for file in files:
        path = await storage_service.save_upload(file, f"samples_{product_key}")
        if cv2.imread(path) is None:
            unreadable += 1
        elif service.add_sample(db, product_key, label, path, source="UPLOAD", reviewer_id=user.id):
            added += 1
        else:
            duplicate += 1
        os.remove(path)
    return {"added": added, "duplicates": duplicate, "unreadable": unreadable}


@router.get("/samples/summary")
def sample_summary(product_key: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(DatasetSample.product_key, DatasetSample.label, DatasetSample.split, func.count(DatasetSample.id))
    if product_key:
        q = q.filter(DatasetSample.product_key == product_key)
    rows = q.group_by(DatasetSample.product_key, DatasetSample.label, DatasetSample.split).all()
    return [{"product_key": k, "label": label, "split": s, "count": n} for k, label, s, n in rows]


@router.get("/datasets")
def datasets(product_key: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(DatasetVersion)
    if product_key:
        q = q.filter(DatasetVersion.product_key == product_key)
    return [{"id": d.id, "product_key": d.product_key, "version": d.version, "content_hash": d.content_hash, "sample_count": d.sample_count,
             "label_counts": d.label_counts, "created_at": d.created_at} for d in q.order_by(DatasetVersion.created_at.desc()).all()]


@router.post("/datasets/{product_key}")
def snapshot_dataset(product_key: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        row = service.create_dataset_version(db, product_key)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"id": row.id, "version": row.version, "content_hash": row.content_hash, "sample_count": row.sample_count}


@router.post("/train")
def train(req: TrainRequest, wait: bool = False, db: Session = Depends(get_db), _: User = Depends(require_roles("SUPERVISOR"))):
    if not db.query(Product).filter(Product.key == req.product_key).first():
        raise HTTPException(404, "Product not found")
    goods = db.query(func.count(DatasetSample.id)).filter(DatasetSample.product_key == req.product_key, DatasetSample.label == "GOOD",
                                                          DatasetSample.split == "TRAIN").scalar()
    if goods < 5:
        raise HTTPException(422, f"At least 5 good training images are needed, found {goods}")
    return _job(service.start_training(db, req.product_key, {"coreset": req.coreset}, wait=wait))


@router.get("/jobs")
def jobs(db: Session = Depends(get_db)):
    return [_job(j) for j in db.query(TrainingJob).order_by(TrainingJob.created_at.desc()).limit(50).all()]


@router.get("/jobs/{job_id}")
def job(job_id: str, db: Session = Depends(get_db)):
    row = db.get(TrainingJob, job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    return {**_job(row), "log": row.log}


@router.get("/models")
def models(kind: Optional[str] = None, product_key: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(ModelVersion)
    if kind:
        q = q.filter(ModelVersion.kind == kind)
    if product_key:
        q = q.filter(ModelVersion.product_key == product_key)
    return [_version(m) for m in q.order_by(ModelVersion.created_at.desc()).all()]


@router.post("/models/{version_id}/promote")
def promote(version_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPERVISOR"))):
    try:
        return _version(service.promote(db, version_id, user.full_name))
    except PermissionError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/models/rollback")
def rollback(req: RollbackRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("SUPERVISOR"))):
    try:
        return _version(service.rollback(db, req.kind, req.product_key, user.full_name))
    except ValueError as e:
        raise HTTPException(409, str(e))
