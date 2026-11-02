import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import cv2
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_org_detection, get_org_inspection, require
from app.core.config import settings
from app.core.database import get_db
from app.models.all_models import DefectDetection, Image as ImageModel, Inspection, ReviewerAction, User
from app.schemas.all_schemas import (
    DefectDetectionResponse, DefectFeedbackRequest, DefectFinalizeRequest, DefectFrameRequest,
    DefectInspectionCreate, DefectInspectionDetailResponse, DefectInspectionSummary, ImageResponse, JobResponse
)
from app.services import defect_pipeline as pipeline
from app.services import job_service
from app.services.defect_analytics_service import build_defect_analytics
from app.services.defect_detection_service import DEFECT_TYPES, decode_base64_image, defect_detector, grade_severity
from app.services.heatmap_service import heatmap_service
from app.services.image_quality import image_quality_analyzer
from app.services.learning.registry import registry
from app.services.storage_service import storage_service

router = APIRouter(prefix="/defects", tags=["Defect Inspection"])

DEFECT_MODE = pipeline.DEFECT_MODE
REFERENCE_SURFACE = pipeline.REFERENCE_SURFACE

# Kept for callers that imported these from the router module
seed_defect_demo_data = pipeline.seed_defect_demo_data
defect_detector = defect_detector


def _inspection(db: Session, id: str, user: User) -> Inspection:
    return get_org_inspection(db, id, user, mode=DEFECT_MODE)


# ---------------------------------------------------------------- inspections
@router.get("/status")
def get_detector_status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return registry.status(db, current_user.organization_id)


@router.get("/types")
def get_defect_types(_: User = Depends(get_current_user)):
    return {"defect_types": DEFECT_TYPES}


@router.post("/inspections", response_model=DefectInspectionDetailResponse)
def create_defect_inspection(
    req: DefectInspectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write")),
):
    insp = pipeline.create_inspection(
        db, current_user.organization_id, current_user, product_id=req.product_id, station_id=req.station_id,
        shift=req.shift, batch_code=req.batch_code or req.brand_name, product_name=req.product_name,
        category=req.category, location=req.location, notes=req.notes,
    )
    return pipeline.build_detail(insp)


@router.get("/inspections", response_model=List[DefectInspectionSummary])
def list_defect_inspections(
    outcome: Optional[str] = None,
    search: Optional[str] = None,
    station_id: Optional[str] = None,
    product_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:read")),
):
    query = db.query(Inspection).filter(
        Inspection.inspection_mode == DEFECT_MODE, Inspection.organization_id == current_user.organization_id
    )
    if outcome:
        query = query.filter(Inspection.overall_outcome == outcome)
    if station_id:
        query = query.filter(Inspection.station_id == station_id)
    if product_id:
        query = query.filter(Inspection.product_id == product_id)
    if search:
        like = f"%{search}%"
        query = query.filter(
            Inspection.product_name.ilike(like) | Inspection.inspection_number.ilike(like)
            | Inspection.batch_code.ilike(like) | Inspection.brand_name.ilike(like)
        )
    results = []
    for insp in query.order_by(Inspection.created_at.desc()).limit(limit).all():
        active = [d for d in insp.defect_detections if d.reviewer_status != "REJECTED"]
        counts: Dict[str, int] = {}
        for d in active:
            counts[d.defect_type] = counts.get(d.defect_type, 0) + 1
        results.append(DefectInspectionSummary(
            id=insp.id, inspection_number=insp.inspection_number, inspection_mode=insp.inspection_mode,
            product_id=insp.product_id, station_id=insp.station_id, shift=insp.shift, batch_code=insp.batch_code,
            source=insp.source, product_name=insp.product_name, brand_name=insp.batch_code or insp.brand_name,
            category=insp.category, status=insp.status, overall_outcome=insp.overall_outcome,
            created_by_id=insp.created_by_id, location=insp.location, notes=insp.notes,
            final_remarks=insp.final_remarks, report_path=insp.report_path,
            image_count=sum(1 for i in insp.images if i.surface_type != REFERENCE_SURFACE),
            created_at=insp.created_at, updated_at=insp.updated_at, defect_count=len(active),
            top_defect_type=max(counts, key=counts.get) if counts else None,
        ))
    return results


