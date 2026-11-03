import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Boolean, Text, JSON, ForeignKey, DateTime, Integer
from sqlalchemy.orm import relationship
from app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="INSPECTOR")  # INSPECTOR, SUPERVISOR, ADMIN
    badge_number = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspections = relationship("Inspection", back_populates="creator")
    reviewer_actions = relationship("ReviewerAction", back_populates="reviewer")

class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_number = Column(String(50), unique=True, index=True, nullable=False)
    inspection_mode = Column(String(30), default="LEGAL_METROLOGY", index=True)  # LEGAL_METROLOGY, DEFECT
    product_name = Column(String(255), nullable=True)
    brand_name = Column(String(255), nullable=True)
    category = Column(String(100), default="PACKAGED_COMMODITY")  # PACKAGED_FOOD, COSMETICS, MEDICAL_DEVICE, TOYS, etc.
    status = Column(String(50), default="DRAFT")  # DRAFT, PROCESSING, REVIEW, FINALIZED
    overall_outcome = Column(String(50), default="PENDING")  # PENDING, PASS, REVIEW, POSSIBLE_NON_COMPLIANCE
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    location = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    final_remarks = Column(Text, nullable=True)
    report_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    creator = relationship("User", back_populates="inspections")
    images = relationship("Image", back_populates="inspection", cascade="all, delete-orphan")
    declarations = relationship("Declaration", back_populates="inspection", cascade="all, delete-orphan")
    compliance_results = relationship("ComplianceResult", back_populates="inspection", cascade="all, delete-orphan")
    reviewer_actions = relationship("ReviewerAction", back_populates="inspection", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="inspection", cascade="all, delete-orphan")
    defect_detections = relationship("DefectDetection", back_populates="inspection", cascade="all, delete-orphan")

class Image(Base):
    __tablename__ = "images"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
    surface_type = Column(String(50), default="UNKNOWN")  # FRONT, BACK, SIDE, TOP, BOTTOM, UNKNOWN
    file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    quality_score = Column(Float, default=1.0)
    quality_metadata = Column(JSON, default=dict)  # blur, glare, resolution, perspective, occlusion
    ocr_raw_data = Column(JSON, default=list)  # list of OCR spans with bboxes and confidence
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="images")
    declarations = relationship("Declaration", back_populates="image")

class Declaration(Base):
    __tablename__ = "declarations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
    image_id = Column(String(36), ForeignKey("images.id"), nullable=True)
    field_name = Column(String(100), nullable=False)  # mrp, net_quantity, manufacturer, date, etc.
    detected_value = Column(Text, nullable=True)
    normalized_value = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0)
    bbox = Column(JSON, default=list)  # [x_min, y_min, x_max, y_max] or polygon
    extraction_method = Column(String(50), default="REGEX")  # REGEX, NLP, LLM, MANUAL
    is_verified = Column(Boolean, default=False)
    reviewer_value = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="declarations")
    image = relationship("Image", back_populates="declarations")

class Rule(Base):
    __tablename__ = "rules"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    rule_id = Column(String(50), unique=True, index=True, nullable=False)  # PC-DEC-001, etc.
    layer = Column(String(50), nullable=False)  # BASE, DECLARATIONS, UNITS, FONT_PDP, SCHEDULES
    category = Column(String(100), default="ALL")
    condition = Column(String(100), nullable=True)
    requirement = Column(String(255), nullable=False)
    what_to_detect = Column(Text, nullable=False)
    validation_logic = Column(String(100), nullable=False)
    severity = Column(String(50), default="HIGH")  # CRITICAL, HIGH, MEDIUM, LOW
    source_ids = Column(String(255), nullable=True)
    status = Column(String(50), default="ACTIVE")
    version = Column(String(20), default="1.0")

class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
    rule_id = Column(String(50), nullable=False)
    field = Column(String(100), nullable=False)
    detected_value = Column(Text, nullable=True)
    normalized_value = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0)
    outcome = Column(String(50), nullable=False)  # PASS, REVIEW, POSSIBLE_NON_COMPLIANCE
    severity = Column(String(50), default="HIGH")
    evidence = Column(JSON, default=dict)  # { image_id, bbox, text, surface_type }
    legal_reference = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    reviewer_status = Column(String(50), default="PENDING")  # PENDING, CONFIRMED, OVERRIDDEN
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="compliance_results")

class ReviewerAction(Base):
    __tablename__ = "reviewer_actions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
    reviewer_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action_type = Column(String(50), nullable=False)  # CONFIRM, CORRECT, REJECT, REQUEST_NEW_IMAGE
    target_field = Column(String(100), nullable=False)
    previous_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="reviewer_actions")
    reviewer = relationship("User", back_populates="reviewer_actions")

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=True)
    user_id = Column(String(36), nullable=True)
    event_type = Column(String(100), nullable=False)  # INSPECTION_CREATED, IMAGE_UPLOADED, OCR_COMPLETED, RULE_EVALUATED, REVIEW_ACTION, FINALIZED
    description = Column(Text, nullable=False)
    state_before = Column(JSON, nullable=True)
    state_after = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="audit_events")

class DefectDetection(Base):
    __tablename__ = "defect_detections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False, index=True)
    image_id = Column(String(36), ForeignKey("images.id"), nullable=True, index=True)
    defect_type = Column(String(50), nullable=False, index=True)  # SCRATCH, CRACK, DENT, DISCOLOURATION, DIMENSIONAL_ANOMALY
    severity = Column(String(20), default="MEDIUM")  # CRITICAL, HIGH, MEDIUM, LOW
    confidence = Column(Float, default=0.5)
    bbox = Column(JSON, default=list)  # [x_min, y_min, x_max, y_max] in original image pixels
    area_ratio = Column(Float, default=0.0)  # bbox area / image area
    detector = Column(String(30), default="OPENCV")  # OPENCV, ONNX
    metrics = Column(JSON, default=dict)  # detector-specific measurements, normalized bbox
    frame_index = Column(Integer, nullable=True)  # set for detections sampled from video
    frame_timestamp_ms = Column(Float, nullable=True)
    reviewer_status = Column(String(20), default="PENDING")  # PENDING, CONFIRMED, REJECTED, RELABELED
    reviewer_note = Column(Text, nullable=True)
    unit_id = Column(String(36), nullable=True, index=True)  # production_units.id
    model_version = Column(String(120), nullable=True)
    length_mm = Column(Float, nullable=True)  # only with a calibration
    width_mm = Column(Float, nullable=True)
    area_mm2 = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="defect_detections")
    image = relationship("Image")
