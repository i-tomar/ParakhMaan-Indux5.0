"""
Versioned training datasets built only from human-verified images.

* Labels come from reviewed detections: CONFIRMED / RELABELED detections and boxes drawn by reviewers.
  REJECTED and unreviewed (PENDING) predictions are never used — unreviewed AI output is not ground truth.
* Splits are assigned once per image and never change ("sticky"), grouped by batch (or inspection when no
  batch is recorded) so near-identical images of one batch cannot leak across train / val / test.
* The "test" split is the frozen golden set the evaluation gate scores every candidate on.
* Each build is an immutable YOLO export (images/, labels/, data.yaml, manifest.json) zipped into
  object storage at datasets/<org>/v<N>/dataset.zip.
"""
import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import cv2
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.all_models import DatasetVersion, DefectDetection, Image, Inspection
from app.services import job_service
from app.services.learning.registry import learning_classes, log_event
from app.services.storage_service import storage_service

DATASET_JOB = "DATASET_BUILD"
LABEL_STATUSES = ("CONFIRMED", "RELABELED")


def assign_split(image: Image, insp: Inspection) -> str:
    if image.dataset_split:
        return image.dataset_split
    group = insp.batch_code or insp.id
    h = int(hashlib.sha256(f"{insp.organization_id}:{group}".encode()).hexdigest()[:8], 16) / 0x100000000
    if h < settings.SPLIT_TEST_FRACTION:
        image.dataset_split = "test"
    elif h < settings.SPLIT_TEST_FRACTION + settings.SPLIT_VAL_FRACTION:
        image.dataset_split = "val"
    else:
        image.dataset_split = "train"
    return image.dataset_split


def image_labels(db: Session, image: Image, classes: List[str]) -> List[Tuple[int, List[float]]]:
    index = {c.upper(): i for i, c in enumerate(classes)}
    labels = []
    for d in db.query(DefectDetection).filter(DefectDetection.image_id == image.id,
                                              DefectDetection.reviewer_status.in_(LABEL_STATUSES)):
        if d.defect_type in index and d.bbox and len(d.bbox) == 4:
            labels.append((index[d.defect_type], d.bbox))
    return labels


def verified_since_last_dataset(db: Session, organization_id: str) -> int:
    last = (db.query(DatasetVersion).filter(DatasetVersion.organization_id == organization_id,
                                            DatasetVersion.status == "READY")
            .order_by(DatasetVersion.version.desc()).first())
    query = (db.query(func.count(Image.id)).join(Inspection, Inspection.id == Image.inspection_id)
             .filter(Inspection.organization_id == organization_id, Image.review_status == "VERIFIED"))
    if last:
        query = query.filter(Image.reviewed_at > last.created_at)
    return query.scalar() or 0


