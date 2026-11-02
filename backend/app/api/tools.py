import os
import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.services.mpe_calculator import mpe_calculator
from app.services.schedule_checker import schedule_checker
from app.services.pdp_calculator import pdp_calculator

router = APIRouter(prefix="/tools", tags=["Inspector Tools & Schedules"], dependencies=[Depends(get_current_user)])

class MPECalculateRequest(BaseModel):
    quantity: float
    unit: str

class LotSampleEvaluateRequest(BaseModel):
    lot_size: int
    declared_quantity: float
    unit: str
    measured_weights: List[float]

class PDPFontCheckRequest(BaseModel):
    package_shape: str = "RECTANGULAR"
    height_cm: float = 15.0
    width_cm: float = 10.0
    depth_or_diameter_cm: float = 5.0

@router.post("/mpe-calculate")
def calculate_mpe(req: MPECalculateRequest):
    """
    Calculates statutory Maximum Permissible Error (MPE) under First Schedule of PCR 2011.
    """
    return mpe_calculator.get_mpe_for_mass_or_volume(req.quantity, req.unit)

@router.post("/lot-sample-evaluate")
def evaluate_lot_sampling(req: LotSampleEvaluateRequest):
    """
    Evaluates net quantity batch sampling inspection under Fifth Schedule (Rules 19-22).
    """
    return mpe_calculator.evaluate_sample_lot(
        lot_size=req.lot_size,
        declared_quantity=req.declared_quantity,
        unit=req.unit,
        measured_weights=req.measured_weights
    )

@router.post("/pdp-font-check")
def calculate_pdp_font(req: PDPFontCheckRequest):
    """
    Calculates Principal Display Panel (PDP) area and required statutory minimum numeral/letter height under Rule 7.
    """
    return pdp_calculator.calculate_pdp_area_and_font_standards(
        package_shape=req.package_shape,
        height_cm=req.height_cm,
        width_cm=req.width_cm,
        depth_or_diameter_cm=req.depth_or_diameter_cm
    )

@router.get("/schedules")
def get_second_schedule_commodities():
    """
    Returns list of commodities and statutory permitted pack sizes under Second Schedule.
    """
    return {
        "commodities": schedule_checker.SECOND_SCHEDULE_COMMODITIES,
        "when_packed_commodities": schedule_checker.THIRD_SCHEDULE_WHEN_PACKED
    }

@router.get("/rules-database")
def get_full_rules_database():
    """
    Returns the complete SIH26034 statutory rules dataset with official source gazettes and legal references.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    rules_path = os.path.join(base_dir, "SIH26034_RULES.json")
    if not os.path.exists(rules_path):
        # Fallback to app data
        rules_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "rules.json")

    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading rules database: {e}")
    
    return {"metadata": {}, "sources": [], "rules": []}
