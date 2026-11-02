import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require
from app.core.config import settings
from app.core.database import get_db
from app.models.all_models import (
    DatasetVersion, DefectDetection, Image as ImageModel, Job, ModelEvent, ModelVersion, Plant, Product,
    ProductionLine, Station, User
)
from app.schemas.all_schemas import JobResponse
from app.services import defect_pipeline as pipeline
from app.services import job_service
from app.services.learning import datasets
from app.services.learning.drift import station_drift
from app.services.learning.registry import learning_classes, registry
from app.services.learning.shadow import shadow_stats
from app.services.learning.training import EVALUATION_JOB, TRAINING_JOB, create_training_candidate
from app.services.storage_service import storage_service

router = APIRouter(prefix="/learning", tags=["Learning Loop & Model Registry"])


class TrainRequest(BaseModel):
    dataset_version_id: Optional[str] = None  # omitted: build a fresh dataset from all verified images
    notes: Optional[str] = Field(None, max_length=500)


class OverrideRequest(BaseModel):
    override_reason: Optional[str] = Field(None, max_length=500)


class SeedRequest(BaseModel):
    count: int = Field(60, ge=5, le=500)


def _model(db: Session, model_id: str, user: User) -> ModelVersion:
    mv = db.query(ModelVersion).filter(ModelVersion.id == model_id, ModelVersion.organization_id == user.organization_id).first()
    if not mv:
        raise HTTPException(status_code=404, detail="Model version not found")
    return mv


def _dataset(db: Session, dataset_id: str, user: User) -> DatasetVersion:
    ds = db.query(DatasetVersion).filter(DatasetVersion.id == dataset_id, DatasetVersion.organization_id == user.organization_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    return ds


def _model_dict(mv: ModelVersion) -> dict:
    return {
        "id": mv.id, "version": mv.version, "name": mv.name, "status": mv.status, "source": mv.source,
        "parent_id": mv.parent_id, "dataset_version_id": mv.dataset_version_id,
        "dataset_version": mv.dataset_version.version if mv.dataset_version else None,
        "classes": mv.classes, "input_size": mv.input_size, "sha256": mv.sha256,
        "train_metrics": mv.train_metrics, "gate_report": mv.gate_report, "model_card": mv.model_card,
        "job_id": mv.job_id, "created_at": mv.created_at, "approved_at": mv.approved_at,
        "activated_at": mv.activated_at, "notes": mv.notes,
    }


def _dataset_dict(ds: DatasetVersion) -> dict:
    return {"id": ds.id, "version": ds.version, "status": ds.status, "classes": ds.classes,
            "image_count": ds.image_count, "label_count": ds.label_count, "class_counts": ds.class_counts,
            "split_counts": ds.split_counts, "manifest_sha256": ds.manifest_sha256, "job_id": ds.job_id,
            "created_at": ds.created_at, "notes": ds.notes}


# ---------------------------------------------------------------- overview
@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(require("model:read"))):
    org = user.organization_id
    active, shadow = registry.active(db, org), registry.shadow(db, org)
    last_ds = (db.query(DatasetVersion).filter(DatasetVersion.organization_id == org)
               .order_by(DatasetVersion.version.desc()).first())
    running = (db.query(Job).filter(Job.organization_id == org, Job.job_type.in_((TRAINING_JOB, EVALUATION_JOB, datasets.DATASET_JOB)),
                                    Job.status.in_(("QUEUED", "RUNNING"))).order_by(Job.created_at.desc()).all())
    return {
        "active_model": _model_dict(active) if active else None,
        "shadow_model": {**_model_dict(shadow), "shadow_stats": shadow_stats(db, shadow)} if shadow else None,
        "latest_dataset": _dataset_dict(last_ds) if last_ds else None,
        "new_verified_since_last_dataset": datasets.verified_since_last_dataset(db, org),
        "running_jobs": [JobResponse.model_validate(j) for j in running],
        "policy": {
            "classes": learning_classes(), "auto_train_min_new_verified": settings.AUTO_TRAIN_MIN_NEW_VERIFIED,
            "uncertain_band": [settings.REVIEW_UNCERTAIN_LOW, settings.REVIEW_UNCERTAIN_HIGH],
            "audit_rate": settings.REVIEW_AUDIT_RATE, "drift_audit_rate": settings.REVIEW_DRIFT_AUDIT_RATE,
            "gate": {"map_tolerance": settings.GATE_MAP_TOLERANCE, "max_class_recall_drop": settings.GATE_MAX_CLASS_RECALL_DROP,
                     "critical_class": settings.GATE_CRITICAL_CLASS, "critical_min_recall": settings.GATE_CRITICAL_MIN_RECALL,
                     "max_latency_ratio": settings.GATE_MAX_LATENCY_RATIO, "min_test_images": settings.GATE_MIN_TEST_IMAGES},
            "training": {"epochs": settings.TRAIN_EPOCHS, "imgsz": settings.TRAIN_IMGSZ, "device": settings.TRAIN_DEVICE},
        },
    }


