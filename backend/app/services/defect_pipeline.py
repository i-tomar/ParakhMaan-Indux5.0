"""
Defect-inspection domain logic shared by the API, the background worker and edge ingestion.
Images are referenced by storage keys (see storage_service); OpenCV reads them via local_path().
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import cv2
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.all_models import (
    AuditEvent, DefectDetection, EdgeDevice, Image as ImageModel, Inspection, Product, Station, User
)
from app.schemas.all_schemas import DefectDetectionResponse, DefectInspectionDetailResponse, ImageResponse
from app.services import job_service
from app.services.defect_analytics_service import build_defect_analytics
from app.services.defect_detection_service import compute_outcome, defect_detector, synthesize_surface_sample
from app.services.heatmap_service import heatmap_service
from app.services.image_quality import image_quality_analyzer
from app.services.learning.registry import registry
from app.services.learning.sampler import route_image
from app.services.learning.shadow import record_shadow
from app.services.pdf_report_service import pdf_report_service
from app.services.storage_service import storage_service

DEFECT_MODE = "DEFECT"
REFERENCE_SURFACE = "REFERENCE"
VIDEO_FRAME_SURFACE = "VIDEO_FRAME"
MAX_VIDEO_KEYFRAMES = 24
VIDEO_JOB = "VIDEO_ANALYSIS"


# ---------------------------------------------------------------- small helpers
def audit(db: Session, inspection_id: str, user_id: Optional[str], event_type: str, description: str,
          state_after: Optional[dict] = None) -> None:
    db.add(AuditEvent(inspection_id=inspection_id, user_id=user_id, event_type=event_type,
                      description=description, state_after=state_after))


def current_shift(now: Optional[datetime] = None) -> str:
    hour = (now or datetime.now()).hour
    return "A" if 6 <= hour < 14 else ("B" if 14 <= hour < 22 else "C")


def next_inspection_number(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = db.query(Inspection).filter(Inspection.inspection_mode == DEFECT_MODE).count() + 1
    while db.query(Inspection).filter(Inspection.inspection_number == f"DEF-{year}-{count:04d}").first():
        count += 1
    return f"DEF-{year}-{count:04d}"


def station_label(station: Optional[Station]) -> Optional[str]:
    if not station:
        return None
    line = station.line
    plant = line.plant if line else None
    return " / ".join(p for p in (plant.name if plant else None, line.name if line else None, station.name) if p)


def resolve_org_refs(db: Session, organization_id: str, product_id: Optional[str], station_id: Optional[str]):
    """Validates that product / station belong to the caller's organisation."""
    product = station = None
    if product_id:
        product = db.query(Product).filter(Product.id == product_id, Product.organization_id == organization_id).first()
        if not product:
            raise HTTPException(status_code=400, detail="Unknown product")
    if station_id:
        station = db.get(Station, station_id)
        if not station or not station.line or station.line.plant.organization_id != organization_id:
            raise HTTPException(status_code=400, detail="Unknown station")
    return product, station


def create_inspection(
    db: Session, organization_id: str, user: Optional[User], *, product_id: Optional[str] = None,
    station_id: Optional[str] = None, shift: Optional[str] = None, batch_code: Optional[str] = None,
    product_name: Optional[str] = None, category: str = "GENERAL_MANUFACTURED", location: Optional[str] = None,
    notes: Optional[str] = None, source: str = "WEB", external_ref: Optional[str] = None,
    created_at: Optional[datetime] = None, number: Optional[str] = None,
) -> Inspection:
    product, station = resolve_org_refs(db, organization_id, product_id, station_id)
    insp = Inspection(
        inspection_number=number or next_inspection_number(db),
        inspection_mode=DEFECT_MODE,
        organization_id=organization_id,
        product_id=product.id if product else None,
        station_id=station.id if station else None,
        shift=shift or current_shift(),
        batch_code=batch_code,
        brand_name=batch_code,
        product_name=(product.name if product else product_name) or "Unnamed Product",
        category=(product.family if product and product.family else category),
        location=station_label(station) or location,
        notes=notes,
        source=source,
        external_ref=external_ref,
        created_by_id=user.id if user else None,
        status="DRAFT",
        overall_outcome="PENDING",
    )
    if created_at:
        insp.created_at = insp.updated_at = created_at
    db.add(insp)
    db.commit()
    db.refresh(insp)
    who = user.full_name if user else ("edge device" if source == "EDGE" else "system")
    audit(db, insp.id, user.id if user else None, "INSPECTION_CREATED",
          f"Defect inspection {insp.inspection_number} created by {who}",
          {"mode": DEFECT_MODE, "source": source, "station": insp.location})
    db.commit()
    db.refresh(insp)
    return insp


