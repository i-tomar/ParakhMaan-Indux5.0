import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Boolean, Text, JSON, ForeignKey, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

# --- Organisation structure (multi-tenant: organisation -> plant -> line -> station) ---
class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    plants = relationship("Plant", back_populates="organization", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="organization", cascade="all, delete-orphan")

class Plant(Base):
    __tablename__ = "plants"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_plant_org_name"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    organization = relationship("Organization", back_populates="plants")
    lines = relationship("ProductionLine", back_populates="plant", cascade="all, delete-orphan")

class ProductionLine(Base):
    __tablename__ = "production_lines"
    __table_args__ = (UniqueConstraint("plant_id", "name", name="uq_line_plant_name"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    plant_id = Column(String(36), ForeignKey("plants.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    plant = relationship("Plant", back_populates="lines")
    stations = relationship("Station", back_populates="line", cascade="all, delete-orphan")

class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (UniqueConstraint("line_id", "name", name="uq_station_line_name"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    line_id = Column(String(36), ForeignKey("production_lines.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    camera_info = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    line = relationship("ProductionLine", back_populates="stations")

class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("organization_id", "sku", name="uq_product_org_sku"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    sku = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    family = Column(String(100), nullable=True)  # product line, e.g. METAL_SHEET, DIE_CASTING
    material = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    organization = relationship("Organization", back_populates="products")

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="OPERATOR")  # OPERATOR, QUALITY_MANAGER, ADMIN, AUDITOR
    badge_number = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    organization = relationship("Organization")
    inspections = relationship("Inspection", back_populates="creator")
    reviewer_actions = relationship("ReviewerAction", back_populates="reviewer")

class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_number = Column(String(50), unique=True, index=True, nullable=False)
    inspection_mode = Column(String(30), default="LEGAL_METROLOGY", index=True)  # LEGAL_METROLOGY, DEFECT
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    product_id = Column(String(36), ForeignKey("products.id"), nullable=True, index=True)
    station_id = Column(String(36), ForeignKey("stations.id"), nullable=True, index=True)
    shift = Column(String(20), nullable=True)  # A / B / C
    batch_code = Column(String(100), nullable=True, index=True)
    source = Column(String(20), default="WEB")  # WEB, EDGE, API
    external_ref = Column(String(150), unique=True, nullable=True)  # idempotency key for edge uploads
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
    product = relationship("Product")
    station = relationship("Station")
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
    # Learning loop: only VERIFIED images (every defect on them reviewed / drawn) become training labels.
    review_status = Column(String(20), default="UNREVIEWED", index=True)  # UNREVIEWED, VERIFIED
    reviewed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    # Sticky dataset split assigned at first verification; "test" images form the frozen golden set.
    dataset_split = Column(String(10), nullable=True, index=True)  # train, val, test
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
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
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
    model_version = Column(String(100), nullable=True)  # ONNX model fingerprint when a model contributed
    metrics = Column(JSON, default=dict)  # detector-specific measurements, normalized bbox
    frame_index = Column(Integer, nullable=True)  # set for detections sampled from video
    frame_timestamp_ms = Column(Float, nullable=True)
    reviewer_status = Column(String(20), default="PENDING")  # PENDING, CONFIRMED, REJECTED, RELABELED
    reviewer_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="defect_detections")
    image = relationship("Image")

class EdgeDevice(Base):
    """An inference node near a camera; authenticates to the central API with a per-device key."""
    __tablename__ = "edge_devices"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    station_id = Column(String(36), ForeignKey("stations.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    key_prefix = Column(String(16), index=True, nullable=False)  # shown in the UI to identify a key
    key_hash = Column(String(128), nullable=False)
    is_active = Column(Boolean, default=True)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    station = relationship("Station")

class Job(Base):
    """Background work (video analysis, later training/evaluation) with persisted status and progress."""
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    job_type = Column(String(50), nullable=False, index=True)  # VIDEO_ANALYSIS
    status = Column(String(20), default="QUEUED", index=True)  # QUEUED, RUNNING, SUCCEEDED, FAILED
    progress = Column(Float, default=0.0)  # 0..1
    message = Column(String(500), nullable=True)
    payload = Column(JSON, default=dict)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=True, index=True)
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

# --- Phase B: governed learning loop ---
class ReviewTask(Base):
    """An image the smart sampler (or a person) routed to human review; at most one open task per image."""
    __tablename__ = "review_tasks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False, index=True)
    image_id = Column(String(36), ForeignKey("images.id"), nullable=False, unique=True)
    priority = Column(Float, default=0.0, index=True)  # higher = review sooner
    reasons = Column(JSON, default=list)  # e.g. [{"code": "UNCERTAIN", "detail": "..."}]
    source = Column(String(20), default="SAMPLER")  # SAMPLER, MANUAL
    status = Column(String(20), default="OPEN", index=True)  # OPEN, DONE, SKIPPED
    created_at = Column(DateTime, default=utcnow)
    completed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    image = relationship("Image")
    inspection = relationship("Inspection")

class DatasetVersion(Base):
    """Immutable YOLO export of all verified images at a point in time."""
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("organization_id", "version", name="uq_dataset_org_version"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(20), default="BUILDING")  # BUILDING, READY, FAILED
    storage_key = Column(String(500), nullable=True)
    classes = Column(JSON, default=list)
    image_count = Column(Integer, default=0)
    label_count = Column(Integer, default=0)
    class_counts = Column(JSON, default=dict)
    split_counts = Column(JSON, default=dict)
    manifest_sha256 = Column(String(64), nullable=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    notes = Column(Text, nullable=True)

class ModelVersion(Base):
    """Model registry entry. Exactly one ACTIVE version per organisation serves inference."""
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("organization_id", "version", name="uq_model_org_version"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    # TRAINING, CANDIDATE, GATE_FAILED, GATE_PASSED, SHADOW, ACTIVE, RETIRED, FAILED
    status = Column(String(20), default="CANDIDATE", index=True)
    source = Column(String(20), default="TRAINED")  # IMPORTED, TRAINED, FEDERATED
    parent_id = Column(String(36), ForeignKey("model_versions.id"), nullable=True)
    dataset_version_id = Column(String(36), ForeignKey("dataset_versions.id"), nullable=True)
    onnx_key = Column(String(500), nullable=True)
    pt_key = Column(String(500), nullable=True)
    sha256 = Column(String(64), nullable=True)
    classes = Column(JSON, default=list)
    input_size = Column(Integer, nullable=True)
    train_metrics = Column(JSON, nullable=True)
    gate_report = Column(JSON, nullable=True)
    model_card = Column(JSON, nullable=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=True)
    created_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    approved_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    dataset_version = relationship("DatasetVersion")

class ShadowPrediction(Base):
    """A shadow model's output on a live image, stored next to the active model's output for comparison."""
    __tablename__ = "shadow_predictions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    model_version_id = Column(String(36), ForeignKey("model_versions.id"), nullable=False, index=True)
    champion_version_id = Column(String(36), ForeignKey("model_versions.id"), nullable=True)
    image_id = Column(String(36), ForeignKey("images.id"), nullable=False, index=True)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
    detections = Column(JSON, default=list)
    champion_detections = Column(JSON, default=list)
    agreement = Column(JSON, default=dict)
    latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utcnow)

class ModelEvent(Base):
    """Audit trail for datasets and models (training, gate, shadow, approval, promotion, rollback)."""
    __tablename__ = "model_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    model_version_id = Column(String(36), ForeignKey("model_versions.id"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    event_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)
