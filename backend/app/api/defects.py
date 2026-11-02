import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import cv2
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.all_models import (
    AuditEvent, DefectDetection, Image as ImageModel, Inspection, ReviewerAction, User
)
from app.schemas.all_schemas import (
    DefectDetectionResponse, DefectFeedbackRequest, DefectFinalizeRequest, DefectFrameRequest,
    DefectInspectionCreate, DefectInspectionDetailResponse, DefectInspectionSummary, ImageResponse
)
from app.services.defect_analytics_service import build_defect_analytics
from app.services.defect_detection_service import (
    DEFECT_TYPES, compute_outcome, decode_base64_image, defect_detector, grade_severity,
    synthesize_surface_sample
)
from app.models.industrial import Product
from app.services.heatmap_service import heatmap_service
from app.services.inference.engine import engine, heatmap_data_url
from app.services.inspection_service import record_unit, run_inspection
from app.services.image_quality import image_quality_analyzer
from app.services.pdf_report_service import pdf_report_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/defects", tags=["Defect Inspection"])

DEFECT_MODE = "DEFECT"
REFERENCE_SURFACE = "REFERENCE"
VIDEO_FRAME_SURFACE = "VIDEO_FRAME"
MAX_VIDEO_KEYFRAMES = 24


# ---------------------------------------------------------------- helpers
def _get_defect_inspection(db: Session, id: str) -> Inspection:
    insp = db.query(Inspection).filter(Inspection.id == id, Inspection.inspection_mode == DEFECT_MODE).first()
    if not insp:
        raise HTTPException(status_code=404, detail="Defect inspection not found")
    return insp


def _next_inspection_number(db: Session) -> str:
    year = datetime.now(timezone.utc).year
    count = db.query(Inspection).filter(Inspection.inspection_mode == DEFECT_MODE).count() + 1
    while db.query(Inspection).filter(Inspection.inspection_number == f"DEF-{year}-{count:04d}").first():
        count += 1
    return f"DEF-{year}-{count:04d}"


def _audit(db: Session, inspection_id: str, user_id: Optional[str], event_type: str, description: str, state_after: Optional[dict] = None) -> None:
    db.add(AuditEvent(
        inspection_id=inspection_id,
        user_id=user_id,
        event_type=event_type,
        description=description,
        state_after=state_after,
    ))


def _detection_dict(d: DefectDetection) -> Dict[str, Any]:
    return {
        "id": d.id,
        "inspection_id": d.inspection_id,
        "image_id": d.image_id,
        "defect_type": d.defect_type,
        "severity": d.severity,
        "confidence": d.confidence,
        "bbox": d.bbox or [],
        "area_ratio": d.area_ratio,
        "detector": d.detector,
        "metrics": d.metrics or {},
        "frame_index": d.frame_index,
        "frame_timestamp_ms": d.frame_timestamp_ms,
        "reviewer_status": d.reviewer_status,
        "reviewer_note": d.reviewer_note,
        "created_at": d.created_at,
    }


def _reference_path(insp: Inspection) -> Optional[str]:
    for img in insp.images:
        if img.surface_type == REFERENCE_SURFACE and os.path.exists(img.file_path):
            return img.file_path
    return None


def _scan_meta(scan: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "latency_ms": scan["latency_ms"],
        "fps": scan["fps"],
        "backend": scan.get("backend") or "+".join(scan.get("streams", [])),
        "image_size": scan["image_size"],
        "product_mask_used": scan.get("product_mask_used", False),
        "reference_used": scan["reference_used"],
        "streams": scan.get("streams", []),
        "timings": scan.get("timings", {}),
        "anomaly": scan.get("anomaly"),
        "model_versions": scan.get("model_versions", {}),
        "decision": scan.get("decision"),
        "reasons": scan.get("reasons", []),
        "mean_brightness": scan["mean_brightness"],
        "exposure_ok": scan["exposure_ok"],
        "detection_count": len(scan["detections"]),
        "outcome": scan.get("outcome") or compute_outcome(scan["detections"], quality_issue=not scan["exposure_ok"]),
    }