def detection_dict(d: DefectDetection) -> Dict[str, Any]:
    return {
        "id": d.id, "inspection_id": d.inspection_id, "image_id": d.image_id, "defect_type": d.defect_type,
        "severity": d.severity, "confidence": d.confidence, "bbox": d.bbox or [], "area_ratio": d.area_ratio,
        "detector": d.detector, "model_version": d.model_version, "metrics": d.metrics or {},
        "frame_index": d.frame_index, "frame_timestamp_ms": d.frame_timestamp_ms,
        "reviewer_status": d.reviewer_status, "reviewer_note": d.reviewer_note, "created_at": d.created_at,
    }


def reference_path(insp: Inspection) -> Optional[str]:
    for img in insp.images:
        if img.surface_type == REFERENCE_SURFACE and storage_service.exists(img.file_path):
            return storage_service.local_path(img.file_path)
    return None


def scan_meta(scan: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "latency_ms": scan["latency_ms"], "fps": scan["fps"], "backend": scan["backend"],
        "image_size": scan["image_size"], "product_mask_used": scan["product_mask_used"],
        "reference_used": scan["reference_used"], "mean_brightness": scan["mean_brightness"],
        "exposure_ok": scan["exposure_ok"], "detection_count": len(scan["detections"]), "outcome": scan["outcome"],
        "model_version": scan.get("model_version"),
    }


def store_detections(
    db: Session, insp: Inspection, image: ImageModel, detections: List[Dict[str, Any]],
    frame_index: Optional[int] = None, frame_ts: Optional[float] = None, created_at: Optional[datetime] = None,
    model_version: Optional[str] = None,
) -> List[DefectDetection]:
    rows = []
    for det in detections:
        detector = det.get("detector", "OPENCV")
        row = DefectDetection(
            inspection_id=insp.id, image_id=image.id, defect_type=det["defect_type"], severity=det["severity"],
            confidence=det["confidence"], bbox=det["bbox"], area_ratio=det.get("area_ratio", 0.0),
            detector=detector,
            model_version=det.get("model_version") or (model_version if "ONNX" in detector else None),
            metrics=det.get("metrics", {}), frame_index=frame_index, frame_timestamp_ms=frame_ts,
            reviewer_status="PENDING",
        )
        if created_at:
            row.created_at = created_at
        db.add(row)
        rows.append(row)
    return rows


def refresh_outcome(db: Session, insp: Inspection) -> str:
    dets = [detection_dict(d) for d in insp.defect_detections]
    analysed = [img for img in insp.images if img.surface_type != REFERENCE_SURFACE]
    # The label-oriented blur / blank checks read smooth, uniform (i.e. defect-free) surfaces as
    # "blurry" or "empty", so only frames too dark or saturated to inspect force a review.
    quality_issue = any(
        not (img.quality_metadata or {}).get("defect_scan", {}).get("exposure_ok", True) for img in analysed
    )
    insp.overall_outcome = compute_outcome(dets, quality_issue=quality_issue) if analysed else "PENDING"
    if insp.status != "FINALIZED":
        insp.status = "ANALYZED" if insp.overall_outcome == "PASS" else ("DRAFT" if not analysed else "REVIEW")
    insp.report_path = None
    db.commit()
    return insp.overall_outcome


def describe(detections: List[Dict[str, Any]]) -> str:
    if not detections:
        return "no defects"
    counts: Dict[str, int] = {}
    for d in detections:
        counts[d["defect_type"]] = counts.get(d["defect_type"], 0) + 1
    return ", ".join(f"{n} {t.lower().replace('_', ' ')}" for t, n in counts.items())