def create_dataset_version(db: Session, organization_id: str, user_id: Optional[str], notes: Optional[str] = None) -> DatasetVersion:
    version = (db.query(func.max(DatasetVersion.version)).filter(DatasetVersion.organization_id == organization_id).scalar() or 0) + 1
    ds = DatasetVersion(organization_id=organization_id, version=version, status="BUILDING",
                        classes=learning_classes(), created_by_id=user_id, notes=notes)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def build_dataset(db: Session, ds: DatasetVersion, progress=None) -> DatasetVersion:
    classes = ds.classes or learning_classes()
    images = (db.query(Image, Inspection).join(Inspection, Inspection.id == Image.inspection_id)
              .filter(Inspection.organization_id == ds.organization_id, Image.review_status == "VERIFIED",
                      Image.surface_type != "REFERENCE")
              .order_by(Image.created_at).all())
    work = tempfile.mkdtemp(prefix="pm_dataset_")
    try:
        for split in ("train", "val", "test"):
            os.makedirs(os.path.join(work, "images", split), exist_ok=True)
            os.makedirs(os.path.join(work, "labels", split), exist_ok=True)
        manifest: List[Dict[str, Any]] = []
        class_counts = {c: 0 for c in classes}
        split_counts = {"train": 0, "val": 0, "test": 0}
        label_total = 0
        for i, (image, insp) in enumerate(images):
            if not storage_service.exists(image.file_path):
                continue
            img = cv2.imread(storage_service.local_path(image.file_path))
            if img is None:
                continue
            split = assign_split(image, insp)
            h, w = img.shape[:2]
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            data = buf.tobytes()
            with open(os.path.join(work, "images", split, f"{image.id}.jpg"), "wb") as f:
                f.write(data)
            rows = []
            for cls, (x1, y1, x2, y2) in image_labels(db, image, classes):
                x1, x2 = max(0.0, min(w, x1)), max(0.0, min(w, x2))
                y1, y2 = max(0.0, min(h, y1)), max(0.0, min(h, y2))
                if x2 - x1 < 1 or y2 - y1 < 1:
                    continue
                rows.append(f"{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
                class_counts[classes[cls]] += 1
            with open(os.path.join(work, "labels", split, f"{image.id}.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(rows))
            label_total += len(rows)
            split_counts[split] += 1
            manifest.append({
                "image_id": image.id, "inspection": insp.inspection_number, "split": split,
                "batch": insp.batch_code, "station_id": insp.station_id, "product_id": insp.product_id,
                "sha256": hashlib.sha256(data).hexdigest(), "labels": len(rows), "size": [w, h],
            })
            if progress:
                progress((i + 1) / max(len(images), 1) * 0.8, f"Exported {i + 1}/{len(images)} verified images")
        db.commit()  # persists newly assigned sticky splits

        with open(os.path.join(work, "data.yaml"), "w", encoding="utf-8") as f:
            f.write("path: .\ntrain: images/train\nval: images/val\ntest: images/test\n")
            f.write(f"nc: {len(classes)}\nnames: {json.dumps(classes)}\n")
        manifest_doc = {
            "dataset_version": ds.version, "organization_id": ds.organization_id, "classes": classes,
            "created_at": datetime.now(timezone.utc).isoformat(), "split_counts": split_counts,
            "class_counts": class_counts, "label_policy": "CONFIRMED/RELABELED detections and reviewer-drawn boxes on VERIFIED images",
            "images": manifest,
        }
        manifest_bytes = json.dumps(manifest_doc, indent=2).encode()
        with open(os.path.join(work, "manifest.json"), "wb") as f:
            f.write(manifest_bytes)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(work):
                for name in files:
                    full = os.path.join(root, name)
                    zf.write(full, os.path.relpath(full, work))
        ds.storage_key = storage_service.put_object(f"datasets/{ds.organization_id}/v{ds.version}/dataset.zip",
                                                    buffer.getvalue(), "application/zip")
        ds.image_count = len(manifest)
        ds.label_count = label_total
        ds.class_counts = class_counts
        ds.split_counts = split_counts
        ds.manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        ds.status = "READY"
        log_event(db, ds.organization_id, "DATASET_BUILT",
                  f"Dataset v{ds.version}: {len(manifest)} verified images, {label_total} labels "
                  f"(train {split_counts['train']} / val {split_counts['val']} / test {split_counts['test']})",
                  payload={"dataset_version_id": ds.id})
        db.commit()
        return ds
    except Exception:
        db.rollback()
        ds.status = "FAILED"
        db.commit()
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def extract_dataset(ds: DatasetVersion) -> str:
    """Unpacks a dataset version into a temporary folder; caller removes it."""
    target = tempfile.mkdtemp(prefix=f"pm_ds_v{ds.version}_")
    with zipfile.ZipFile(storage_service.local_path(ds.storage_key)) as zf:
        zf.extractall(target)
    return target


@job_service.register(DATASET_JOB)
def run_dataset_job(db: Session, job, progress) -> Dict[str, Any]:
    ds = db.get(DatasetVersion, (job.payload or {})["dataset_version_id"])
    ds.job_id = job.id
    db.commit()
    build_dataset(db, ds, progress)
    return {"dataset_version_id": ds.id, "version": ds.version, "image_count": ds.image_count,
            "label_count": ds.label_count, "split_counts": ds.split_counts}
