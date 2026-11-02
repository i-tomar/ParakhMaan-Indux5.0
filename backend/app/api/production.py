"""Master data (products, golden references, lines, machines, batches) and the unit log."""
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_roles
from app.core.config import resolve_backend_path, settings
from app.core.database import get_db
from app.models.all_models import DefectDetection, User
from app.models.industrial import (
    Batch, GoldenReference, Machine, ModelVersion, Product, ProductionLine, ProductionUnit, RejectEvent,
)
from app.services.analytics.quality import batch_report_data
from app.services.inference.engine import engine
from app.services.line.actuator import latency_budget
from app.services.line.decision import DecisionPolicy
from app.services.pdf_report_service import pdf_report_service
from app.services.storage_service import storage_service

router = APIRouter(prefix="/production", tags=["Production"])


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:70] or uuid.uuid4().hex[:8]


class ToleranceRow(BaseModel):
    feature: str
    nominal: float
    minus: float = Field(ge=0)
    plus: float = Field(ge=0)


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    key: Optional[str] = Field(None, pattern=r"^[a-z0-9_]+$", max_length=80)
    category: str = "GENERAL_MANUFACTURED"
    description: Optional[str] = None
    dimension_spec: List[ToleranceRow] = []
    decision_policy: Dict[str, Any] = {}
    calibration_id: Optional[str] = None


class LineIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str
    belt_speed_mm_s: float = Field(200.0, gt=0)
    camera_to_diverter_mm: float = Field(600.0, gt=0)
    pitch_mm: float = Field(300.0, gt=0)
    actuator_kind: str = Field("SIMULATED", pattern="^(SIMULATED|SERIAL|WEBHOOK)$")
    actuator_target: Optional[str] = None


