import base64
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user, get_org_inspection, require
from app.models.all_models import (
    User, Inspection, Image as ImageModel, Declaration, ComplianceResult, AuditEvent
)
from app.schemas.all_schemas import (
    InspectionCreate, InspectionUpdate, InspectionResponse, InspectionDetailResponse,
    InspectionFinalizeRequest, ImageResponse
)
from app.services.storage_service import storage_service
from app.services.image_quality import image_quality_analyzer
from app.services.ocr_service import ocr_service
from app.services.declaration_service import declaration_extractor
from app.services.classifier_service import product_classifier
from app.services.rule_engine import rule_engine
from app.services.pdf_report_service import pdf_report_service
from app.services.heatmap_service import heatmap_service
from app.services.llm_service import llm_service

router = APIRouter(prefix="/inspections", tags=["Inspections"])

LEGAL_MODE = "LEGAL_METROLOGY"

@router.post("", response_model=InspectionResponse)
def create_inspection(
    req: InspectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write"))
):
    count = db.query(Inspection).filter(Inspection.inspection_mode == LEGAL_MODE).count() + 1
    while db.query(Inspection).filter(Inspection.inspection_number == f"INSP-2026-{count:04d}").first():
        count += 1
    insp_number = f"INSP-2026-{count:04d}"

    inspection = Inspection(
        inspection_number=insp_number,
        inspection_mode=LEGAL_MODE,
        product_name=req.product_name,
        brand_name=req.brand_name,
        category=req.category,
        location=req.location,
        notes=req.notes,
        created_by_id=current_user.id,
        organization_id=current_user.organization_id,
        status="DRAFT",
        overall_outcome="PENDING"
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)

    # Audit event
    audit = AuditEvent(
        inspection_id=inspection.id,
        user_id=current_user.id,
        event_type="INSPECTION_CREATED",
        description=f"Inspection {insp_number} created by {current_user.full_name}",
        state_after={"status": inspection.status, "category": inspection.category}
    )
    db.add(audit)
    db.commit()

    return inspection

@router.get("", response_model=List[InspectionResponse])
def list_inspections(
    status: Optional[str] = None,
    outcome: Optional[str] = None,
    search: Optional[str] = None,
    mode: str = LEGAL_MODE,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:read"))
):
    query = db.query(Inspection).filter(
        Inspection.inspection_mode == mode, Inspection.organization_id == current_user.organization_id
    )
    if status:
        query = query.filter(Inspection.status == status)
    if outcome:
        query = query.filter(Inspection.overall_outcome == outcome)
    if search:
        query = query.filter(
            (Inspection.product_name.ilike(f"%{search}%")) |
            (Inspection.inspection_number.ilike(f"%{search}%")) |
            (Inspection.brand_name.ilike(f"%{search}%"))
        )
    inspections = query.order_by(Inspection.created_at.desc()).all()
    
    # Calculate image counts
    results = []
    for insp in inspections:
        img_count = len(insp.images)
        insp_dict = {
            "id": insp.id,
            "inspection_number": insp.inspection_number,
            "inspection_mode": insp.inspection_mode,
            "product_name": insp.product_name,
            "brand_name": insp.brand_name,
            "category": insp.category,
            "status": insp.status,
            "overall_outcome": insp.overall_outcome,
            "created_by_id": insp.created_by_id,
            "location": insp.location,
            "notes": insp.notes,
            "final_remarks": insp.final_remarks,
            "report_path": insp.report_path,
            "image_count": img_count,
            "created_at": insp.created_at,
            "updated_at": insp.updated_at
        }
        results.append(InspectionResponse(**insp_dict))
    return results

@router.get("/{id}", response_model=InspectionDetailResponse)
def get_inspection_detail(id: str, db: Session = Depends(get_db),
                          current_user: User = Depends(require("inspection:read"))):
    return get_org_inspection(db, id, current_user)