# ---------------------------------------------------------------- datasets
@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db), user: User = Depends(require("model:read"))):
    rows = (db.query(DatasetVersion).filter(DatasetVersion.organization_id == user.organization_id)
            .order_by(DatasetVersion.version.desc()).all())
    return [_dataset_dict(d) for d in rows]


@router.post("/datasets", response_model=JobResponse, status_code=202)
def build_dataset(db: Session = Depends(get_db), user: User = Depends(require("model:manage"))):
    ds = datasets.create_dataset_version(db, user.organization_id, user.id)
    return job_service.enqueue(db, datasets.DATASET_JOB, {"dataset_version_id": ds.id},
                               organization_id=user.organization_id, created_by_id=user.id)


@router.get("/datasets/{dataset_id}/download")
def download_dataset(dataset_id: str, db: Session = Depends(get_db), user: User = Depends(require("model:manage"))):
    ds = _dataset(db, dataset_id, user)
    if ds.status != "READY" or not ds.storage_key:
        raise HTTPException(status_code=409, detail="Dataset is not ready")
    return FileResponse(storage_service.local_path(ds.storage_key), media_type="application/zip",
                        filename=f"parakhmaan_dataset_v{ds.version}.zip")


# ---------------------------------------------------------------- models
@router.get("/models")
def list_models(db: Session = Depends(get_db), user: User = Depends(require("model:read"))):
    rows = (db.query(ModelVersion).filter(ModelVersion.organization_id == user.organization_id)
            .order_by(ModelVersion.version.desc()).all())
    return [_model_dict(m) for m in rows]


@router.get("/models/{model_id}")
def get_model(model_id: str, db: Session = Depends(get_db), user: User = Depends(require("model:read"))):
    mv = _model(db, model_id, user)
    events = (db.query(ModelEvent).filter(ModelEvent.model_version_id == mv.id).order_by(ModelEvent.created_at.desc()).all())
    return {**_model_dict(mv), "shadow_stats": shadow_stats(db, mv),
            "events": [{"event_type": e.event_type, "description": e.description, "created_at": e.created_at,
                        "payload": e.payload} for e in events]}


@router.post("/models/train", response_model=JobResponse, status_code=202)
def train_model(req: TrainRequest, db: Session = Depends(get_db), user: User = Depends(require("model:manage"))):
    if req.dataset_version_id:
        ds = _dataset(db, req.dataset_version_id, user)
        if ds.status != "READY":
            raise HTTPException(status_code=409, detail="Dataset is not ready")
    busy = db.query(Job).filter(Job.organization_id == user.organization_id, Job.job_type == TRAINING_JOB,
                                Job.status.in_(("QUEUED", "RUNNING"))).first()
    if busy:
        raise HTTPException(status_code=409, detail="A training job is already running")
    mv = create_training_candidate(db, user.organization_id, user.id, req.dataset_version_id, req.notes)
    return job_service.enqueue(db, TRAINING_JOB, {"model_version_id": mv.id},
                               organization_id=user.organization_id, created_by_id=user.id)


@router.post("/models/{model_id}/evaluate", response_model=JobResponse, status_code=202)
def evaluate_model(model_id: str, dataset_version_id: Optional[str] = None, db: Session = Depends(get_db),
                   user: User = Depends(require("model:manage"))):
    mv = _model(db, model_id, user)
    if dataset_version_id:
        _dataset(db, dataset_version_id, user)
    elif not mv.dataset_version_id:
        latest = (db.query(DatasetVersion).filter(DatasetVersion.organization_id == user.organization_id,
                                                  DatasetVersion.status == "READY")
                  .order_by(DatasetVersion.version.desc()).first())
        if not latest:
            raise HTTPException(status_code=409, detail="Build a dataset first")
        dataset_version_id = latest.id
    return job_service.enqueue(db, EVALUATION_JOB, {"model_version_id": mv.id, "dataset_version_id": dataset_version_id},
                               organization_id=user.organization_id, created_by_id=user.id)


@router.post("/models/{model_id}/shadow")
def start_shadow(model_id: str, req: OverrideRequest, db: Session = Depends(get_db),
                 user: User = Depends(require("model:manage"))):
    return _model_dict(registry.start_shadow(db, _model(db, model_id, user), user, req.override_reason))


@router.delete("/models/{model_id}/shadow")
def stop_shadow(model_id: str, db: Session = Depends(get_db), user: User = Depends(require("model:manage"))):
    return _model_dict(registry.stop_shadow(db, _model(db, model_id, user), user))


@router.post("/models/{model_id}/promote")
def promote(model_id: str, req: OverrideRequest, db: Session = Depends(get_db),
            user: User = Depends(require("model:manage"))):
    return _model_dict(registry.promote(db, _model(db, model_id, user), user, req.override_reason))


