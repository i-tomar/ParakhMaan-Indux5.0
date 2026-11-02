"""Manufacturing domain tables. Purely additive: Legal Metrology tables are untouched."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.all_models import generate_uuid


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    key = Column(String(80), unique=True, index=True, nullable=False)  # anomaly model folder name
    name = Column(String(255), nullable=False)
    category = Column(String(100), default="GENERAL_MANUFACTURED")
    description = Column(Text, nullable=True)
    dimension_spec = Column(JSON, default=list)  # [{feature, nominal, minus, plus}]
    decision_policy = Column(JSON, default=dict)
    calibration_id = Column(String(36), ForeignKey("calibrations.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)

    calibration = relationship("CalibrationProfile", foreign_keys=[calibration_id])
    golden_references = relationship("GoldenReference", back_populates="product", cascade="all, delete-orphan")


class GoldenReference(Base):
    __tablename__ = "golden_references"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False)
    label = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)

    product = relationship("Product", back_populates="golden_references")


class CalibrationProfile(Base):
    __tablename__ = "calibrations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    method = Column(String(40), nullable=False)
    mm_per_px = Column(Float, nullable=False)
    data = Column(JSON, default=dict)  # full Calibration, including assumptions
    created_at = Column(DateTime, default=_now)


class ProductionLine(Base):
    __tablename__ = "production_lines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    belt_speed_mm_s = Column(Float, default=200.0)
    camera_to_diverter_mm = Column(Float, default=600.0)
    pitch_mm = Column(Float, default=300.0)
    actuator_kind = Column(String(20), default="SIMULATED")  # SIMULATED, SERIAL, WEBHOOK
    actuator_target = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=_now)

    machines = relationship("Machine", back_populates="line")


class Machine(Base):
    __tablename__ = "machines"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    line_id = Column(String(36), ForeignKey("production_lines.id"), nullable=True)
    created_at = Column(DateTime, default=_now)

    line = relationship("ProductionLine", back_populates="machines")


class Batch(Base):
    __tablename__ = "batches"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(80), unique=True, index=True, nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=False, index=True)
    status = Column(String(20), default="OPEN")  # OPEN, CLOSED
    planned_quantity = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    is_synthetic = Column(Boolean, default=False)
    started_at = Column(DateTime, default=_now)
    closed_at = Column(DateTime, nullable=True)

    product = relationship("Product")


class ProductionUnit(Base):
    """One physical item inspected once: the row every analytic is computed from."""
    __tablename__ = "production_units"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    unit_code = Column(String(80), unique=True, index=True, nullable=False)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=True, index=True)
    batch_id = Column(String(36), ForeignKey("batches.id"), nullable=True, index=True)
    machine_id = Column(String(36), ForeignKey("machines.id"), nullable=True, index=True)
    line_id = Column(String(36), ForeignKey("production_lines.id"), nullable=True, index=True)
    shift = Column(String(5), index=True, nullable=True)  # A, B, C
    source = Column(String(20), default="UPLOAD")  # UPLOAD, CAMERA, VIDEO, LIVE, SIMULATED
    is_synthetic = Column(Boolean, default=False, index=True)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=True, index=True)
    image_path = Column(String(500), nullable=True)
    heatmap_path = Column(String(500), nullable=True)
    decision = Column(String(20), index=True, nullable=False)  # ACCEPT, REJECT, MANUAL_REVIEW
    decision_reasons = Column(JSON, default=list)
    final_decision = Column(String(20), nullable=True)  # inspector override
    anomaly_score = Column(Float, nullable=True)
    dimensional = Column(JSON, nullable=True)
    model_versions = Column(JSON, default=dict)
    streams = Column(JSON, default=list)
    latency_ms = Column(Float, nullable=True)
    inspected_at = Column(DateTime, default=_now, index=True)

    product = relationship("Product")
    batch = relationship("Batch")
    machine = relationship("Machine")
    line = relationship("ProductionLine")


class RejectEvent(Base):
    __tablename__ = "reject_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    unit_id = Column(String(36), ForeignKey("production_units.id"), nullable=False, index=True)
    actuator = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False)
    fire_after_ms = Column(Float, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)


class QualityAlert(Base):
    __tablename__ = "quality_alerts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    fingerprint = Column(String(200), unique=True, index=True, nullable=False)
    kind = Column(String(40), nullable=False)  # DEFECT_RATE_SPIKE, ASSOCIATION
    dimension = Column(String(40), nullable=True)
    group_name = Column(String(120), nullable=True)
    message = Column(Text, nullable=False)
    value = Column(Float, nullable=True)
    limit_value = Column(Float, nullable=True)
    status = Column(String(20), default="OPEN")  # OPEN, ACKNOWLEDGED, RESOLVED
    created_at = Column(DateTime, default=_now)


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    alert_id = Column(String(36), ForeignKey("quality_alerts.id"), nullable=True)
    dimension = Column(String(40), nullable=True)
    group_name = Column(String(120), nullable=True)
    finding = Column(Text, nullable=False)  # what was confirmed on the shop floor
    action = Column(Text, nullable=False)
    owner = Column(String(120), nullable=True)
    status = Column(String(20), default="OPEN")
    created_at = Column(DateTime, default=_now)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    kind = Column(String(20), nullable=False, index=True)  # SEGMENTATION, ANOMALY
    product_key = Column(String(80), nullable=True, index=True)
    version = Column(String(80), nullable=False, index=True)
    path = Column(String(500), nullable=False)
    status = Column(String(20), default="CANDIDATE", index=True)  # CANDIDATE, PRODUCTION, ARCHIVED, REFUSED
    metrics = Column(JSON, default=dict)
    gate_result = Column(JSON, nullable=True)
    parent_version = Column(String(80), nullable=True)
    dataset_version_id = Column(String(36), ForeignKey("dataset_versions.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    promoted_at = Column(DateTime, nullable=True)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_key = Column(String(80), index=True, nullable=False)
    version = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)
    sample_count = Column(Integer, default=0)
    label_counts = Column(JSON, default=dict)
    manifest_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=_now)


class DatasetSample(Base):
    __tablename__ = "dataset_samples"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    product_key = Column(String(80), index=True, nullable=False)
    label = Column(String(50), nullable=False, index=True)  # GOOD or a defect class
    file_path = Column(String(500), nullable=False)
    sha256 = Column(String(64), index=True, nullable=False)
    annotation = Column(JSON, nullable=True)  # {bbox, polygon}
    split = Column(String(10), default="TRAIN", index=True)  # TRAIN, HOLDOUT
    source = Column(String(30), default="REVIEW")  # REVIEW, UPLOAD, IMPORT
    source_detection_id = Column(String(36), nullable=True)
    reviewer_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=_now)


class TrainingJob(Base):
    __tablename__ = "training_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    kind = Column(String(20), nullable=False)  # ANOMALY, SEGMENTATION
    product_key = Column(String(80), nullable=True, index=True)
    status = Column(String(20), default="QUEUED", index=True)  # QUEUED, RUNNING, SUCCEEDED, FAILED
    params = Column(JSON, default=dict)
    dataset_version_id = Column(String(36), ForeignKey("dataset_versions.id"), nullable=True)
    candidate_version = Column(String(80), nullable=True)
    log = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    finished_at = Column(DateTime, nullable=True)
