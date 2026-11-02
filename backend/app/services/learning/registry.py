"""
Model registry: which model each organisation runs, and the governed transitions between versions.

    TRAINING -> CANDIDATE -> GATE_PASSED -> SHADOW -> ACTIVE -> RETIRED (-> ACTIVE again on rollback)
                         +-> GATE_FAILED (promotion only by an administrator, with a recorded reason)

Inference always asks the registry for the organisation's ACTIVE version; workers and API replicas
pick up a promotion on their next request because the lookup is a cheap indexed query and detectors
are cached per version.
"""
import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import resolve_backend_path, settings
from app.core.permissions import has_permission
from app.models.all_models import ModelEvent, ModelVersion, User
from app.services.defect_detection_service import DefectDetector, defect_detector
from app.services.storage_service import storage_service

log = logging.getLogger(__name__)

PROMOTABLE = {"GATE_PASSED", "SHADOW"}


def learning_classes() -> list[str]:
    return [c.strip() for c in settings.LEARNING_CLASSES.split(",") if c.strip()]


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log_event(db: Session, organization_id: str, event_type: str, description: str,
              model: Optional[ModelVersion] = None, user: Optional[User] = None, payload: Optional[dict] = None) -> None:
    db.add(ModelEvent(organization_id=organization_id, model_version_id=model.id if model else None,
                      user_id=user.id if user else None, event_type=event_type, description=description,
                      payload=payload))


def next_version(db: Session, organization_id: str) -> int:
    return (db.query(func.max(ModelVersion.version)).filter(ModelVersion.organization_id == organization_id).scalar() or 0) + 1