def _with_model_version(scan: Dict[str, Any], detector=None) -> Dict[str, Any]:
    detector = detector or defect_detector
    scan["model_version"] = detector.model_version if "ONNX" in scan["backend"] else None
    return scan


def _learn_from(db: Session, insp: Inspection, image: ImageModel, frame, scan: Dict[str, Any]) -> None:
    """Feeds the learning loop: shadow comparison and smart review sampling. Never blocks inspection."""
    try:
        record_shadow(db, insp, image, frame, scan["detections"], registry.active(db, insp.organization_id))
        route_image(db, insp, image, [{**d, "reviewer_status": "PENDING"} for d in scan["detections"]], scan)
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger(__name__).warning("Learning-loop hooks failed for image %s: %s", image.id, e)


# ---------------------------------------------------------------- analysis
def analyze_and_store(
    db: Session, insp: Inspection, key: str, original_filename: str, surface_type: str,
    user_id: Optional[str], event_type: str,
) -> Dict[str, Any]:
    path = storage_service.local_path(key)
    quality = image_quality_analyzer.analyze(path)
    frame = cv2.imread(path)
    if frame is None:
        raise HTTPException(status_code=400, detail="Unable to decode image")
    detector = registry.detector_for(db, insp.organization_id)
    ref_path = reference_path(insp)
    scan = _with_model_version(detector.detect(frame, cv2.imread(ref_path) if ref_path else None), detector)

    image = ImageModel(
        inspection_id=insp.id, surface_type=surface_type, file_path=key, original_filename=original_filename,
        quality_score=quality["quality_score"], quality_metadata={**quality, "defect_scan": scan_meta(scan)},
        ocr_raw_data=[],
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    rows = store_detections(db, insp, image, scan["detections"], model_version=scan["model_version"])
    audit(db, insp.id, user_id, event_type,
          f"{surface_type} analysed in {scan['latency_ms']} ms ({scan['backend']}): {describe(scan['detections'])}",
          {"image_id": image.id, "detections": len(rows), "latency_ms": scan["latency_ms"]})
    db.commit()
    db.refresh(insp)
    outcome = refresh_outcome(db, insp)
    _learn_from(db, insp, image, frame, scan)
    return {
        "image": ImageResponse.model_validate(image),
        "detections": [DefectDetectionResponse.model_validate(r) for r in rows],
        "scan": scan_meta(scan),
        "overall_outcome": outcome,
    }


@job_service.register(VIDEO_JOB)
def run_video_job(db: Session, job, progress) -> Dict[str, Any]:
    p = job.payload or {}
    insp = db.get(Inspection, job.inspection_id)
    if not insp:
        raise ValueError("Inspection no longer exists")
    try:
        return process_video(db, insp, p["video_key"], p.get("video_name", "video.mp4"),
                             float(p.get("sample_fps", 2.0)), int(p.get("max_frames", 40)),
                             job.created_by_id, progress)
    finally:
        storage_service.delete(p.get("video_key"))


def process_video(db: Session, insp: Inspection, video_key: str, video_name: str, sample_fps: float,
                  max_frames: int, user_id: Optional[str], progress=None) -> Dict[str, Any]:
    cap = cv2.VideoCapture(storage_service.local_path(video_key))
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Unable to decode video. Use MP4 (H.264), AVI, or MOV.")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(src_fps / max(0.1, sample_fps))))
    expected = min(max_frames, max(1, total_frames // step)) if total_frames else max_frames
    ref_path = reference_path(insp)
    ref = cv2.imread(ref_path) if ref_path else None
    detector = registry.detector_for(db, insp.organization_id)

    sampled = with_defects = keyframes = 0
    latencies: List[float] = []
    type_counts: Dict[str, int] = {}
    first_frame = None
    frame_idx = 0
    started = datetime.now(timezone.utc)
    while sampled < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % step == 0:
            sampled += 1
            if first_frame is None:
                first_frame = frame
            scan = _with_model_version(detector.detect(frame, ref, max_side=960), detector)
            latencies.append(scan["latency_ms"])
            if scan["detections"]:
                with_defects += 1
                for d in scan["detections"]:
                    type_counts[d["defect_type"]] = type_counts.get(d["defect_type"], 0) + 1
                if keyframes < MAX_VIDEO_KEYFRAMES:
                    ts = round(frame_idx / src_fps * 1000.0, 1)
                    image = _store_frame(db, insp, frame, frame_idx, video_name,
                                         {**scan_meta(scan), "frame_index": frame_idx, "timestamp_ms": ts})
                    store_detections(db, insp, image, scan["detections"], frame_index=frame_idx, frame_ts=ts,
                                     model_version=scan["model_version"])
                    db.commit()
                    _learn_from(db, insp, image, frame, scan)
                    keyframes += 1
            if progress:
                progress(sampled / expected * 0.95, f"Analysed {sampled}/{expected} frames, {with_defects} with defects")
        frame_idx += 1
    cap.release()

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None
    if sampled and not keyframes and first_frame is not None:
        # Clean video: keep one representative frame so the inspection has visual evidence.
        _store_frame(db, insp, first_frame, 0, video_name,
                     {"latency_ms": avg_latency, "frame_index": 0, "detection_count": 0, "exposure_ok": True})
        db.commit()
    summary = {
        "video": video_name, "source_fps": round(src_fps, 2), "total_frames": total_frames,
        "frames_sampled": sampled, "frames_with_defects": with_defects, "keyframes_saved": keyframes,
        "avg_latency_ms": avg_latency, "processing_fps": round(sampled / elapsed, 2) if elapsed > 0 else None,
        "detections_by_type": type_counts,
    }
    audit(db, insp.id, user_id, "DEFECT_VIDEO_SCAN",
          f"Video '{video_name}': {sampled} frames sampled, {with_defects} with defects, avg {avg_latency} ms/frame",
          summary)
    db.commit()
    db.refresh(insp)
    summary["overall_outcome"] = refresh_outcome(db, insp)
    summary["inspection_id"] = insp.id
    return summary


def _store_frame(db: Session, insp: Inspection, frame, frame_idx: int, video_name: str, meta: Dict[str, Any]) -> ImageModel:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    key = storage_service.save_bytes(buf.tobytes(), insp.id, f"frame_{frame_idx:06d}.jpg")
    quality = image_quality_analyzer.analyze(storage_service.local_path(key))
    image = ImageModel(
        inspection_id=insp.id, surface_type=VIDEO_FRAME_SURFACE, file_path=key,
        original_filename=f"{video_name}#frame{frame_idx}", quality_score=quality["quality_score"],
        quality_metadata={**quality, "defect_scan": meta}, ocr_raw_data=[],
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


# ---------------------------------------------------------------- edge ingestion
def ingest_edge_result(db: Session, device: EdgeDevice, image_bytes: bytes, meta: Dict[str, Any]) -> Inspection:
    """
    Stores a result computed on an edge node. The edge decision is kept as reported (it is what
    happened on the line); the image is retained so the result can be reviewed and re-analysed.
    """
    local_id = str(meta.get("local_id") or "")[:100]
    external_ref = f"{device.id}:{local_id}" if local_id else None
    if external_ref:
        existing = db.query(Inspection).filter(Inspection.external_ref == external_ref).first()
        if existing:
            return existing

    captured_at = None
    if meta.get("captured_at"):
        try:
            captured_at = datetime.fromisoformat(str(meta["captured_at"]).replace("Z", "+00:00"))
        except ValueError:
            captured_at = None
    insp = create_inspection(
        db, device.organization_id, None, product_id=meta.get("product_id"), station_id=device.station_id,
        shift=meta.get("shift"), batch_code=meta.get("batch_code"), product_name=meta.get("product_name"),
        source="EDGE", external_ref=external_ref, created_at=captured_at,
        notes=f"Captured by edge device '{device.name}'",
    )
    key = storage_service.save_bytes(image_bytes, insp.id, "edge_capture.jpg")
    path = storage_service.local_path(key)
    quality = image_quality_analyzer.analyze(path)
    scan = meta.get("scan") or {}
    image = ImageModel(
        inspection_id=insp.id, surface_type="EDGE_CAPTURE", file_path=key, original_filename="edge_capture.jpg",
        quality_score=quality["quality_score"],
        quality_metadata={**quality, "defect_scan": {**scan, "edge_device": device.name}}, ocr_raw_data=[],
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    detections = [d for d in meta.get("detections", []) if isinstance(d, dict) and d.get("defect_type") and d.get("bbox")]
    store_detections(db, insp, image, detections, model_version=scan.get("model_version"),
                     created_at=captured_at)
    audit(db, insp.id, None, "EDGE_INGEST",
          f"Result from edge device '{device.name}': {describe(detections)} "
          f"({scan.get('latency_ms', '?')} ms on device)",
          {"device_id": device.id, "local_id": local_id})
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(insp)
    refresh_outcome(db, insp)
    frame = cv2.imread(path)
    if frame is not None:
        _learn_from(db, insp, image, frame, {**scan, "detections": detections})
    return insp


# ---------------------------------------------------------------- detail / report / samples
def build_detail(insp: Inspection) -> Dict[str, Any]:
    detail = DefectInspectionDetailResponse.model_validate(insp).model_dump()
    detail["station_name"] = station_label(insp.station)
    analytics = build_defect_analytics(
        inspections=[{"id": insp.id, "product_name": insp.product_name, "overall_outcome": insp.overall_outcome,
                      "created_at": insp.created_at}],
        detections=[detection_dict(d) for d in insp.defect_detections],
        days=1,
    )
    detail["root_causes"] = analytics["root_causes"]
    return detail


def generate_report(db: Session, insp: Inspection, inspector_name: Optional[str] = None) -> str:
    dets = [detection_dict(d) for d in insp.defect_detections]
    overlay_dir = os.path.join(settings.REPORTS_DIR, "defect_overlays", insp.id)
    overlay_paths = []
    for img in insp.images:
        if img.surface_type == REFERENCE_SURFACE or not storage_service.exists(img.file_path):
            continue
        img_dets = [d for d in dets if d["image_id"] == img.id]
        path = heatmap_service.save_defect_overlay(storage_service.local_path(img.file_path), img_dets,
                                                   os.path.join(overlay_dir, f"{img.id}.jpg"))
        if path:
            overlay_paths.append(path)
    backends = {(img.quality_metadata or {}).get("defect_scan", {}).get("backend") for img in insp.images}
    backends.discard(None)
    detail = build_detail(insp)
    report_path = pdf_report_service.generate_defect_report({
        "inspection_number": insp.inspection_number, "product_name": insp.product_name,
        "brand_name": insp.batch_code or insp.brand_name, "category": insp.category,
        "location": detail["station_name"] or insp.location, "overall_outcome": insp.overall_outcome,
        "created_at": insp.created_at, "final_remarks": insp.final_remarks,
        "inspector_name": inspector_name or (insp.creator.full_name if insp.creator else None),
        "defect_detections": dets, "overlay_paths": overlay_paths, "root_causes": detail["root_causes"],
        "detector_backend": ", ".join(sorted(backends)) or "OPENCV",
    })
    insp.report_path = report_path
    db.commit()
    return report_path


def save_training_sample(det: DefectDetection, label: str, verdict: str) -> Optional[str]:
    """Stores a reviewed crop + manifest line so confirmed/rejected samples can be used for retraining."""
    if not det.image or not storage_service.exists(det.image.file_path) or len(det.bbox or []) != 4:
        return None
    img = cv2.imread(storage_service.local_path(det.image.file_path))
    if img is None:
        return None
    h, w = img.shape[:2]
    x1, y1, x2, y2 = det.bbox
    pad_x, pad_y = (x2 - x1) * 0.15, (y2 - y1) * 0.15
    crop = img[max(0, int(y1 - pad_y)):min(h, int(y2 + pad_y)), max(0, int(x1 - pad_x)):min(w, int(x2 + pad_x))]
    if crop.size == 0:
        return None
    folder = os.path.join(settings.DEFECT_SAMPLES_DIR, label if verdict != "REJECTED" else "_false_positive")
    os.makedirs(folder, exist_ok=True)
    crop_path = os.path.join(folder, f"{det.id}.jpg")
    cv2.imwrite(crop_path, crop)
    with open(os.path.join(settings.DEFECT_SAMPLES_DIR, "manifest.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "detection_id": det.id, "inspection_id": det.inspection_id, "image_key": det.image.file_path,
            "image_size": [w, h], "bbox": det.bbox, "label": label, "verdict": verdict,
            "model_version": det.model_version, "crop_path": crop_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")
    return crop_path


# ---------------------------------------------------------------- demo data
DEMO_SAMPLES = [
    {"number": "DEF-DEMO-0001", "sku": "CRS-PANEL-01", "station": ("Press Line 2", "Final QC"), "batch": "LOT-A17",
     "defects": ["SCRATCH", "CRACK"], "kwargs": {}, "days_ago": 5},
    {"number": "DEF-DEMO-0002", "sku": "ALU-COVER-04", "station": ("Finishing Line 1", "Coating QC"), "batch": "LOT-B04",
     "defects": ["DENT", "DISCOLOURATION"], "kwargs": {}, "days_ago": 3},
    {"number": "DEF-DEMO-0003", "sku": "CRS-PANEL-01", "station": ("Press Line 2", "Final QC"), "batch": "LOT-A18",
     "defects": [], "kwargs": {}, "days_ago": 2},
    {"number": "DEF-DEMO-0004", "sku": "BRKT-C11", "station": ("CNC Cell 3", "Dimensional Check"), "batch": "LOT-C11",
     "defects": [], "kwargs": {"product_on_background": True, "notch": True}, "days_ago": 1},
    {"number": "DEF-DEMO-0005", "sku": "CRS-PANEL-01", "station": ("Press Line 2", "Post-Press Inspection"),
     "batch": "LOT-A19", "defects": ["SCRATCH"], "kwargs": {}, "days_ago": 0},
]


def seed_defect_demo_data(db: Session, user: User) -> Dict[str, Any]:
    from app.models.all_models import ProductionLine

    if db.query(Inspection).filter(Inspection.inspection_number.like("DEF-DEMO-%")).first():
        return {"message": "Defect demo data already seeded"}
    org_id = user.organization_id
    now = datetime.now(timezone.utc)
    created = []
    for idx, sample in enumerate(DEMO_SAMPLES):
        product = db.query(Product).filter(Product.organization_id == org_id, Product.sku == sample["sku"]).first()
        line_name, station_name = sample["station"]
        station = (
            db.query(Station).join(ProductionLine, ProductionLine.id == Station.line_id)
            .filter(ProductionLine.name == line_name, Station.name == station_name).first()
        )
        when = now - timedelta(days=sample["days_ago"])
        insp = create_inspection(
            db, org_id, user, product_id=product.id if product else None, station_id=station.id if station else None,
            batch_code=sample["batch"], product_name=sample["sku"], notes="Synthetic demo sample",
            created_at=when, number=sample["number"], shift=current_shift(when),
        )
        img = synthesize_surface_sample(sample["defects"], seed=11 + idx, **sample["kwargs"])
        key = storage_service.save_bytes(cv2.imencode(".jpg", img)[1].tobytes(), insp.id, f"{sample['number']}.jpg")
        path = storage_service.local_path(key)
        quality = image_quality_analyzer.analyze(path)
        detector = registry.detector_for(db, org_id)
        scan = _with_model_version(detector.detect_file(path), detector)
        image = ImageModel(
            inspection_id=insp.id, surface_type="SURFACE", file_path=key, original_filename=f"{sample['number']}.jpg",
            quality_score=quality["quality_score"], quality_metadata={**quality, "defect_scan": scan_meta(scan)},
            ocr_raw_data=[], created_at=when,
        )
        db.add(image)
        db.commit()
        db.refresh(image)
        store_detections(db, insp, image, scan["detections"], created_at=when, model_version=scan["model_version"])
        audit(db, insp.id, user.id, "DEFECT_SCAN_COMPLETED",
              f"SURFACE analysed in {scan['latency_ms']} ms ({scan['backend']}): {describe(scan['detections'])}")
        db.commit()
        db.refresh(insp)
        refresh_outcome(db, insp)
        created.append(insp.inspection_number)
    return {"message": "Defect demo data seeded", "inspections": created}