def _store_detections(
    db: Session, insp: Inspection, image: ImageModel, detections: List[Dict[str, Any]],
    frame_index: Optional[int] = None, frame_ts: Optional[float] = None, created_at: Optional[datetime] = None
) -> List[DefectDetection]:
    rows = []
    for det in detections:
        row = DefectDetection(
            inspection_id=insp.id,
            image_id=image.id,
            defect_type=det["defect_type"],
            severity=det["severity"],
            confidence=det["confidence"],
            bbox=det["bbox"],
            area_ratio=det.get("area_ratio", 0.0),
            detector=det.get("detector", "OPENCV"),
            metrics=det.get("metrics", {}),
            frame_index=frame_index,
            frame_timestamp_ms=frame_ts,
            reviewer_status="PENDING",
        )
        if created_at:
            row.created_at = created_at
        db.add(row)
        rows.append(row)
    return rows


def _refresh_outcome(db: Session, insp: Inspection) -> str:
    dets = [_detection_dict(d) for d in insp.defect_detections]
    analysed = [img for img in insp.images if img.surface_type != REFERENCE_SURFACE]
    # The label-oriented blur / blank checks read smooth, uniform (i.e. defect-free) surfaces as
    # "blurry" or "empty", so only frames too dark or saturated to inspect force a review.
    quality_issue = any(
        not (img.quality_metadata or {}).get("defect_scan", {}).get("exposure_ok", True) for img in analysed
    )
    if not analysed:
        insp.overall_outcome = "PENDING"
    else:
        insp.overall_outcome = compute_outcome(dets, quality_issue=quality_issue)
    if insp.status != "FINALIZED":
        insp.status = "ANALYZED" if insp.overall_outcome == "PASS" else ("DRAFT" if not analysed else "REVIEW")
    insp.report_path = None
    db.commit()
    return insp.overall_outcome


def _describe(detections: List[Dict[str, Any]]) -> str:
    if not detections:
        return "no defects"
    counts: Dict[str, int] = {}
    for d in detections:
        counts[d["defect_type"]] = counts.get(d["defect_type"], 0) + 1
    return ", ".join(f"{n} {t.lower().replace('_', ' ')}" for t, n in counts.items())


def _product_for(db: Session, insp: Inspection) -> Optional[Product]:
    if not insp.product_name:
        return None
    return db.query(Product).filter((Product.name == insp.product_name) | (Product.key == insp.product_name)).first()


