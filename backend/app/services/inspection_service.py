"""Turns one engine result into persistent records. Every source uses this one path, so an image
upload, a video and a conveyor stream all produce the same structured log."""
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.all_models import DefectDetection
from app.models.industrial import Batch, CalibrationProfile, GoldenReference, Machine, Product, ProductionLine, ProductionUnit
from app.services.inference.engine import engine
from app.services.line.decision import DecisionPolicy, decide
from app.services.metrology.calibration import Calibration
from app.services.metrology.measure import inspect_dimensions, segment_part

_sequence_lock = threading.Lock()


def shift_for(moment: datetime) -> str:
    """Three eight-hour shifts: A 06-14, B 14-22, C 22-06."""
    hour = moment.hour
    return "A" if 6 <= hour < 14 else ("B" if 14 <= hour < 22 else "C")


def unit_code(moment: datetime) -> str:
    return f"U-{moment:%y%m%d}-{uuid.uuid4().hex[:8].upper()}"


def active_reference(db: Session, product: Optional[Product]) -> Optional[np.ndarray]:
    if product is None:
        return None
    ref = db.query(GoldenReference).filter(GoldenReference.product_id == product.id, GoldenReference.is_active.is_(True)).first()
    return cv2.imread(ref.file_path) if ref and os.path.exists(ref.file_path) else None


def calibration_for(db: Session, product: Optional[Product]) -> Optional[Calibration]:
    if product is None or not product.calibration_id:
        return None
    row = db.get(CalibrationProfile, product.calibration_id)
    return Calibration.from_dict(row.data) if row else None


def run_inspection(
    db: Session, image: np.ndarray, product: Optional[Product], reference: Optional[np.ndarray] = None,
    want_heatmap: bool = True,
) -> Dict[str, Any]:
    """Models, geometry and the decision for one image. Stores nothing."""
    reference = reference if reference is not None else active_reference(db, product)
    scan = engine.inspect(image, product.key if product else None, reference, want_heatmap=want_heatmap)
    if product is None and scan.get("product_key"):
        product = db.query(Product).filter(Product.key == scan["product_key"]).first()

    calibration = calibration_for(db, product)
    dimensional = None
    if calibration is not None:
        reference_contour = segment_part(reference) if reference is not None else None
        dimensional = inspect_dimensions(image, calibration, (product.dimension_spec if product else None), reference_contour)
        for d in scan["detections"]:
            m = d["metrics"]
            if m.get("length_px") is not None:
                d["length_mm"] = round(m["length_px"] * calibration.mm_per_px, 2)
                d["width_mm"] = round(m["width_px"] * calibration.mm_per_px, 2)
            if m.get("mask_area_ratio") is not None:
                w, h = scan["image_size"]
                d["area_mm2"] = round(m["mask_area_ratio"] * w * h * calibration.mm_per_px ** 2, 2)

    policy = DecisionPolicy.from_dict(product.decision_policy if product else None)
    verdict = decide(scan["detections"], dimensional.get("status") if dimensional else None, scan["exposure_ok"], policy)
    return {**scan, **verdict, "dimensional": dimensional, "product_id": product.id if product else None}


def model_label(det: Dict[str, Any], versions: Dict[str, Optional[str]]) -> Optional[str]:
    detector = det.get("detector", "")
    if detector.startswith("YOLO"):
        return versions.get("segmentation")
    if detector == "ANOMALY":
        return versions.get("anomaly")
    return "opencv-classical"


def record_unit(
    db: Session,
    result: Dict[str, Any],
    image: np.ndarray,
    *,
    batch: Optional[Batch] = None,
    machine: Optional[Machine] = None,
    line: Optional[ProductionLine] = None,
    source: str = "UPLOAD",
    is_synthetic: bool = False,
    inspection_id: Optional[str] = None,
    image_id: Optional[str] = None,
    image_path: Optional[str] = None,
    when: Optional[datetime] = None,
    shift: Optional[str] = None,
    store_image: bool = True,
) -> ProductionUnit:
    moment = when or datetime.now(timezone.utc)
    code = unit_code(moment)
    folder = os.path.join(settings.STORAGE_DIR, "units", f"{moment:%Y%m%d}")
    heatmap_path = None
    if store_image:
        os.makedirs(folder, exist_ok=True)
        if image_path is None:
            image_path = os.path.join(folder, f"{code}.jpg")
            cv2.imwrite(image_path, image, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if result.get("heatmap_jpeg"):
            heatmap_path = os.path.join(folder, f"{code}_heatmap.jpg")
            with open(heatmap_path, "wb") as f:
                f.write(result["heatmap_jpeg"])

    unit = ProductionUnit(
        unit_code=code, product_id=result.get("product_id"), batch_id=batch.id if batch else None,
        machine_id=machine.id if machine else None, line_id=line.id if line else None,
        shift=shift or shift_for(moment), source=source, is_synthetic=is_synthetic, inspection_id=inspection_id,
        image_path=image_path, heatmap_path=heatmap_path, decision=result["decision"],
        decision_reasons=result["reasons"], anomaly_score=(result.get("anomaly") or {}).get("normalised"),
        dimensional=result.get("dimensional"), model_versions=result["model_versions"], streams=result["streams"],
        latency_ms=result["latency_ms"], inspected_at=moment,
    )
    db.add(unit)
    db.flush()

    rows: List[DefectDetection] = []
    if inspection_id:
        for det in result["detections"]:
            row = DefectDetection(
                inspection_id=inspection_id, image_id=image_id, unit_id=unit.id, defect_type=det["defect_type"],
                severity=det["severity"], confidence=det["confidence"], bbox=det["bbox"], area_ratio=det.get("area_ratio", 0.0),
                detector=det.get("detector", "OPENCV"), metrics=det.get("metrics", {}), reviewer_status="PENDING",
                model_version=model_label(det, result["model_versions"]), length_mm=det.get("length_mm"),
                width_mm=det.get("width_mm"), area_mm2=det.get("area_mm2"), created_at=moment,
            )
            db.add(row)
            rows.append(row)
    db.commit()
    unit.detection_rows = rows  # type: ignore[attr-defined]
    return unit