@router.get("/inspections/{id}", response_model=DefectInspectionDetailResponse)
def get_defect_inspection(id: str, db: Session = Depends(get_db), current_user: User = Depends(require("inspection:read"))):
    return pipeline.build_detail(_inspection(db, id, current_user))


@router.post("/inspections/{id}/reference", response_model=ImageResponse)
async def upload_reference_image(
    id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write")),
):
    """Golden (defect-free) sample used for colour, contour, and printed-design comparison."""
    insp = _inspection(db, id, current_user)
    key = await storage_service.save_upload(file, id)
    for old in [img for img in insp.images if img.surface_type == REFERENCE_SURFACE]:
        storage_service.delete(old.file_path)
        db.delete(old)
    quality = image_quality_analyzer.analyze(storage_service.local_path(key))
    image = ImageModel(
        inspection_id=id, surface_type=REFERENCE_SURFACE, file_path=key,
        original_filename=file.filename or "reference.jpg", quality_score=quality["quality_score"],
        quality_metadata=quality, ocr_raw_data=[],
    )
    db.add(image)
    pipeline.audit(db, id, current_user.id, "REFERENCE_UPLOADED", f"Golden reference sample '{image.original_filename}' attached")
    db.commit()
    db.refresh(image)
    return image


@router.post("/inspections/{id}/analyze")
async def analyze_uploaded_image(
    id: str,
    file: UploadFile = File(...),
    surface_type: str = Form("SURFACE"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write")),
):
    insp = _inspection(db, id, current_user)
    key = await storage_service.save_upload(file, id)
    return await run_in_threadpool(
        pipeline.analyze_and_store, db, insp, key, file.filename or "uploaded_image.jpg",
        surface_type.upper()[:50], current_user.id, "DEFECT_SCAN_COMPLETED"
    )


@router.post("/inspections/{id}/capture")
def analyze_camera_capture(
    id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write")),
):
    insp = _inspection(db, id, current_user)
    surface_type = str(payload.get("surface_type", "SURFACE")).upper()[:50]
    img = decode_base64_image(payload.get("image_base64", ""))
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    key = storage_service.save_bytes(buf.tobytes(), id, f"cam_{surface_type.lower()}.jpg")
    return pipeline.analyze_and_store(
        db, insp, key, f"live_cam_{surface_type.lower()}.jpg", surface_type, current_user.id, "DEFECT_CAMERA_SCAN"
    )


@router.post("/inspections/{id}/video", response_model=JobResponse, status_code=202)
async def analyze_video(
    id: str,
    file: UploadFile = File(...),
    sample_fps: float = Form(2.0),
    max_frames: int = Form(40),
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write")),
):
    """Queues video analysis; poll GET /jobs/{job_id} for progress and the summary."""
    insp = _inspection(db, id, current_user)
    video_key = await storage_service.save_upload(file, id, kind="video")
    return job_service.enqueue(
        db, pipeline.VIDEO_JOB,
        {"video_key": video_key, "video_name": (file.filename or "video.mp4")[:200],
         "sample_fps": max(0.1, min(float(sample_fps), 30.0)), "max_frames": max(1, min(int(max_frames), 120))},
        organization_id=current_user.organization_id, created_by_id=current_user.id, inspection_id=insp.id,
    )


@router.delete("/inspections/{id}/images/{image_id}")
def delete_defect_image(id: str, image_id: str, db: Session = Depends(get_db),
                        current_user: User = Depends(require("inspection:write"))):
    insp = _inspection(db, id, current_user)
    img = db.query(ImageModel).filter(ImageModel.id == image_id, ImageModel.inspection_id == id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    db.query(DefectDetection).filter(DefectDetection.image_id == image_id).delete()
    storage_service.delete(img.file_path)
    db.delete(img)
    db.commit()
    db.refresh(insp)
    pipeline.refresh_outcome(db, insp)
    return {"message": "Image deleted successfully"}


@router.get("/inspections/{id}/overlay/{image_id}")
def get_defect_overlay(id: str, image_id: str, db: Session = Depends(get_db),
                       current_user: User = Depends(require("inspection:read"))):
    insp = _inspection(db, id, current_user)
    img = db.query(ImageModel).filter(ImageModel.id == image_id, ImageModel.inspection_id == insp.id).first()
    if not img or not storage_service.exists(img.file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    dets = [pipeline.detection_dict(d) for d in insp.defect_detections if d.image_id == image_id]
    data_url = heatmap_service.generate_defect_overlay_base64(storage_service.local_path(img.file_path), dets)
    if not data_url:
        raise HTTPException(status_code=500, detail="Failed to render defect overlay")
    return {"image_id": image_id, "overlay_data_url": data_url}


@router.post("/inspections/{id}/finalize", response_model=DefectInspectionDetailResponse)
def finalize_defect_inspection(
    id: str,
    req: DefectFinalizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:finalize")),
):
    insp = _inspection(db, id, current_user)
    if req.override_outcome:
        if req.override_outcome not in ("PASS", "REVIEW", "DEFECTIVE"):
            raise HTTPException(status_code=400, detail="override_outcome must be PASS, REVIEW, or DEFECTIVE")
        insp.overall_outcome = req.override_outcome
    if req.final_remarks:
        insp.final_remarks = req.final_remarks
    insp.status = "FINALIZED"
    db.commit()
    pipeline.generate_report(db, insp, current_user.full_name)
    pipeline.audit(db, id, current_user.id, "INSPECTION_FINALIZED",
                   f"Defect inspection finalized by {current_user.full_name}. Outcome: {insp.overall_outcome}",
                   {"status": "FINALIZED", "outcome": insp.overall_outcome})
    db.commit()
    db.refresh(insp)
    return pipeline.build_detail(insp)


def get_defect_report(insp: Inspection, db: Session):
    path = insp.report_path if insp.report_path and os.path.exists(insp.report_path) else pipeline.generate_report(db, insp)
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


@router.get("/inspections/{id}/report")
def get_defect_report_endpoint(id: str, db: Session = Depends(get_db),
                               current_user: User = Depends(require("inspection:read"))):
    return get_defect_report(_inspection(db, id, current_user), db)


# ---------------------------------------------------------------- feedback / retraining loop
@router.post("/detections/{detection_id}/feedback")
def submit_detection_feedback(
    detection_id: str,
    req: DefectFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("review:write")),
):
    det = get_org_detection(db, detection_id, current_user)
    if det.inspection.status == "FINALIZED":
        raise HTTPException(status_code=409, detail="Inspection is finalized")

    previous_type, previous_status = det.defect_type, det.reviewer_status
    if req.action == "RELABEL":
        if not req.defect_type:
            raise HTTPException(status_code=400, detail="defect_type is required for RELABEL")
        det.defect_type = req.defect_type.upper()[:50]
        det.severity = grade_severity({
            "defect_type": det.defect_type, "metrics": det.metrics or {},
            "area_ratio": det.area_ratio, "confidence": det.confidence,
        })
        det.reviewer_status = "RELABELED"
    else:
        det.reviewer_status = "CONFIRMED" if req.action == "CONFIRM" else "REJECTED"
    det.reviewer_note = req.note

    sample_path = pipeline.save_training_sample(det, det.defect_type, det.reviewer_status)
    db.add(ReviewerAction(
        inspection_id=det.inspection_id, reviewer_id=current_user.id,
        action_type={"CONFIRM": "CONFIRM", "REJECT": "REJECT", "RELABEL": "CORRECT"}[req.action],
        target_field=f"defect:{det.id}", previous_value=f"{previous_type} ({previous_status})",
        new_value=f"{det.defect_type} ({det.reviewer_status})", reason=req.note,
    ))
    pipeline.audit(db, det.inspection_id, current_user.id, "REVIEWER_ACTION",
                   f"Detection {previous_type} marked {det.reviewer_status}"
                   + (f" as {det.defect_type}" if req.action == "RELABEL" else ""),
                   {"detection_id": det.id, "training_sample": sample_path})
    db.commit()

    insp = det.inspection
    db.refresh(insp)
    outcome = pipeline.refresh_outcome(db, insp)
    db.refresh(det)
    return {
        "detection": DefectDetectionResponse.model_validate(det),
        "overall_outcome": outcome,
        "training_sample_saved": sample_path is not None,
    }


# ---------------------------------------------------------------- live / real-time
@router.post("/analyze-frame")
def analyze_live_frame(req: DefectFrameRequest, db: Session = Depends(get_db),
                       current_user: User = Depends(require("inspection:write"))):
    """Stateless single-frame detection for the live camera loop (nothing is persisted)."""
    img = decode_base64_image(req.image_base64)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    ref = None
    if req.inspection_id:
        ref_path = pipeline.reference_path(_inspection(db, req.inspection_id, current_user))
        ref = cv2.imread(ref_path) if ref_path else None
    detector = registry.detector_for(db, current_user.organization_id)
    scan = detector.detect(img, ref, max_side=req.max_side)
    return {**pipeline.scan_meta({**scan, "model_version": detector.model_version}), "detections": scan["detections"]}


# ---------------------------------------------------------------- analytics & log
@router.get("/analytics")
def get_defect_analytics(
    days: int = Query(30, ge=1, le=365),
    product: Optional[str] = None,
    station_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("analytics:read")),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = db.query(Inspection).filter(
        Inspection.inspection_mode == DEFECT_MODE,
        Inspection.organization_id == current_user.organization_id,
        Inspection.created_at >= since.replace(tzinfo=None),
    )
    if product:
        query = query.filter(Inspection.product_name == product)
    if station_id:
        query = query.filter(Inspection.station_id == station_id)
    inspections = query.all()
    ids = [i.id for i in inspections]
    detections = db.query(DefectDetection).filter(DefectDetection.inspection_id.in_(ids)).all() if ids else []
    images = db.query(ImageModel).filter(ImageModel.inspection_id.in_(ids)).all() if ids else []
    return build_defect_analytics(
        inspections=[{"id": i.id, "product_name": i.product_name, "overall_outcome": i.overall_outcome,
                      "created_at": i.created_at} for i in inspections],
        detections=[pipeline.detection_dict(d) for d in detections],
        images=[{"quality_metadata": img.quality_metadata} for img in images if img.surface_type != REFERENCE_SURFACE],
        days=min(days, 90),
    )


@router.get("/log")
def get_defect_log(
    defect_type: Optional[str] = None,
    severity: Optional[str] = None,
    reviewer_status: Optional[str] = None,
    product: Optional[str] = None,
    station_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:read")),
):
    query = (
        db.query(DefectDetection, Inspection)
        .join(Inspection, Inspection.id == DefectDetection.inspection_id)
        .filter(Inspection.organization_id == current_user.organization_id)
    )
    if defect_type:
        query = query.filter(DefectDetection.defect_type == defect_type)
    if severity:
        query = query.filter(DefectDetection.severity == severity)
    if reviewer_status:
        query = query.filter(DefectDetection.reviewer_status == reviewer_status)
    if product:
        query = query.filter(Inspection.product_name == product)
    if station_id:
        query = query.filter(Inspection.station_id == station_id)
    total = query.count()
    rows = query.order_by(DefectDetection.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {**pipeline.detection_dict(d), "inspection_number": i.inspection_number, "product_name": i.product_name,
             "batch": i.batch_code or i.brand_name, "station": i.location, "shift": i.shift}
            for d, i in rows
        ],
    }


@router.post("/demo/seed")
def seed_defect_demo(db: Session = Depends(get_db), current_user: User = Depends(require("system:configure"))):
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Demo seeding is disabled in production")
    return pipeline.seed_defect_demo_data(db, current_user)