@router.post("/models/{model_id}/rollback")
def rollback(model_id: str, db: Session = Depends(get_db), user: User = Depends(require("model:manage"))):
    return _model_dict(registry.rollback(db, _model(db, model_id, user), user))


@router.get("/models/{model_id}/download")
def download_model(model_id: str, db: Session = Depends(get_db), user: User = Depends(require("model:manage"))):
    mv = _model(db, model_id, user)
    if not mv.onnx_key:
        raise HTTPException(status_code=409, detail="Model has no ONNX artefact")
    return FileResponse(storage_service.local_path(mv.onnx_key), media_type="application/octet-stream",
                        filename=f"parakhmaan_{mv.name}.onnx")


# ---------------------------------------------------------------- monitoring
@router.get("/drift")
def drift(recent_hours: int = Query(24, ge=1, le=24 * 30), baseline_days: int = Query(14, ge=2, le=180),
          db: Session = Depends(get_db), user: User = Depends(require("model:read"))):
    return {"recent_hours": recent_hours, "baseline_days": baseline_days,
            "thresholds": {"watch": settings.DRIFT_PSI_WATCH, "alert": settings.DRIFT_PSI_ALERT},
            "stations": station_drift(db, user.organization_id, recent_hours, baseline_days)}


@router.get("/events")
def events(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), user: User = Depends(require("model:read"))):
    rows = (db.query(ModelEvent).filter(ModelEvent.organization_id == user.organization_id)
            .order_by(ModelEvent.created_at.desc()).limit(limit).all())
    names = {m.id: m.name for m in db.query(ModelVersion).filter(ModelVersion.organization_id == user.organization_id)}
    return [{"id": e.id, "event_type": e.event_type, "description": e.description, "created_at": e.created_at,
             "model": names.get(e.model_version_id), "payload": e.payload} for e in rows]


# ---------------------------------------------------------------- development helper
@router.post("/demo/seed-reviewed")
def seed_reviewed(req: SeedRequest, db: Session = Depends(get_db), user: User = Depends(require("system:configure"))):
    """
    Development only: creates synthetic surface images with known defect boxes as already-verified
    inspections, so the full loop (dataset -> training -> gate -> shadow -> promotion) can be demonstrated.
    Synthetic data exercises the pipeline; it is not evidence of real-world accuracy.
    """
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Disabled in production")
    from app.services.learning.evaluation import synth_labelled

    rng = np.random.default_rng(int(datetime.now().timestamp()))
    stations = (db.query(Station).join(ProductionLine, ProductionLine.id == Station.line_id)
                .join(Plant, Plant.id == ProductionLine.plant_id)
                .filter(Plant.organization_id == user.organization_id, Station.is_active.is_(True)).all())
    products = db.query(Product).filter(Product.organization_id == user.organization_id).all()
    created = 0
    now = datetime.now(timezone.utc)
    for i in range(req.count):
        img, gts = synth_labelled(rng)
        batch = f"SYN-{int(rng.integers(1, max(4, req.count // 3)) ):03d}"
        when = now - timedelta(hours=float(rng.uniform(0, 72)))
        insp = pipeline.create_inspection(
            db, user.organization_id, user,
            station_id=stations[i % len(stations)].id if stations else None,
            product_id=products[i % len(products)].id if products else None,
            batch_code=batch, notes="Synthetic verified sample (demo)", created_at=when,
        )
        key = storage_service.save_bytes(cv2.imencode(".jpg", img)[1].tobytes(), insp.id, "synthetic.jpg")
        h, w = img.shape[:2]
        image = ImageModel(inspection_id=insp.id, surface_type="SURFACE", file_path=key, original_filename="synthetic.jpg",
                           quality_score=1.0, ocr_raw_data=[], created_at=when, review_status="VERIFIED",
                           reviewed_by_id=user.id, reviewed_at=now,
                           quality_metadata={"defect_scan": {"image_size": [w, h], "backend": "SYNTHETIC",
                                                             "mean_brightness": float(img.mean()), "exposure_ok": True}})
        db.add(image)
        db.flush()
        for cls, (x1, y1, x2, y2) in gts:
            db.add(DefectDetection(inspection_id=insp.id, image_id=image.id, defect_type=cls, confidence=1.0,
                                   bbox=[float(x1), float(y1), float(x2), float(y2)], detector="HUMAN",
                                   reviewer_status="CONFIRMED", severity="MEDIUM", created_at=when,
                                   metrics={"method": "synthetic_ground_truth",
                                            "bbox_norm": [x1 / w, y1 / h, x2 / w, y2 / h]}))
        datasets.assign_split(image, insp)
        db.commit()
        db.refresh(insp)
        pipeline.refresh_outcome(db, insp)
        created += 1
    return {"created": created, "note": "Synthetic images verified with known ground truth (demo data)"}
