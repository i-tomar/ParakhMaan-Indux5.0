"""Manufacturing analytics, alerts and corrective actions."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.all_models import User
from app.models.industrial import CorrectiveAction, QualityAlert
from app.services.analytics import quality

router = APIRouter(prefix="/analytics", tags=["Manufacturing Analytics"])


class AlertUpdate(BaseModel):
    status: str = Field(pattern="^(OPEN|ACKNOWLEDGED|RESOLVED)$")


class ActionIn(BaseModel):
    alert_id: Optional[str] = None
    dimension: Optional[str] = None
    group_name: Optional[str] = None
    finding: str = Field(min_length=3)
    action: str = Field(min_length=3)
    owner: Optional[str] = None


@router.get("/overview")
def overview(
    days: int = Query(30, ge=1, le=365), product_id: Optional[str] = None, batch_id: Optional[str] = None,
    machine_id: Optional[str] = None, line_id: Optional[str] = None, shift: Optional[str] = None,
    include_synthetic: bool = True, db: Session = Depends(get_db),
):
    return quality.overview(db, days, product_id=product_id, batch_id=batch_id, machine_id=machine_id, line_id=line_id,
                            shift=shift, include_synthetic=include_synthetic)


@router.get("/root-cause")
def root_cause(
    days: int = Query(30, ge=1, le=365), defect_type: Optional[str] = None, product_id: Optional[str] = None,
    batch_id: Optional[str] = None, machine_id: Optional[str] = None, line_id: Optional[str] = None,
    shift: Optional[str] = None, include_synthetic: bool = True, db: Session = Depends(get_db),
):
    return quality.root_cause(db, days, defect_type, product_id=product_id, batch_id=batch_id, machine_id=machine_id,
                              line_id=line_id, shift=shift, include_synthetic=include_synthetic)


@router.get("/alerts")
def alerts(status: Optional[str] = None, db: Session = Depends(get_db)):
    quality.refresh_alerts(db)
    q = db.query(QualityAlert)
    if status:
        q = q.filter(QualityAlert.status == status)
    return [{"id": a.id, "kind": a.kind, "dimension": a.dimension, "group": a.group_name, "message": a.message, "value": a.value,
             "limit": a.limit_value, "status": a.status, "created_at": a.created_at}
            for a in q.order_by(QualityAlert.created_at.desc()).limit(100).all()]


@router.post("/alerts/{alert_id}")
def update_alert(alert_id: str, req: AlertUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    row = db.get(QualityAlert, alert_id)
    if not row:
        raise HTTPException(404, "Alert not found")
    row.status = req.status
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/corrective-actions")
def actions(db: Session = Depends(get_db)):
    return [{"id": a.id, "alert_id": a.alert_id, "dimension": a.dimension, "group": a.group_name, "finding": a.finding,
             "action": a.action, "owner": a.owner, "status": a.status, "created_at": a.created_at}
            for a in db.query(CorrectiveAction).order_by(CorrectiveAction.created_at.desc()).all()]


@router.post("/corrective-actions")
def create_action(req: ActionIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    row = CorrectiveAction(**req.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id}
