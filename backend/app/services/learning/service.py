"""Feedback → dataset version → training → holdout comparison → gated promotion → rollback.

Anomaly retraining runs on the edge node with no training framework. It runs in a background
thread with a status row. Segmentation retraining needs PyTorch, so `ml/retrain_yolo.py` runs in
the ml/ environment and registers its candidate through this same gate.
"""
import hashlib
import json
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import resolve_backend_path, settings
from app.core.database import SessionLocal
from app.models.industrial import DatasetSample, DatasetVersion, ModelVersion, TrainingJob
from app.services.inference.anomaly_engine import ProductModel, fit_product, image_score, score_map
from app.services.inference.engine import engine
from app.services.learning.gate import evaluate_gate

logger = logging.getLogger(__name__)
GOOD = "GOOD"
HOLDOUT_EVERY = 5  # one in five samples of each label goes to the holdout, permanently


def roc_auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based AUROC (Mann-Whitney), with ties averaged. Avoids a scikit-learn runtime dependency."""
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1)
    for value in np.unique(scores):
        same = scores == value
        ranks[same] = ranks[same].mean()
    positives, negatives = int(labels.sum()), int((~labels).sum())
    return float((ranks[labels].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def samples_root(product_key: str) -> str:
    return os.path.join(settings.DEFECT_SAMPLES_DIR, product_key)


def add_sample(
    db: Session, product_key: str, label: str, source_path: str, *, annotation: Optional[Dict[str, Any]] = None,
    source: str = "REVIEW", detection_id: Optional[str] = None, reviewer_id: Optional[str] = None,
) -> Optional[DatasetSample]:
    """Adds one image. Duplicates are ignored. The split is fixed at insertion and never changes,
    which is what keeps the holdout independent of every later training run."""
    digest = _sha256(source_path)
    existing = db.query(DatasetSample).filter(DatasetSample.product_key == product_key, DatasetSample.sha256 == digest).first()
    if existing:
        return None
    label = label.upper()
    count = db.query(func.count(DatasetSample.id)).filter(DatasetSample.product_key == product_key, DatasetSample.label == label).scalar()
    split = "HOLDOUT" if (count + 1) % HOLDOUT_EVERY == 0 else "TRAIN"
    folder = os.path.join(samples_root(product_key), label)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"{digest[:20]}{os.path.splitext(source_path)[1] or '.jpg'}")
    shutil.copyfile(source_path, target)
    sample = DatasetSample(product_key=product_key, label=label, file_path=target, sha256=digest, annotation=annotation,
                           split=split, source=source, source_detection_id=detection_id, reviewer_id=reviewer_id)
    db.add(sample)
    db.commit()
    return sample


def create_dataset_version(db: Session, product_key: str) -> DatasetVersion:
    """Immutable snapshot. Identical content gives the identical hash and reuses the version."""
    samples = db.query(DatasetSample).filter(DatasetSample.product_key == product_key).order_by(DatasetSample.sha256).all()
    if not samples:
        raise ValueError(f"No samples collected for {product_key}")
    entries = [{"sha256": s.sha256, "label": s.label, "split": s.split, "path": s.file_path, "annotation": s.annotation} for s in samples]
    digest = hashlib.sha256(json.dumps([[e["sha256"], e["label"], e["split"]] for e in entries]).encode()).hexdigest()
    existing = db.query(DatasetVersion).filter(DatasetVersion.product_key == product_key, DatasetVersion.content_hash == digest).first()
    if existing:
        return existing
    version = 1 + (db.query(func.max(DatasetVersion.version)).filter(DatasetVersion.product_key == product_key).scalar() or 0)
    folder = os.path.join(settings.DEFECT_SAMPLES_DIR, "_versions", product_key)
    os.makedirs(folder, exist_ok=True)
    manifest = os.path.join(folder, f"v{version}.json")
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump({"product_key": product_key, "version": version, "content_hash": digest, "samples": entries}, f, indent=1)
    counts: Dict[str, int] = {}
    for e in entries:
        name = f"{e['split']}/{e['label']}"
        counts[name] = counts.get(name, 0) + 1
    row = DatasetVersion(product_key=product_key, version=version, content_hash=digest, sample_count=len(entries),
                         label_counts=counts, manifest_path=manifest)
    db.add(row)
    db.commit()
    return row


def evaluate_on_holdout(model: ProductModel, holdout: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Scores against the fixed holdout at the model's own good-only threshold."""
    scores, labels = [], []
    for item in holdout:
        image = cv2.imread(item["path"])
        if image is None:
            continue
        scores.append(image_score(score_map(engine.extractor, model, image)))
        labels.append(item["label"] != GOOD)
    s, y = np.array(scores), np.array(labels, dtype=bool)
    pred = s >= model.image_threshold
    tp, fp = int((pred & y).sum()), int((pred & ~y).sum())
    fn, tn = int((~pred & y).sum()), int((~pred & ~y).sum())
    return {
        "holdout_good": int((~y).sum()), "holdout_defective": int(y.sum()),
        "image_auroc": round(roc_auc(s, y), 4) if y.any() and (~y).any() else None,
        "recall": round(tp / max(1, tp + fn), 4), "false_reject_rate": round(fp / max(1, fp + tn), 4),
        "precision": round(tp / max(1, tp + fp), 4), "threshold": round(model.image_threshold, 4),
    }


