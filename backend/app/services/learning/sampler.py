"""
Smart sampler (active learning): decides which analysed images a person should review.

Reasons, each adding to the task priority:
  UNCERTAIN     a detection's confidence is in the uncertain band
  DISAGREEMENT  the model and the OpenCV engine disagree on a defect class both can detect
  UNKNOWN_CLASS a detection whose type the model's taxonomy does not cover
  QUALITY       the frame was too dark / bright to trust
  DRIFT         the station's input distribution has shifted (see drift.py)
  AUDIT         a random share of PASS images, so missed defects (false negatives) are found too —
                without this the loop would only ever learn from what the model already flags
"""
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.all_models import Image, Inspection, ReviewTask
from app.services.learning.drift import drift_cache
from app.services.learning.registry import learning_classes

NON_LEARNED_TYPES = {"DIMENSIONAL_ANOMALY"}  # handled by geometry rules, not by the model


def _unit_hash(text: str) -> float:
    """Deterministic pseudo-random number in [0, 1) so sampling decisions are reproducible."""
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16) / 0x100000000


def assess(detections: List[Dict[str, Any]], scan: Dict[str, Any], image_id: str,
           drift_status: str = "OK") -> Tuple[float, List[Dict[str, str]]]:
    known = {c.upper() for c in learning_classes()}
    active = [d for d in detections if d.get("reviewer_status", "PENDING") != "REJECTED"]
    reasons: List[Dict[str, str]] = []
    priority = 0.0

    uncertain = [d for d in active if settings.REVIEW_UNCERTAIN_LOW <= d.get("confidence", 0) < settings.REVIEW_UNCERTAIN_HIGH]
    if uncertain:
        priority += 3 + len(uncertain)
        reasons.append({"code": "UNCERTAIN", "detail": f"{len(uncertain)} detection(s) with confidence "
                        f"{settings.REVIEW_UNCERTAIN_LOW:.2f}-{settings.REVIEW_UNCERTAIN_HIGH:.2f}"})

    both_engines = "ONNX" in str(scan.get("backend", "")) and "OPENCV" in str(scan.get("backend", ""))
    if both_engines:
        single = [d for d in active if d.get("detector") in ("ONNX", "OPENCV") and d.get("defect_type") in known]
        if single:
            priority += 2
            by = sorted({f"{d['defect_type'].lower()} ({d['detector'].lower()} only)" for d in single})
            reasons.append({"code": "DISAGREEMENT", "detail": "Engines disagree: " + ", ".join(by)})

    unknown = [d for d in active if d.get("defect_type") not in known and d.get("defect_type") not in NON_LEARNED_TYPES]
    if unknown:
        priority += 2
        reasons.append({"code": "UNKNOWN_CLASS", "detail": "Outside model taxonomy: "
                        + ", ".join(sorted({d["defect_type"] for d in unknown}))})

    if scan.get("exposure_ok") is False:
        priority += 1
        reasons.append({"code": "QUALITY", "detail": "Frame too dark or too bright to trust"})

    if drift_status == "ALERT":
        priority += 2
        reasons.append({"code": "DRIFT", "detail": "Station input distribution has shifted"})

    if not active:
        rate = settings.REVIEW_DRIFT_AUDIT_RATE if drift_status in ("ALERT", "WATCH") else settings.REVIEW_AUDIT_RATE
        if _unit_hash(image_id) < rate:
            priority += 1
            reasons.append({"code": "AUDIT", "detail": f"Random audit of a clean result ({rate:.0%} sample)"})

    return round(priority, 2), reasons


def route_image(db: Session, insp: Inspection, image: Image, detections: List[Dict[str, Any]],
                scan: Dict[str, Any]) -> Optional[ReviewTask]:
    """Creates a review task for the image if the sampler finds a reason (at most one task per image)."""
    if image.review_status == "VERIFIED":
        return None
    drift_status = drift_cache.status(insp.organization_id, insp.station_id)
    priority, reasons = assess(detections, scan, image.id, drift_status)
    if not reasons:
        return None
    task = db.query(ReviewTask).filter(ReviewTask.image_id == image.id).first()
    if task:
        return task
    task = ReviewTask(organization_id=insp.organization_id, inspection_id=insp.id, image_id=image.id,
                      priority=priority, reasons=reasons, source="SAMPLER", status="OPEN")
    db.add(task)
    db.commit()
    return task
