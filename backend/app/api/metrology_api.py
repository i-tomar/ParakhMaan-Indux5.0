"""Calibration and dimensional inspection."""
import json
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import require_roles
from app.core.database import get_db
from app.models.all_models import User
from app.models.industrial import CalibrationProfile, Product
from app.services.inspection_service import active_reference, calibration_for
from app.services.metrology.calibration import Calibration, calibrate_checkerboard, calibrate_reference_length
from app.services.metrology.measure import inspect_dimensions, segment_part

router = APIRouter(prefix="/metrology", tags=["Dimensional Inspection"])


class ReferenceCalibration(BaseModel):
    name: str
    known_mm: float = Field(gt=0)
    measured_px: float = Field(gt=0)


def _row(c: CalibrationProfile) -> Dict[str, Any]:
    return {"id": c.id, "name": c.name, "method": c.method, "mm_per_px": c.mm_per_px, "created_at": c.created_at, "details": c.data}


def _save(db: Session, name: str, calibration: Calibration) -> Dict[str, Any]:
    row = CalibrationProfile(name=name, method=calibration.method, mm_per_px=calibration.mm_per_px, data=calibration.to_dict())
    db.add(row)
    db.commit()
    return _row(row)


async def _read_image(file: UploadFile) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(await file.read(), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(400, "File is not a readable image")
    return image


@router.get("/calibrations")
def list_calibrations(db: Session = Depends(get_db)):
    return [_row(c) for c in db.query(CalibrationProfile).order_by(CalibrationProfile.created_at.desc()).all()]


@router.post("/calibrations/reference")
def create_reference_calibration(req: ReferenceCalibration, db: Session = Depends(get_db), _: User = Depends(require_roles("SUPERVISOR"))):
    return _save(db, req.name, calibrate_reference_length(req.known_mm, req.measured_px))


@router.post("/calibrations/checkerboard")
async def create_checkerboard_calibration(
    name: str = Form(...), columns: int = Form(..., ge=2), rows: int = Form(..., ge=2), square_mm: float = Form(..., gt=0),
    file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(require_roles("SUPERVISOR")),
):
    image = await _read_image(file)
    try:
        calibration = calibrate_checkerboard(image, (columns, rows), square_mm)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _save(db, name, calibration)


@router.post("/inspect")
async def inspect(
    file: UploadFile = File(...), product_id: Optional[str] = Form(None), calibration_id: Optional[str] = Form(None),
    specification: Optional[str] = Form(None), db: Session = Depends(get_db),
):
    """Measures one part. `specification` is a JSON list of {feature, nominal, minus, plus}."""
    image = await _read_image(file)
    product = db.get(Product, product_id) if product_id else None
    calibration = None
    if calibration_id:
        row = db.get(CalibrationProfile, calibration_id)
        if not row:
            raise HTTPException(404, "Calibration not found")
        calibration = Calibration.from_dict(row.data)
    elif product:
        calibration = calibration_for(db, product)
    if calibration is None:
        raise HTTPException(422, "A calibration is required: millimetres cannot be reported without one")
    spec: List[Dict[str, Any]] = product.dimension_spec if product else []
    if specification:
        try:
            spec = json.loads(specification)
        except json.JSONDecodeError:
            raise HTTPException(422, "specification must be valid JSON")
    reference = active_reference(db, product)
    contour = segment_part(reference) if reference is not None else None
    return inspect_dimensions(image, calibration, spec, contour)