def _analyze_and_store(
    db: Session, insp: Inspection, file_path: str, original_filename: str, surface_type: str,
    user_id: Optional[str], event_type: str, source: str = "UPLOAD"
) -> Dict[str, Any]:
    quality = image_quality_analyzer.analyze(file_path)
    img = cv2.imread(file_path)
    if img is None:
        raise HTTPException(status_code=400, detail=f"Unable to decode image: {original_filename}")
    ref_path = _reference_path(insp)
    reference = cv2.imread(ref_path) if ref_path else None
    scan = run_inspection(db, img, _product_for(db, insp), reference)
    scan["outcome"] = compute_outcome(scan["detections"], quality_issue=not scan["exposure_ok"])

    image = ImageModel(
        inspection_id=insp.id,
        surface_type=surface_type,
        file_path=file_path,
        original_filename=original_filename,
        quality_score=quality["quality_score"],
        quality_metadata={**quality, "defect_scan": _scan_meta(scan)},
        ocr_raw_data=[],
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    unit = record_unit(db, scan, img, source=source, inspection_id=insp.id, image_id=image.id, image_path=file_path)
    rows = unit.detection_rows
    _audit(
        db, insp.id, user_id, event_type,
        f"{surface_type} analysed in {scan['latency_ms']} ms ({'+'.join(scan['streams'])}): {_describe(scan['detections'])}",
        {"image_id": image.id, "unit_id": unit.id, "detections": len(rows), "latency_ms": scan["latency_ms"]},
    )
    db.commit()
    db.refresh(insp)
    outcome = _refresh_outcome(db, insp)

    return {
        "image": ImageResponse.model_validate(image),
        "detections": [DefectDetectionResponse.model_validate(r) for r in rows],
        "scan": _scan_meta(scan),
        "overall_outcome": outcome,
        "unit_id": unit.id,
        "unit_code": unit.unit_code,
        "decision": scan["decision"],
        "reasons": scan["reasons"],
        "heatmap_data_url": heatmap_data_url(scan.get("heatmap_jpeg")),
    }


def _build_detail(insp: Inspection) -> Dict[str, Any]:
    detail = DefectInspectionDetailResponse.model_validate(insp).model_dump()
    analytics = build_defect_analytics(
        inspections=[{"id": insp.id, "product_name": insp.product_name, "overall_outcome": insp.overall_outcome, "created_at": insp.created_at}],
        detections=[_detection_dict(d) for d in insp.defect_detections],
        days=1,
    )
    detail["root_causes"] = analytics["root_causes"]
    return detail


def generate_defect_report_for(db: Session, insp: Inspection, inspector_name: Optional[str] = None) -> str:
    dets = [_detection_dict(d) for d in insp.defect_detections]
    overlay_dir = os.path.join(settings.REPORTS_DIR, "defect_overlays", insp.id)
    overlay_paths = []
    for img in insp.images:
        if img.surface_type == REFERENCE_SURFACE:
            continue
        img_dets = [d for d in dets if d["image_id"] == img.id]
        path = heatmap_service.save_defect_overlay(img.file_path, img_dets, os.path.join(overlay_dir, f"{img.id}.jpg"))
        if path:
            overlay_paths.append(path)
    backends = {(img.quality_metadata or {}).get("defect_scan", {}).get("backend") for img in insp.images}
    backends.discard(None)
    detail = _build_detail(insp)
    report_path = pdf_report_service.generate_defect_report({
        "inspection_number": insp.inspection_number,
        "product_name": insp.product_name,
        "brand_name": insp.brand_name,
        "category": insp.category,
        "location": insp.location,
        "overall_outcome": insp.overall_outcome,
        "created_at": insp.created_at,
        "final_remarks": insp.final_remarks,
        "inspector_name": inspector_name or (insp.creator.full_name if insp.creator else None),
        "defect_detections": dets,
        "overlay_paths": overlay_paths,
        "root_causes": detail["root_causes"],
        "detector_backend": ", ".join(sorted(backends)) or "OPENCV",
    })
    insp.report_path = report_path
    db.commit()
    return report_path


def _save_training_sample(det: DefectDetection, label: str, verdict: str) -> Optional[str]:
    """Stores a reviewed crop + manifest line so confirmed/rejected samples can be used for retraining."""
    if not det.image or not os.path.exists(det.image.file_path) or len(det.bbox or []) != 4:
        return None
    img = cv2.imread(det.image.file_path)
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
            "detection_id": det.id,
            "inspection_id": det.inspection_id,
            "image_path": det.image.file_path,
            "image_size": [w, h],
            "bbox": det.bbox,
            "label": label,
            "verdict": verdict,
            "crop_path": crop_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")
    return crop_path


# ---------------------------------------------------------------- inspections
@router.get("/status")
def get_detector_status():
    status = engine.status()
    legacy = defect_detector.status()
    return {**legacy, "model_loaded": status["segmentation"]["loaded"], "model_error": status["segmentation"]["error"],
            "model_classes": status["segmentation"]["classes"], "engine": status}


@router.post("/inspections", response_model=DefectInspectionDetailResponse)
def create_defect_inspection(
    req: DefectInspectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    insp = Inspection(
        inspection_number=_next_inspection_number(db),
        inspection_mode=DEFECT_MODE,
        product_name=req.product_name,
        brand_name=req.brand_name,
        category=req.category,
        location=req.location,
        notes=req.notes,
        created_by_id=current_user.id,
        status="DRAFT",
        overall_outcome="PENDING",
    )
    db.add(insp)
    db.commit()
    db.refresh(insp)
    _audit(db, insp.id, current_user.id, "INSPECTION_CREATED",
           f"Defect inspection {insp.inspection_number} created by {current_user.full_name}",
           {"mode": DEFECT_MODE, "category": insp.category})
    db.commit()
    db.refresh(insp)
    return _build_detail(insp)


@router.get("/inspections", response_model=List[DefectInspectionSummary])
def list_defect_inspections(
    outcome: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Inspection).filter(Inspection.inspection_mode == DEFECT_MODE)
    if outcome:
        query = query.filter(Inspection.overall_outcome == outcome)
    if search:
        query = query.filter(
            (Inspection.product_name.ilike(f"%{search}%")) |
            (Inspection.inspection_number.ilike(f"%{search}%")) |
            (Inspection.brand_name.ilike(f"%{search}%"))
        )
    results = []
    for insp in query.order_by(Inspection.created_at.desc()).all():
        active = [d for d in insp.defect_detections if d.reviewer_status != "REJECTED"]
        counts: Dict[str, int] = {}
        for d in active:
            counts[d.defect_type] = counts.get(d.defect_type, 0) + 1
        results.append(DefectInspectionSummary(
            id=insp.id,
            inspection_number=insp.inspection_number,
            inspection_mode=insp.inspection_mode,
            product_name=insp.product_name,
            brand_name=insp.brand_name,
            category=insp.category,
            status=insp.status,
            overall_outcome=insp.overall_outcome,
            created_by_id=insp.created_by_id,
            location=insp.location,
            notes=insp.notes,
            final_remarks=insp.final_remarks,
            report_path=insp.report_path,
            image_count=sum(1 for i in insp.images if i.surface_type != REFERENCE_SURFACE),
            created_at=insp.created_at,
            updated_at=insp.updated_at,
            defect_count=len(active),
            top_defect_type=max(counts, key=counts.get) if counts else None,
        ))
    return results


@router.get("/inspections/{id}", response_model=DefectInspectionDetailResponse)
def get_defect_inspection(id: str, db: Session = Depends(get_db)):
    return _build_detail(_get_defect_inspection(db, id))


@router.post("/inspections/{id}/reference", response_model=ImageResponse)
async def upload_reference_image(
    id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Golden (defect-free) sample used for colour, contour, and printed-design comparison."""
    insp = _get_defect_inspection(db, id)
    file_path = await storage_service.save_upload(file, id)
    if cv2.imread(file_path) is None:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="Reference file is not a readable image")

    for old in [img for img in insp.images if img.surface_type == REFERENCE_SURFACE]:
        db.delete(old)
    quality = image_quality_analyzer.analyze(file_path)
    image = ImageModel(
        inspection_id=id,
        surface_type=REFERENCE_SURFACE,
        file_path=file_path,
        original_filename=file.filename or "reference.jpg",
        quality_score=quality["quality_score"],
        quality_metadata=quality,
        ocr_raw_data=[],
    )
    db.add(image)
    _audit(db, id, current_user.id, "REFERENCE_UPLOADED", f"Golden reference sample '{image.original_filename}' attached")
    db.commit()
    db.refresh(image)
    return image


@router.post("/inspections/{id}/analyze")
async def analyze_uploaded_image(
    id: str,
    file: UploadFile = File(...),
    surface_type: str = Form("SURFACE"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    insp = _get_defect_inspection(db, id)
    file_path = await storage_service.save_upload(file, id)
    return await run_in_threadpool(
        _analyze_and_store, db, insp, file_path, file.filename or "uploaded_image.jpg",
        surface_type.upper(), current_user.id, "DEFECT_SCAN_COMPLETED"
    )


@router.post("/inspections/{id}/capture")
def analyze_camera_capture(
    id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    insp = _get_defect_inspection(db, id)
    surface_type = str(payload.get("surface_type", "SURFACE")).upper()
    img = decode_base64_image(payload.get("image_base64", ""))
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    file_path = storage_service.save_bytes(buf.tobytes(), id, f"cam_{surface_type.lower()}.jpg")
    return _analyze_and_store(
        db, insp, file_path, f"live_cam_{surface_type.lower()}.jpg", surface_type, current_user.id, "DEFECT_CAMERA_SCAN", "CAMERA"
    )


def _process_video(db: Session, insp: Inspection, video_path: str, video_name: str, sample_fps: float, max_frames: int, user_id: str) -> Dict[str, Any]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Unable to decode video. Use MP4 (H.264), AVI, or MOV.")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(src_fps / max(0.1, sample_fps))))
    ref = cv2.imread(_reference_path(insp)) if _reference_path(insp) else None
    product = _product_for(db, insp)

    sampled, with_defects, keyframes = 0, 0, 0
    latencies: List[float] = []
    type_counts: Dict[str, int] = {}
    frame_idx = 0
    started = datetime.now(timezone.utc)
    while sampled < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % step == 0:
            sampled += 1
            scan = run_inspection(db, frame, product, ref, want_heatmap=False)
            latencies.append(scan["latency_ms"])
            if scan["detections"]:
                with_defects += 1
                for d in scan["detections"]:
                    type_counts[d["defect_type"]] = type_counts.get(d["defect_type"], 0) + 1
                if keyframes < MAX_VIDEO_KEYFRAMES:
                    ts = frame_idx / src_fps * 1000.0
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    frame_path = storage_service.save_bytes(buf.tobytes(), insp.id, f"frame_{frame_idx:06d}.jpg")
                    quality = image_quality_analyzer.analyze(frame_path)
                    image = ImageModel(
                        inspection_id=insp.id,
                        surface_type=VIDEO_FRAME_SURFACE,
                        file_path=frame_path,
                        original_filename=f"{video_name}#frame{frame_idx}",
                        quality_score=quality["quality_score"],
                        quality_metadata={**quality, "defect_scan": {**_scan_meta(scan), "frame_index": frame_idx, "timestamp_ms": round(ts, 1)}},
                        ocr_raw_data=[],
                    )
                    db.add(image)
                    db.commit()
                    db.refresh(image)
                    unit = record_unit(db, scan, frame, source="VIDEO", inspection_id=insp.id, image_id=image.id, image_path=frame_path)
                    for row in unit.detection_rows:
                        row.frame_index, row.frame_timestamp_ms = frame_idx, round(ts, 1)
                    db.commit()
                    keyframes += 1
        frame_idx += 1
    cap.release()

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None
    summary = {
        "video": video_name,
        "source_fps": round(src_fps, 2),
        "total_frames": total_frames,
        "frames_sampled": sampled,
        "frames_with_defects": with_defects,
        "keyframes_saved": keyframes,
        "avg_latency_ms": avg_latency,
        "processing_fps": round(sampled / elapsed, 2) if elapsed > 0 else None,
        "detections_by_type": type_counts,
        "mode": "SAMPLED_REVIEW",
        "note": "Sampled frames of a recording. For continuous per-unit inspection use Live Inspection.",
    }
    _audit(db, insp.id, user_id, "DEFECT_VIDEO_SCAN",
           f"Video '{video_name}': {sampled} frames sampled, {with_defects} with defects, avg {avg_latency} ms/frame",
           summary)
    db.commit()
    db.refresh(insp)
    if sampled and not keyframes:
        # Clean video: keep one representative frame so the inspection has visual evidence.
        cap = cv2.VideoCapture(video_path)
        ok, frame = cap.read()
        cap.release()
        if ok:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            frame_path = storage_service.save_bytes(buf.tobytes(), insp.id, "frame_000000.jpg")
            quality = image_quality_analyzer.analyze(frame_path)
            db.add(ImageModel(
                inspection_id=insp.id, surface_type=VIDEO_FRAME_SURFACE, file_path=frame_path,
                original_filename=f"{video_name}#frame0", quality_score=quality["quality_score"],
                quality_metadata={**quality, "defect_scan": {"latency_ms": avg_latency, "frame_index": 0, "detection_count": 0}},
                ocr_raw_data=[],
            ))
            db.commit()
            db.refresh(insp)
    summary["overall_outcome"] = _refresh_outcome(db, insp)
    return summary


@router.post("/inspections/{id}/video")
async def analyze_video(
    id: str,
    file: UploadFile = File(...),
    sample_fps: float = Form(2.0),
    max_frames: int = Form(40),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    insp = _get_defect_inspection(db, id)
    max_frames = max(1, min(int(max_frames), 120))
    video_path = await storage_service.save_upload(file, id, kind="video")
    try:
        return await run_in_threadpool(
            _process_video, db, insp, video_path, file.filename or "video.mp4", sample_fps, max_frames, current_user.id
        )
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


@router.delete("/inspections/{id}/images/{image_id}")
def delete_defect_image(id: str, image_id: str, db: Session = Depends(get_db)):
    insp = _get_defect_inspection(db, id)
    img = db.query(ImageModel).filter(ImageModel.id == image_id, ImageModel.inspection_id == id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    db.query(DefectDetection).filter(DefectDetection.image_id == image_id).delete()
    if os.path.exists(img.file_path):
        try:
            os.remove(img.file_path)
        except OSError:
            pass
    db.delete(img)
    db.commit()
    db.refresh(insp)
    _refresh_outcome(db, insp)
    return {"message": "Image deleted successfully"}


@router.get("/inspections/{id}/overlay/{image_id}")
def get_defect_overlay(id: str, image_id: str, db: Session = Depends(get_db)):
    insp = _get_defect_inspection(db, id)
    img = db.query(ImageModel).filter(ImageModel.id == image_id, ImageModel.inspection_id == insp.id).first()
    if not img or not os.path.exists(img.file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    dets = [_detection_dict(d) for d in insp.defect_detections if d.image_id == image_id]
    data_url = heatmap_service.generate_defect_overlay_base64(img.file_path, dets)
    if not data_url:
        raise HTTPException(status_code=500, detail="Failed to render defect overlay")
    return {"image_id": image_id, "overlay_data_url": data_url}


@router.post("/inspections/{id}/finalize", response_model=DefectInspectionDetailResponse)
def finalize_defect_inspection(
    id: str,
    req: DefectFinalizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    insp = _get_defect_inspection(db, id)
    if req.override_outcome:
        if req.override_outcome not in ("PASS", "REVIEW", "DEFECTIVE"):
            raise HTTPException(status_code=400, detail="override_outcome must be PASS, REVIEW, or DEFECTIVE")
        insp.overall_outcome = req.override_outcome
    if req.final_remarks:
        insp.final_remarks = req.final_remarks
    insp.status = "FINALIZED"
    db.commit()
    generate_defect_report_for(db, insp, current_user.full_name)
    _audit(db, id, current_user.id, "INSPECTION_FINALIZED",
           f"Defect inspection finalized by {current_user.full_name}. Outcome: {insp.overall_outcome}",
           {"status": "FINALIZED", "outcome": insp.overall_outcome})
    db.commit()
    db.refresh(insp)
    return _build_detail(insp)


@router.get("/inspections/{id}/report")
def get_defect_report(id: str, db: Session = Depends(get_db)):
    insp = _get_defect_inspection(db, id)
    path = insp.report_path if insp.report_path and os.path.exists(insp.report_path) else generate_defect_report_for(db, insp)
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


# ---------------------------------------------------------------- feedback / retraining loop
@router.post("/detections/{detection_id}/feedback")
def submit_detection_feedback(
    detection_id: str,
    req: DefectFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    det = db.query(DefectDetection).filter(DefectDetection.id == detection_id).first()
    if not det:
        raise HTTPException(status_code=404, detail="Detection not found")

    previous_type, previous_status = det.defect_type, det.reviewer_status
    if req.action == "RELABEL":
        if not req.defect_type:
            raise HTTPException(status_code=400, detail="defect_type is required for RELABEL")
        det.defect_type = req.defect_type.upper()
        det.severity = grade_severity({
            "defect_type": det.defect_type, "metrics": det.metrics or {},
            "area_ratio": det.area_ratio, "confidence": det.confidence,
        })
        det.reviewer_status = "RELABELED"
    else:
        det.reviewer_status = "CONFIRMED" if req.action == "CONFIRM" else "REJECTED"
    det.reviewer_note = req.note

    sample_path = _save_training_sample(det, det.defect_type, det.reviewer_status)
    db.add(ReviewerAction(
        inspection_id=det.inspection_id,
        reviewer_id=current_user.id,
        action_type={"CONFIRM": "CONFIRM", "REJECT": "REJECT", "RELABEL": "CORRECT"}[req.action],
        target_field=f"defect:{det.id}",
        previous_value=f"{previous_type} ({previous_status})",
        new_value=f"{det.defect_type} ({det.reviewer_status})",
        reason=req.note,
    ))
    _audit(db, det.inspection_id, current_user.id, "REVIEWER_ACTION",
           f"Detection {previous_type} marked {det.reviewer_status}" + (f" as {det.defect_type}" if req.action == "RELABEL" else ""),
           {"detection_id": det.id, "training_sample": sample_path})
    db.commit()

    insp = db.query(Inspection).filter(Inspection.id == det.inspection_id).first()
    db.refresh(insp)
    outcome = _refresh_outcome(db, insp)
    db.refresh(det)
    return {
        "detection": DefectDetectionResponse.model_validate(det),
        "overall_outcome": outcome,
        "training_sample_saved": sample_path is not None,
    }


# ---------------------------------------------------------------- live / real-time
@router.post("/analyze-frame")
def analyze_live_frame(req: DefectFrameRequest, db: Session = Depends(get_db)):
    """Stateless single-frame detection for the live camera loop (nothing is persisted)."""
    img = decode_base64_image(req.image_base64)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    ref = None
    if req.inspection_id:
        insp = db.query(Inspection).filter(Inspection.id == req.inspection_id).first()
        ref_path = _reference_path(insp) if insp else None
        ref = cv2.imread(ref_path) if ref_path else None
    scan = engine.inspect(img, reference=ref, want_heatmap=False)
    if scan["streams"] == ["OPENCV"]:
        scan = {**scan, "outcome": compute_outcome(scan["detections"], quality_issue=not scan["exposure_ok"])}
    return {**_scan_meta(scan), "outcome": compute_outcome(scan["detections"], quality_issue=not scan["exposure_ok"]), "detections": scan["detections"]}


# ---------------------------------------------------------------- analytics & log
@router.get("/analytics")
def get_defect_analytics(
    days: int = Query(30, ge=1, le=365),
    product: Optional[str] = None,
    db: Session = Depends(get_db)
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = db.query(Inspection).filter(Inspection.inspection_mode == DEFECT_MODE, Inspection.created_at >= since.replace(tzinfo=None))
    if product:
        query = query.filter(Inspection.product_name == product)
    inspections = query.all()
    ids = [i.id for i in inspections]
    detections = db.query(DefectDetection).filter(DefectDetection.inspection_id.in_(ids)).all() if ids else []
    images = db.query(ImageModel).filter(ImageModel.inspection_id.in_(ids)).all() if ids else []
    return build_defect_analytics(
        inspections=[{"id": i.id, "product_name": i.product_name, "overall_outcome": i.overall_outcome, "created_at": i.created_at} for i in inspections],
        detections=[_detection_dict(d) for d in detections],
        images=[{"quality_metadata": img.quality_metadata} for img in images if img.surface_type != REFERENCE_SURFACE],
        days=min(days, 90),
    )


@router.get("/log")
def get_defect_log(
    defect_type: Optional[str] = None,
    severity: Optional[str] = None,
    reviewer_status: Optional[str] = None,
    product: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    query = db.query(DefectDetection, Inspection).join(Inspection, Inspection.id == DefectDetection.inspection_id)
    if defect_type:
        query = query.filter(DefectDetection.defect_type == defect_type)
    if severity:
        query = query.filter(DefectDetection.severity == severity)
    if reviewer_status:
        query = query.filter(DefectDetection.reviewer_status == reviewer_status)
    if product:
        query = query.filter(Inspection.product_name == product)
    total = query.count()
    rows = query.order_by(DefectDetection.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {**_detection_dict(d), "inspection_number": i.inspection_number, "product_name": i.product_name, "batch": i.brand_name}
            for d, i in rows
        ],
    }


# ---------------------------------------------------------------- demo data
DEMO_SAMPLES = [
    {"number": "DEF-DEMO-0001", "product": "Cold-Rolled Steel Panel", "batch": "LOT-A17", "category": "METAL_SHEET",
     "station": "Press Line 2", "defects": ["SCRATCH", "CRACK"], "kwargs": {}, "days_ago": 5},
    {"number": "DEF-DEMO-0002", "product": "Aluminium Housing Cover", "batch": "LOT-B04", "category": "DIE_CASTING",
     "station": "Finishing Cell 1", "defects": ["DENT", "DISCOLOURATION"], "kwargs": {}, "days_ago": 3},
    {"number": "DEF-DEMO-0003", "product": "Cold-Rolled Steel Panel", "batch": "LOT-A18", "category": "METAL_SHEET",
     "station": "Press Line 2", "defects": [], "kwargs": {}, "days_ago": 2},
    {"number": "DEF-DEMO-0004", "product": "Machined Bracket", "batch": "LOT-C11", "category": "MACHINED_PART",
     "station": "CNC Cell 3", "defects": [], "kwargs": {"product_on_background": True, "notch": True}, "days_ago": 1},
    {"number": "DEF-DEMO-0005", "product": "Cold-Rolled Steel Panel", "batch": "LOT-A19", "category": "METAL_SHEET",
     "station": "Press Line 2", "defects": ["SCRATCH"], "kwargs": {}, "days_ago": 0},
]


def seed_defect_demo_data(db: Session) -> Dict[str, Any]:
    if db.query(Inspection).filter(Inspection.inspection_number.like("DEF-DEMO-%")).first():
        return {"message": "Defect demo data already seeded"}

    demo_dir = os.path.join(settings.STORAGE_DIR, "demo_defects")
    os.makedirs(demo_dir, exist_ok=True)
    now = datetime.now(timezone.utc)
    created = []
    for idx, sample in enumerate(DEMO_SAMPLES):
        when = now - timedelta(days=sample["days_ago"])
        insp = Inspection(
            inspection_number=sample["number"],
            inspection_mode=DEFECT_MODE,
            product_name=sample["product"],
            brand_name=sample["batch"],
            category=sample["category"],
            location=sample["station"],
            notes="Synthetic demo sample",
            status="DRAFT",
            overall_outcome="PENDING",
            created_at=when,
            updated_at=when,
        )
        db.add(insp)
        db.commit()
        db.refresh(insp)

        image_path = os.path.join(demo_dir, f"{sample['number']}.jpg")
        cv2.imwrite(image_path, synthesize_surface_sample(sample["defects"], seed=11 + idx, **sample["kwargs"]))
        quality = image_quality_analyzer.analyze(image_path)
        scan = defect_detector.detect_file(image_path)
        image = ImageModel(
            inspection_id=insp.id,
            surface_type="SURFACE",
            file_path=image_path,
            original_filename=os.path.basename(image_path),
            quality_score=quality["quality_score"],
            quality_metadata={**quality, "defect_scan": _scan_meta(scan)},
            ocr_raw_data=[],
            created_at=when,
        )
        db.add(image)
        db.commit()
        db.refresh(image)
        _store_detections(db, insp, image, scan["detections"], created_at=when)
        _audit(db, insp.id, None, "DEFECT_SCAN_COMPLETED",
               f"SURFACE analysed in {scan['latency_ms']} ms ({scan['backend']}): {_describe(scan['detections'])}")
        db.commit()
        db.refresh(insp)
        _refresh_outcome(db, insp)
        created.append(insp.inspection_number)
    return {"message": "Defect demo data seeded", "inspections": created}


@router.post("/demo/seed")
def seed_defect_demo(db: Session = Depends(get_db)):
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Demo seeding is only available with DEMO_MODE=true")
    return seed_defect_demo_data(db)


@router.get("/types")
def get_defect_types():
    return {"defect_types": DEFECT_TYPES}