class ModelRegistry:
    def __init__(self):
        self._cache: Dict[Tuple[str, str, Optional[float]], DefectDetector] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- lookups
    def active(self, db: Session, organization_id: Optional[str]) -> Optional[ModelVersion]:
        if not organization_id:
            return None
        return db.query(ModelVersion).filter(
            ModelVersion.organization_id == organization_id, ModelVersion.status == "ACTIVE"
        ).first()

    def shadow(self, db: Session, organization_id: Optional[str]) -> Optional[ModelVersion]:
        if not organization_id:
            return None
        return db.query(ModelVersion).filter(
            ModelVersion.organization_id == organization_id, ModelVersion.status == "SHADOW"
        ).first()

    def detector_for_version(self, mv: ModelVersion, backend: Optional[str] = None,
                             conf_threshold: Optional[float] = None) -> DefectDetector:
        backend = (backend or settings.DEFECT_DETECTOR_BACKEND).lower()
        key = (mv.id, backend, conf_threshold)
        with self._lock:
            det = self._cache.get(key)
        if det is not None:
            return det
        path = storage_service.local_path(mv.onnx_key) if mv.onnx_key else ""
        det = DefectDetector(model_path=path, model_classes=",".join(mv.classes or learning_classes()),
                             backend=backend, conf_threshold=conf_threshold)
        if det.model_version:
            det.model_version = f"{mv.name}@{(mv.sha256 or '')[:12]}"
        with self._lock:
            self._cache[key] = det
        return det

    def detector_for(self, db: Session, organization_id: Optional[str]) -> DefectDetector:
        """The detector serving live inference for an organisation (falls back to the configured model)."""
        mv = self.active(db, organization_id)
        return self.detector_for_version(mv) if mv else defect_detector

    def status(self, db: Session, organization_id: Optional[str]) -> dict:
        mv = self.active(db, organization_id)
        status = self.detector_for(db, organization_id).status()
        shadow = self.shadow(db, organization_id)
        status["registry"] = {
            "active": {"id": mv.id, "name": mv.name, "version": mv.version, "source": mv.source} if mv else None,
            "shadow": {"id": shadow.id, "name": shadow.name, "version": shadow.version} if shadow else None,
        }
        return status

    # ---------------------------------------------------------------- bootstrap
    def ensure_imported(self, db: Session, organization_id: str) -> Optional[ModelVersion]:
        """Registers the configured model file as v1 (ACTIVE) the first time an organisation has no models."""
        if db.query(ModelVersion).filter(ModelVersion.organization_id == organization_id).first():
            return None
        path = resolve_backend_path(settings.DEFECT_MODEL_PATH)
        if not path or not os.path.exists(path):
            return None
        folder = os.path.dirname(path)
        prefix = f"models/{organization_id}/v1"
        onnx_key = storage_service.put_file(f"{prefix}/model.onnx", path)
        pt_path = os.path.splitext(path)[0] + ".pt"
        pt_key = storage_service.put_file(f"{prefix}/model.pt", pt_path) if os.path.exists(pt_path) else None
        card_path = os.path.join(folder, "model_card.json")
        card = json.load(open(card_path, encoding="utf-8")) if os.path.exists(card_path) else None
        classes = [c.strip() for c in (settings.DEFECT_MODEL_CLASSES or settings.LEARNING_CLASSES).split(",") if c.strip()]
        probe = DefectDetector(model_path=path, model_classes=",".join(classes), backend="onnx")
        now = datetime.now(timezone.utc)
        mv = ModelVersion(
            organization_id=organization_id, version=1, name="v1", status="ACTIVE", source="IMPORTED",
            onnx_key=onnx_key, pt_key=pt_key, sha256=sha256_of(path), classes=classes,
            input_size=probe.status().get("model_input_size"),
            train_metrics=(card or {}).get("validation_metrics"), model_card=card,
            activated_at=now, approved_at=now, notes="Imported from DEFECT_MODEL_PATH",
        )
        db.add(mv)
        db.flush()
        log_event(db, organization_id, "MODEL_IMPORTED", f"Registered {os.path.basename(path)} as v1 (active)", mv)
        db.commit()
        return mv

    # ---------------------------------------------------------------- transitions
    def start_shadow(self, db: Session, mv: ModelVersion, user: User, override_reason: Optional[str] = None) -> ModelVersion:
        if mv.status not in ("GATE_PASSED", "GATE_FAILED", "CANDIDATE", "RETIRED"):
            raise HTTPException(status_code=409, detail=f"A {mv.status} model cannot enter shadow mode")
        if mv.status != "GATE_PASSED":
            self._require_override(user, override_reason, "shadow-test a model that has not passed the gate")
        for other in db.query(ModelVersion).filter(ModelVersion.organization_id == mv.organization_id,
                                                   ModelVersion.status == "SHADOW").all():
            other.status = "GATE_PASSED" if (other.gate_report or {}).get("passed") else "CANDIDATE"
        mv.status = "SHADOW"
        log_event(db, mv.organization_id, "SHADOW_STARTED", f"{mv.name} is running in shadow mode", mv, user,
                  {"override_reason": override_reason} if override_reason else None)
        db.commit()
        return mv

    def stop_shadow(self, db: Session, mv: ModelVersion, user: User) -> ModelVersion:
        if mv.status != "SHADOW":
            raise HTTPException(status_code=409, detail="Model is not in shadow mode")
        mv.status = "GATE_PASSED" if (mv.gate_report or {}).get("passed") else "CANDIDATE"
        log_event(db, mv.organization_id, "SHADOW_STOPPED", f"{mv.name} left shadow mode", mv, user)
        db.commit()
        return mv

    def promote(self, db: Session, mv: ModelVersion, user: User, override_reason: Optional[str] = None,
                event_type: str = "MODEL_PROMOTED") -> ModelVersion:
        if mv.status == "ACTIVE":
            raise HTTPException(status_code=409, detail="Model is already active")
        if mv.status in ("TRAINING", "FAILED") or not mv.onnx_key:
            raise HTTPException(status_code=409, detail=f"A {mv.status} model cannot be promoted")
        if mv.status not in PROMOTABLE and event_type != "MODEL_ROLLBACK":
            self._require_override(user, override_reason, "promote a model that has not passed the evaluation gate")
        previous = self.active(db, mv.organization_id)
        if previous:
            previous.status = "RETIRED"
        now = datetime.now(timezone.utc)
        mv.status = "ACTIVE"
        mv.approved_by_id = user.id
        mv.approved_at = now
        mv.activated_at = now
        verb = "Rolled back to" if event_type == "MODEL_ROLLBACK" else "Promoted"
        log_event(db, mv.organization_id, event_type,
                  f"{verb} {mv.name}" + (f" (replacing {previous.name})" if previous else ""), mv, user,
                  {"previous_id": previous.id if previous else None, "override_reason": override_reason})
        db.commit()
        return mv

    def rollback(self, db: Session, mv: ModelVersion, user: User) -> ModelVersion:
        if mv.status != "RETIRED":
            raise HTTPException(status_code=409, detail="Only a previously active (retired) model can be rolled back to")
        return self.promote(db, mv, user, event_type="MODEL_ROLLBACK")

    @staticmethod
    def _require_override(user: User, reason: Optional[str], action: str) -> None:
        if not has_permission(user.role, "model:override"):
            raise HTTPException(status_code=403, detail=f"Only an administrator can {action}")
        if not reason or len(reason.strip()) < 10:
            raise HTTPException(status_code=400, detail=f"A reason (10+ characters) is required to {action}")


registry = ModelRegistry()