@router.post("/{id}/images", response_model=ImageResponse)
async def upload_inspection_image(
    id: str,
    file: UploadFile = File(...),
    surface_type: str = Form("FRONT"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write"))
):
    insp = get_org_inspection(db, id, current_user)

    # Save image to storage (key), then analyse the locally readable copy
    file_path = await storage_service.save_upload(file, id)
    local_path = storage_service.local_path(file_path)

    # Perform OpenCV image quality analysis
    quality_meta = image_quality_analyzer.analyze(local_path)

    # Perform OCR
    ocr_spans = ocr_service.extract_text(local_path, image_id=None, surface_type=surface_type)

    image = ImageModel(
        inspection_id=id,
        surface_type=surface_type.upper(),
        file_path=file_path,
        original_filename=file.filename or "uploaded_image.jpg",
        quality_score=quality_meta["quality_score"],
        quality_metadata=quality_meta,
        ocr_raw_data=ocr_spans
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    # Update spans with real image ID
    for span in ocr_spans:
        span["image_id"] = image.id
    image.ocr_raw_data = ocr_spans
    db.commit()

    # Audit event
    audit = AuditEvent(
        inspection_id=id,
        user_id=current_user.id,
        event_type="IMAGE_UPLOADED",
        description=f"Surface {surface_type} uploaded (Quality Score: {quality_meta['quality_score']})",
        state_after={"image_id": image.id, "quality_score": image.quality_score}
    )
    db.add(audit)
    db.commit()

    return image

@router.post("/{id}/images/capture", response_model=ImageResponse)
def capture_camera_image(
    id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write"))
):
    """
    Accepts Base64 image captured directly from PC webcam or mobile camera.
    """
    insp = get_org_inspection(db, id, current_user)

    image_data_b64 = payload.get("image_base64", "")
    surface_type = str(payload.get("surface_type", "FRONT")).upper()[:50]

    if "," in image_data_b64:
        image_data_b64 = image_data_b64.split(",")[1]

    try:
        image_bytes = base64.b64decode(image_data_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    file_path = storage_service.save_bytes(image_bytes, id, f"cam_{surface_type.lower()}.jpg")
    local_path = storage_service.local_path(file_path)

    # Quality check
    quality_meta = image_quality_analyzer.analyze(local_path)

    # OCR extraction
    ocr_spans = ocr_service.extract_text(local_path, image_id=None, surface_type=surface_type)

    image = ImageModel(
        inspection_id=id,
        surface_type=surface_type,
        file_path=file_path,
        original_filename=f"live_cam_{surface_type.lower()}.jpg",
        quality_score=quality_meta["quality_score"],
        quality_metadata=quality_meta,
        ocr_raw_data=ocr_spans
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    # Update spans with image ID
    for span in ocr_spans:
        span["image_id"] = image.id
    image.ocr_raw_data = ocr_spans
    db.commit()

    # Audit event
    audit = AuditEvent(
        inspection_id=id,
        user_id=current_user.id,
        event_type="CAMERA_CAPTURED",
        description=f"Surface {surface_type} captured via live camera (Quality Score: {quality_meta['quality_score']})",
        state_after={"image_id": image.id, "quality_score": image.quality_score}
    )
    db.add(audit)
    db.commit()

    return image

@router.delete("/{id}/images/{image_id}")
def delete_inspection_image(
    id: str,
    image_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write"))
):
    get_org_inspection(db, id, current_user)
    img = db.query(ImageModel).filter(ImageModel.id == image_id, ImageModel.inspection_id == id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    storage_service.delete(img.file_path)
    db.delete(img)
    db.commit()
    return {"message": "Image deleted successfully"}

@router.post("/{id}/process")
def process_inspection_pipeline(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write"))
):
    """
    Executes the deterministic AI compliance pipeline:
    1. Collects all image OCR spans
    2. Extracts structured declarations
    3. Runs category classification
    4. Evaluates Deterministic Rule Engine
    5. Calculates overall outcome (PASS / REVIEW / POSSIBLE_NON_COMPLIANCE)
    """
    insp = get_org_inspection(db, id, current_user)

    if insp.inspection_mode == "DEFECT":
        raise HTTPException(status_code=400, detail="Defect inspections are processed via /defects endpoints")

    if not insp.images:
        raise HTTPException(status_code=400, detail="No package images uploaded for this inspection")

    insp.status = "PROCESSING"
    db.commit()

    # 1. Aggregate all OCR spans and image metadata (with automatic live re-extraction fallback)
    all_spans = []
    images_meta = []
    all_text = []

    for img in insp.images:
        spans = img.ocr_raw_data or []
        # If spans are missing or only contain placeholder text, run real OCR extraction
        has_real_text = any(s.get("text") and s.get("text") != "[Detected Text Region]" for s in spans)
        if not has_real_text and storage_service.exists(img.file_path):
            spans = ocr_service.extract_text(storage_service.local_path(img.file_path), image_id=img.id,
                                             surface_type=img.surface_type)
            img.ocr_raw_data = spans
            db.commit()

        q_meta = img.quality_metadata or {}
        images_meta.append({
            "image_id": img.id,
            "surface_type": img.surface_type,
            "quality_score": img.quality_score,
            "blur": q_meta.get("blur", False),
            "glare": q_meta.get("glare", False),
            "is_empty": q_meta.get("is_empty", False) or (img.quality_score == 0.0),
            "surface_visible": q_meta.get("surface_visible", True),
            "sharpness_score": q_meta.get("sharpness_score", 0.0),
            "edge_density": q_meta.get("edge_density", 0.0),
            "issues": q_meta.get("issues", [])
        })
        for s in spans:
            all_spans.append(s)
            all_text.append(s.get("text", ""))

    text_corpus = " ".join(all_text)

    # 2. Product Category Classification
    cat_result = product_classifier.classify(text_corpus, user_selected_category=insp.category)
    insp.category = cat_result["category"]

    # 3. Extract Statutory Declarations
    extracted_decls = declaration_extractor.extract_from_spans(all_spans)

    # Clean existing declarations and store new ones
    db.query(Declaration).filter(Declaration.inspection_id == id).delete()
    for d in extracted_decls:
        decl = Declaration(
            inspection_id=id,
            image_id=d.get("image_id"),
            field_name=d.get("field_name"),
            detected_value=d.get("detected_value"),
            normalized_value=d.get("normalized_value"),
            confidence=d.get("confidence", 1.0),
            bbox=d.get("bbox", []),
            extraction_method=d.get("extraction_method", "REGEX")
        )
        db.add(decl)
    db.commit()

    # 4. Evaluate Deterministic Rule Engine
    compliance_results = rule_engine.evaluate_inspection(
        declarations=extracted_decls,
        images_metadata=images_meta,
        category=insp.category,
        is_imported=("imported" in text_corpus.lower() or "country of origin" in text_corpus.lower())
    )

    # Store compliance results
    db.query(ComplianceResult).filter(ComplianceResult.inspection_id == id).delete()
    for res in compliance_results:
        c_res = ComplianceResult(
            inspection_id=id,
            rule_id=res.get("rule_id"),
            field=res.get("field"),
            detected_value=res.get("detected_value"),
            normalized_value=res.get("normalized_value"),
            confidence=res.get("confidence", 1.0),
            outcome=res.get("outcome"),
            severity=res.get("severity", "HIGH"),
            evidence=res.get("evidence", {}),
            legal_reference=res.get("legal_reference"),
            explanation=res.get("explanation"),
            reviewer_status="PENDING"
        )
        db.add(c_res)
    db.commit()

    # 5. Compute overall outcome and update state
    overall_outcome = rule_engine.compute_overall_outcome(compliance_results)
    insp.overall_outcome = overall_outcome
    insp.status = "REVIEW" if overall_outcome == "REVIEW" else "FINALIZED"
    db.commit()

    # Generate initial PDF report
    try:
        insp_detail = get_org_inspection(db, id, current_user)
        report_path = pdf_report_service.generate_inspection_report(insp_detail.__dict__)
        insp.report_path = report_path
        db.commit()
    except Exception as e:
        print(f"Error generating initial PDF: {e}")

    # Audit event
    audit = AuditEvent(
        inspection_id=id,
        user_id=current_user.id,
        event_type="RULE_ENGINE_EVALUATED",
        description=f"Rule engine processed {len(compliance_results)} statutory rules. Overall outcome: {overall_outcome}",
        state_after={"status": insp.status, "overall_outcome": overall_outcome}
    )
    db.add(audit)
    db.commit()

    return get_org_inspection(db, id, current_user)

@router.post("/{id}/finalize", response_model=InspectionDetailResponse)
def finalize_inspection(
    id: str,
    req: InspectionFinalizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:finalize"))
):
    insp = get_org_inspection(db, id, current_user)

    insp.status = "FINALIZED"
    if req.override_status:
        insp.overall_outcome = req.override_status
    if req.final_remarks:
        insp.final_remarks = req.final_remarks
    db.commit()

    # Re-generate PDF with final signoff
    insp_dict = {
        "id": insp.id,
        "inspection_number": insp.inspection_number,
        "product_name": insp.product_name,
        "brand_name": insp.brand_name,
        "category": insp.category,
        "status": insp.status,
        "overall_outcome": insp.overall_outcome,
        "inspector_name": current_user.full_name,
        "final_remarks": insp.final_remarks,
        "created_at": insp.created_at,
        "compliance_results": [r.__dict__ for r in insp.compliance_results],
        "declarations": [d.__dict__ for d in insp.declarations],
        "reviewer_actions": [a.__dict__ for a in insp.reviewer_actions]
    }
    report_path = pdf_report_service.generate_inspection_report(insp_dict)
    insp.report_path = report_path
    db.commit()

    # Audit event
    audit = AuditEvent(
        inspection_id=id,
        user_id=current_user.id,
        event_type="INSPECTION_FINALIZED",
        description=f"Inspection finalized by {current_user.full_name}. Outcome: {insp.overall_outcome}",
        state_after={"status": "FINALIZED", "outcome": insp.overall_outcome, "remarks": insp.final_remarks}
    )
    db.add(audit)
    db.commit()

    return insp

@router.get("/{id}/heatmap/{image_id}")
def get_image_heatmap(id: str, image_id: str, db: Session = Depends(get_db),
                      current_user: User = Depends(require("inspection:read"))):
    """
    Generates and returns an OpenCV thermal/attention heatmap for a package image.
    """
    get_org_inspection(db, id, current_user)
    img = db.query(ImageModel).filter(ImageModel.id == image_id, ImageModel.inspection_id == id).first()
    if not img or not storage_service.exists(img.file_path):
        raise HTTPException(status_code=404, detail="Image not found")

    heatmap_b64 = heatmap_service.generate_heatmap_base64(
        image_path=storage_service.local_path(img.file_path),
        ocr_spans=img.ocr_raw_data or []
    )
    if not heatmap_b64:
        raise HTTPException(status_code=500, detail="Failed to generate visual heatmap")

    return {
        "image_id": image_id,
        "surface_type": img.surface_type,
        "heatmap_data_url": heatmap_b64
    }

@router.post("/{id}/reprocess", response_model=InspectionDetailResponse)
def reprocess_inspection(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:write"))
):
    """
    Forces live re-extraction with native WinOCR across all images and re-runs Rule Engine.
    """
    insp = get_org_inspection(db, id, current_user)

    for img in insp.images:
        if storage_service.exists(img.file_path):
            spans = ocr_service.extract_text(storage_service.local_path(img.file_path), image_id=img.id,
                                             surface_type=img.surface_type)
            img.ocr_raw_data = spans
    db.commit()

    return process_inspection_pipeline(id, db, current_user)

@router.post("/{id}/ai-analysis")
async def get_ai_deep_analysis(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require("inspection:read"))
):
    """
    Generates a deep LLM statutory reasoning & risk assessment report for this inspection.
    """
    insp = get_org_inspection(db, id, current_user)

    decls = [d.__dict__ for d in insp.declarations]
    compliance_results = [r.__dict__ for r in insp.compliance_results]
    images_meta = [
        {"image_id": img.id, "surface_type": img.surface_type, "quality_score": img.quality_score}
        for img in insp.images
    ]

    analysis = await llm_service.analyze_full_inspection(
        inspection_number=insp.inspection_number,
        category=insp.category,
        declarations=decls,
        compliance_results=compliance_results,
        images_meta=images_meta
    )
    return analysis

@router.get("/llm/status")
async def get_llm_status(_: User = Depends(get_current_user)):
    """
    Checks the local Ollama LLM status and active model.
    """
    return await llm_service.check_ollama_status()

@router.post("/llm/config")
def update_llm_config(payload: dict = Body(...), _: User = Depends(require("system:configure"))):
    """
    Updates LLM base URL and active model.
    """
    base_url = payload.get("base_url")
    model = payload.get("model")
    llm_service.set_model_config(base_url=base_url, model=model)
    return {
        "message": "LLM configuration updated",
        "base_url": llm_service.base_url,
        "model": llm_service.model
    }