class MachineIn(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str
    line_id: Optional[str] = None


class BatchIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    product_id: str
    planned_quantity: Optional[int] = Field(None, gt=0)
    notes: Optional[str] = None


class UnitOverride(BaseModel):
    final_decision: str = Field(pattern="^(ACCEPT|REJECT)$")


def product_dict(p: Product) -> Dict[str, Any]:
    status = engine.status()["anomaly"]
    return {
        "id": p.id, "key": p.key, "name": p.name, "category": p.category, "description": p.description,
        "dimension_spec": p.dimension_spec or [], "decision_policy": DecisionPolicy.from_dict(p.decision_policy).to_dict(),
        "calibration_id": p.calibration_id, "is_active": p.is_active, "created_at": p.created_at,
        "anomaly_model": status["versions"].get(p.key),
        "golden_references": [{"id": g.id, "file_path": g.file_path, "label": g.label, "is_active": g.is_active}
                              for g in p.golden_references],
    }


def ensure_products_for_models(db: Session) -> None:
    """Every anomaly model found on disk gets a product row and a registry entry."""
    folder = resolve_backend_path(settings.ANOMALY_PRODUCTS_DIR)
    for key, version in engine.status()["anomaly"]["versions"].items():
        if not db.query(Product).filter(Product.key == key).first():
            db.add(Product(key=key, name=key.replace("_", " ").title(), category="MVTEC_REFERENCE"))
        if not db.query(ModelVersion).filter(ModelVersion.version == version).first():
            db.add(ModelVersion(kind="ANOMALY", product_key=key, version=version, path=os.path.join(folder, key),
                                status="PRODUCTION", promoted_at=datetime.now(timezone.utc), notes="Installed base model"))
    status = engine.status()["segmentation"]
    if status["version"] and not db.query(ModelVersion).filter(ModelVersion.version == status["version"]).first():
        db.add(ModelVersion(kind="SEGMENTATION", version=status["version"], path=resolve_backend_path(settings.SEG_MODEL_PATH),
                            status="PRODUCTION", promoted_at=datetime.now(timezone.utc), notes="Installed base model"))
    db.commit()


# ---------------------------------------------------------------- products
@router.get("/products")
def list_products(db: Session = Depends(get_db)):
    return [product_dict(p) for p in db.query(Product).order_by(Product.name).all()]


@router.post("/products")
def create_product(req: ProductIn, db: Session = Depends(get_db), _: User = Depends(require_roles("SUPERVISOR"))):
    key = req.key or _slug(req.name)
    if db.query(Product).filter(Product.key == key).first():
        raise HTTPException(409, f"Product key '{key}' already exists")
    row = Product(key=key, name=req.name, category=req.category, description=req.description,
                  dimension_spec=[t.model_dump() for t in req.dimension_spec], decision_policy=req.decision_policy,
                  calibration_id=req.calibration_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return product_dict(row)


@router.put("/products/{product_id}")
def update_product(product_id: str, req: ProductIn, db: Session = Depends(get_db), _: User = Depends(require_roles("SUPERVISOR"))):
    row = db.get(Product, product_id)
    if not row:
        raise HTTPException(404, "Product not found")
    row.name, row.category, row.description = req.name, req.category, req.description
    row.dimension_spec = [t.model_dump() for t in req.dimension_spec]
    row.decision_policy, row.calibration_id = req.decision_policy, req.calibration_id
    db.commit()
    db.refresh(row)
    return product_dict(row)


@router.post("/products/{product_id}/golden")
async def add_golden_reference(
    product_id: str, file: UploadFile = File(...), label: str = Form(""), db: Session = Depends(get_db),
    _: User = Depends(require_roles("SUPERVISOR")),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    path = await storage_service.save_upload(file, f"golden_{product.key}")
    if cv2.imread(path) is None:
        os.remove(path)
        raise HTTPException(400, "Reference file is not a readable image")
    for old in product.golden_references:
        old.is_active = False
    row = GoldenReference(product_id=product_id, file_path=path, label=label or file.filename)
    db.add(row)
    db.commit()
    db.refresh(product)
    return product_dict(product)


@router.post("/golden/{golden_id}/activate")
def activate_golden(golden_id: str, db: Session = Depends(get_db), _: User = Depends(require_roles("SUPERVISOR"))):
    row = db.get(GoldenReference, golden_id)
    if not row:
        raise HTTPException(404, "Golden reference not found")
    for other in row.product.golden_references:
        other.is_active = other.id == golden_id
    db.commit()
    return product_dict(row.product)


# ---------------------------------------------------------------- lines / machines
@router.get("/lines")
def list_lines(db: Session = Depends(get_db)):
    rows = db.query(ProductionLine).order_by(ProductionLine.code).all()
    return [{"id": r.id, "code": r.code, "name": r.name, "belt_speed_mm_s": r.belt_speed_mm_s,
             "camera_to_diverter_mm": r.camera_to_diverter_mm, "pitch_mm": r.pitch_mm, "actuator_kind": r.actuator_kind,
             "actuator_target": r.actuator_target,
             "budget": latency_budget(r.belt_speed_mm_s, r.camera_to_diverter_mm, r.pitch_mm),
             "machines": [{"id": m.id, "code": m.code, "name": m.name} for m in r.machines]} for r in rows]


@router.post("/lines")
def create_line(req: LineIn, db: Session = Depends(get_db), _: User = Depends(require_roles("SUPERVISOR"))):
    if db.query(ProductionLine).filter(ProductionLine.code == req.code).first():
        raise HTTPException(409, "Line code already exists")
    row = ProductionLine(**req.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "code": row.code}


@router.get("/machines")
def list_machines(db: Session = Depends(get_db)):
    return [{"id": m.id, "code": m.code, "name": m.name, "line_id": m.line_id, "line": m.line.code if m.line else None}
            for m in db.query(Machine).order_by(Machine.code).all()]


@router.post("/machines")
def create_machine(req: MachineIn, db: Session = Depends(get_db), _: User = Depends(require_roles("SUPERVISOR"))):
    if db.query(Machine).filter(Machine.code == req.code).first():
        raise HTTPException(409, "Machine code already exists")
    row = Machine(**req.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "code": row.code}


# ---------------------------------------------------------------- batches
@router.get("/batches")
def list_batches(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Batch)
    if status:
        q = q.filter(Batch.status == status)
    out = []
    for b in q.order_by(Batch.started_at.desc()).limit(200).all():
        data = batch_report_data(db, b)
        out.append({"id": b.id, "code": b.code, "product_id": b.product_id, "product": data["product"], "status": b.status,
                    "planned_quantity": b.planned_quantity, "is_synthetic": b.is_synthetic, "started_at": b.started_at,
                    "closed_at": b.closed_at, "kpis": data["kpis"], "top_defect": data["pareto"][0]["defect_type"] if data["pareto"] else None})
    return out


@router.post("/batches")
def create_batch(req: BatchIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if db.query(Batch).filter(Batch.code == req.code).first():
        raise HTTPException(409, "Batch code already exists")
    if not db.get(Product, req.product_id):
        raise HTTPException(404, "Product not found")
    row = Batch(**req.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "code": row.code}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    row = db.get(Batch, batch_id)
    if not row:
        raise HTTPException(404, "Batch not found")
    return {"id": row.id, **batch_report_data(db, row)}


@router.post("/batches/{batch_id}/close")
def close_batch(batch_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    row = db.get(Batch, batch_id)
    if not row:
        raise HTTPException(404, "Batch not found")
    row.status, row.closed_at = "CLOSED", datetime.now(timezone.utc)
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/batches/{batch_id}/report")
def batch_report(batch_id: str, db: Session = Depends(get_db)):
    row = db.get(Batch, batch_id)
    if not row:
        raise HTTPException(404, "Batch not found")
    path = pdf_report_service.generate_batch_report(batch_report_data(db, row))
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


# ---------------------------------------------------------------- units
def unit_dict(u: ProductionUnit, detections: Optional[List[DefectDetection]] = None) -> Dict[str, Any]:
    data = {
        "id": u.id, "unit_code": u.unit_code, "product": u.product.name if u.product else None, "product_id": u.product_id,
        "batch": u.batch.code if u.batch else None, "machine": u.machine.code if u.machine else None,
        "line": u.line.code if u.line else None, "shift": u.shift, "source": u.source, "is_synthetic": u.is_synthetic,
        "decision": u.decision, "final_decision": u.final_decision, "reasons": u.decision_reasons or [],
        "anomaly_score": u.anomaly_score, "dimensional": u.dimensional, "model_versions": u.model_versions or {},
        "streams": u.streams or [], "latency_ms": u.latency_ms, "inspected_at": u.inspected_at,
        "image_path": u.image_path, "heatmap_path": u.heatmap_path, "inspection_id": u.inspection_id,
    }
    if detections is not None:
        data["detections"] = [{
            "id": d.id, "defect_type": d.defect_type, "severity": d.severity, "confidence": d.confidence, "bbox": d.bbox,
            "area_ratio": d.area_ratio, "detector": d.detector, "metrics": d.metrics, "reviewer_status": d.reviewer_status,
            "model_version": d.model_version, "length_mm": d.length_mm, "width_mm": d.width_mm, "area_mm2": d.area_mm2,
        } for d in detections]
    return data


@router.get("/units")
def list_units(
    decision: Optional[str] = None, product_id: Optional[str] = None, batch_id: Optional[str] = None,
    machine_id: Optional[str] = None, shift: Optional[str] = None, search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    q = db.query(ProductionUnit)
    for column, value in ((ProductionUnit.decision, decision), (ProductionUnit.product_id, product_id),
                          (ProductionUnit.batch_id, batch_id), (ProductionUnit.machine_id, machine_id),
                          (ProductionUnit.shift, shift)):
        if value:
            q = q.filter(column == value)
    if search:
        q = q.filter(ProductionUnit.unit_code.ilike(f"%{search}%"))
    total = q.count()
    rows = q.order_by(ProductionUnit.inspected_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [unit_dict(u) for u in rows]}


@router.get("/units/{unit_id}")
def get_unit(unit_id: str, db: Session = Depends(get_db)):
    unit = db.get(ProductionUnit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")
    detections = db.query(DefectDetection).filter(DefectDetection.unit_id == unit_id).all()
    rejects = db.query(RejectEvent).filter(RejectEvent.unit_id == unit_id).all()
    return {**unit_dict(unit, detections), "reject_events": [
        {"actuator": r.actuator, "status": r.status, "fire_after_ms": r.fire_after_ms, "at": r.created_at} for r in rejects]}


@router.post("/units/{unit_id}/decision")
def override_decision(unit_id: str, req: UnitOverride, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    unit = db.get(ProductionUnit, unit_id)
    if not unit:
        raise HTTPException(404, "Unit not found")
    unit.final_decision = req.final_decision
    db.commit()
    return unit_dict(unit)
