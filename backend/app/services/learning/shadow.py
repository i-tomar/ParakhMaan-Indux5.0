"""
Shadow mode: a candidate model sees the same live images as the active model but never affects outcomes.

For every analysed image the shadow model's own predictions are stored next to the active model's
model-only predictions. Agreement is available immediately; once images are human-verified, both are
also scored against the verified labels, so a promotion decision rests on real production traffic.
"""
import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.all_models import DefectDetection, Image, Inspection, ModelVersion, ShadowPrediction
from app.services.defect_detection_service import _iou
from app.services.learning.datasets import LABEL_STATUSES
from app.services.learning.registry import registry

log = logging.getLogger(__name__)
MATCH_IOU = 0.3


def _slim(dets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"defect_type": d["defect_type"], "confidence": round(float(d["confidence"]), 3),
             "bbox": [round(float(v), 1) for v in d["bbox"]]} for d in dets]


def compare(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Greedy class-aware matching of two prediction sets (a = reference)."""
    used = set()
    matched = 0
    for p in sorted(b, key=lambda d: -d["confidence"]):
        best, best_iou = None, MATCH_IOU
        for i, r in enumerate(a):
            if i in used or r["defect_type"] != p["defect_type"]:
                continue
            iou = _iou(r["bbox"], p["bbox"])
            if iou >= best_iou:
                best, best_iou = i, iou
        if best is not None:
            used.add(best)
            matched += 1
    only_a, only_b = len(a) - matched, len(b) - matched
    total = matched + only_a + only_b
    return {"matched": matched, "champion_only": only_a, "shadow_only": only_b,
            "agreement": round(matched / total, 3) if total else 1.0}


def record_shadow(db: Session, insp: Inspection, image: Image, frame, champion_detections: List[Dict[str, Any]],
                  champion_version: Optional[ModelVersion] = None) -> Optional[ShadowPrediction]:
    shadow = registry.shadow(db, insp.organization_id)
    if not shadow or not shadow.onnx_key:
        return None
    try:
        det = registry.detector_for_version(shadow, backend="onnx")
        started = time.perf_counter()
        scan = det.detect(frame)
        latency = (time.perf_counter() - started) * 1000
    except Exception as e:  # shadow failures must never affect production inspection
        log.warning("Shadow inference failed: %s", e)
        return None
    shadow_dets = _slim(scan["detections"])
    champion_model = _slim([d for d in champion_detections if "ONNX" in str(d.get("detector", ""))])
    row = ShadowPrediction(organization_id=insp.organization_id, model_version_id=shadow.id,
                           champion_version_id=champion_version.id if champion_version else None,
                           image_id=image.id, inspection_id=insp.id, detections=shadow_dets,
                           champion_detections=champion_model, agreement=compare(champion_model, shadow_dets),
                           latency_ms=round(latency, 1))
    db.add(row)
    db.commit()
    return row


def _prf(tp: int, fp: int, fn: int) -> Dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}


def shadow_stats(db: Session, mv: ModelVersion) -> Dict[str, Any]:
    rows = db.query(ShadowPrediction).filter(ShadowPrediction.model_version_id == mv.id).all()
    if not rows:
        return {"images": 0, "agreement": None, "verified_images": 0, "shadow": None, "champion": None}
    agreement = sum(r.agreement.get("agreement", 0) for r in rows) / len(rows)
    latency = [r.latency_ms for r in rows if r.latency_ms]

    image_ids = [r.image_id for r in rows]
    verified = {i.id for i in db.query(Image).filter(Image.id.in_(image_ids), Image.review_status == "VERIFIED")}
    truth: Dict[str, List[Dict[str, Any]]] = {i: [] for i in verified}
    if verified:
        for d in db.query(DefectDetection).filter(DefectDetection.image_id.in_(verified),
                                                  DefectDetection.reviewer_status.in_(LABEL_STATUSES)):
            truth[d.image_id].append({"defect_type": d.defect_type, "bbox": d.bbox, "confidence": 1.0})
    totals = {"shadow": [0, 0, 0], "champion": [0, 0, 0]}
    for r in rows:
        if r.image_id not in verified:
            continue
        gt = truth[r.image_id]
        for key, preds in (("shadow", r.detections), ("champion", r.champion_detections)):
            c = compare(gt, preds or [])
            totals[key][0] += c["matched"]
            totals[key][1] += c["shadow_only"]   # predictions without a matching label
            totals[key][2] += c["champion_only"]  # labels the predictions missed
    return {
        "images": len(rows),
        "agreement": round(agreement, 3),
        "avg_latency_ms": round(sum(latency) / len(latency), 1) if latency else None,
        "verified_images": len(verified),
        "shadow": _prf(*totals["shadow"]) if verified else None,
        "champion": _prf(*totals["champion"]) if verified else None,
    }