def _model_folder(product_key: str, version: str) -> str:
    return os.path.join(resolve_backend_path(settings.ANOMALY_PRODUCTS_DIR), "_registry", product_key, version)


def production_model(db: Session, kind: str, product_key: Optional[str]) -> Optional[ModelVersion]:
    return db.query(ModelVersion).filter(ModelVersion.kind == kind, ModelVersion.product_key == product_key,
                                         ModelVersion.status == "PRODUCTION").first()


def train_anomaly(db: Session, job: TrainingJob) -> ModelVersion:
    if engine.extractor is None:
        raise RuntimeError(engine.anomaly_error or "Anomaly backbone not loaded")
    key = job.product_key
    dataset = create_dataset_version(db, key)
    with open(dataset.manifest_path, encoding="utf-8") as f:
        entries = json.load(f)["samples"]
    train = [e for e in entries if e["split"] == "TRAIN" and e["label"] == GOOD]
    holdout = [e for e in entries if e["split"] == "HOLDOUT"]
    overlap = {e["sha256"] for e in train} & {e["sha256"] for e in holdout}
    if overlap:  # cannot happen through add_sample; it would invalidate every number below
        raise RuntimeError(f"Holdout leakage: {len(overlap)} images in both splits")
    images = [img for img in (cv2.imread(e["path"]) for e in train) if img is not None]
    params = job.params or {}
    model = fit_product(engine.extractor, images, coreset_size=int(params.get("coreset", 3000)))
    metrics = {**evaluate_on_holdout(model, holdout), "train_images": len(images), "fit_seconds": model.meta["fit_seconds"]}

    n = 1 + db.query(func.count(ModelVersion.id)).filter(ModelVersion.kind == "ANOMALY", ModelVersion.product_key == key).scalar()
    version = f"{key}-anomaly-v{n}"
    folder = _model_folder(key, version)
    model.save(folder)
    current = production_model(db, "ANOMALY", key)
    # Rescore production on today's holdout, so both models answer the same exam.
    baseline = None
    if current and os.path.isdir(current.path):
        baseline = evaluate_on_holdout(ProductModel.load(current.path), holdout)
        current.metrics = {**(current.metrics or {}), "latest_holdout": baseline}
    gate = evaluate_gate("ANOMALY", metrics, baseline)
    row = ModelVersion(kind="ANOMALY", product_key=key, version=version, path=folder, status="CANDIDATE", metrics=metrics,
                       gate_result=gate, parent_version=current.version if current else None, dataset_version_id=dataset.id)
    db.add(row)
    db.commit()
    return row


def _run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(TrainingJob, job_id)
        job.status = "RUNNING"
        db.commit()
        try:
            row = train_anomaly(db, job)
            job.status, job.candidate_version = "SUCCEEDED", row.version
            job.log = json.dumps({"metrics": row.metrics, "gate": row.gate_result})
        except Exception as e:
            logger.exception("training job failed")
            db.rollback()
            job = db.get(TrainingJob, job_id)
            job.status, job.error = "FAILED", str(e)
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def start_training(db: Session, product_key: str, params: Optional[Dict[str, Any]] = None, wait: bool = False) -> TrainingJob:
    job = TrainingJob(kind="ANOMALY", product_key=product_key, params=params or {})
    db.add(job)
    db.commit()
    db.refresh(job)
    if wait:
        _run_job(job.id)
        db.refresh(job)
    else:
        threading.Thread(target=_run_job, args=(job.id,), daemon=True).start()
    return job


def promote(db: Session, version_id: str, reviewer: str) -> ModelVersion:
    row = db.get(ModelVersion, version_id)
    if row is None:
        raise ValueError("Model version not found")
    if row.status == "PRODUCTION":
        return row
    if not (row.gate_result or {}).get("passed"):
        row.status = "REFUSED"
        db.commit()
        failed = [c["check"] for c in (row.gate_result or {}).get("checks", []) if not c["passed"]]
        raise PermissionError(f"Promotion refused by gate: {', '.join(failed) or 'no gate result'}")
    _activate(db, row, reviewer)
    return row


def rollback(db: Session, kind: str, product_key: Optional[str], reviewer: str) -> ModelVersion:
    current = production_model(db, kind, product_key)
    previous = (db.query(ModelVersion).filter(ModelVersion.kind == kind, ModelVersion.product_key == product_key,
                                              ModelVersion.status == "ARCHIVED", ModelVersion.promoted_at.isnot(None))
                .order_by(ModelVersion.promoted_at.desc()).first())
    if previous is None:
        raise ValueError("No earlier production version to roll back to")
    if current:
        current.notes = f"Rolled back by {reviewer}"
    _activate(db, previous, reviewer)
    return previous


def _activate(db: Session, row: ModelVersion, reviewer: str) -> None:
    current = production_model(db, row.kind, row.product_key)
    if current and current.id != row.id:
        current.status = "ARCHIVED"
    row.status, row.promoted_at = "PRODUCTION", datetime.now(timezone.utc)
    row.notes = f"Activated by {reviewer}"
    db.commit()
    if row.kind == "ANOMALY":
        engine.load_product(row.product_key, row.path, row.version)
    else:
        engine.load_seg(row.path, row.version)
