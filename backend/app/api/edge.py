import json

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_device_key
from app.models.all_models import EdgeDevice
from app.services import defect_pipeline as pipeline
from app.services.defect_pipeline import station_label

router = APIRouter(prefix="/edge", tags=["Edge Devices"])


def get_device(x_device_key: str = Header(..., alias="X-Device-Key"), db: Session = Depends(get_db)) -> EdgeDevice:
    device = db.query(EdgeDevice).filter(
        EdgeDevice.key_prefix == x_device_key[:12], EdgeDevice.key_hash == hash_device_key(x_device_key)
    ).first()
    if not device or not device.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive device key")
    return device


@router.get("/ping")
def ping(device: EdgeDevice = Depends(get_device)):
    """Lets an edge node verify its key and learn which station it is bound to."""
    return {"device_id": device.id, "name": device.name, "station_id": device.station_id,
            "station": station_label(device.station), "organization_id": device.organization_id}


@router.get("/model")
def active_model(device: EdgeDevice = Depends(get_device), db: Session = Depends(get_db)):
    """The organisation's ACTIVE model, so edge nodes switch automatically after a promotion or rollback."""
    from app.services.learning.registry import registry
    from app.services.storage_service import storage_service

    mv = registry.active(db, device.organization_id)
    if not mv or not mv.onnx_key:
        return {"model": None}
    return {"model": {"id": mv.id, "name": mv.name, "version": mv.version, "sha256": mv.sha256,
                      "classes": mv.classes, "input_size": mv.input_size,
                      "download_url": storage_service.signed_url(mv.onnx_key)}}


@router.post("/ingest", status_code=201)
async def ingest(
    file: UploadFile = File(...),
    metadata: str = Form(...),
    device: EdgeDevice = Depends(get_device),
    db: Session = Depends(get_db),
):
    """
    Receives one inspected item from an edge node: the captured image plus the detections the node
    produced locally. Idempotent on metadata.local_id, so the node can safely retry after outages.
    """
    try:
        meta = json.loads(metadata)
        if not isinstance(meta, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    limit = settings.MAX_IMAGE_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_IMAGE_MB} MB limit")
    insp = pipeline.ingest_edge_result(db, device, data, meta)
    return {"inspection_id": insp.id, "inspection_number": insp.inspection_number, "overall_outcome": insp.overall_outcome}
