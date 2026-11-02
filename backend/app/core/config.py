import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEV_SECRET_KEY = "dev-only-insecure-secret-change-me"

class Settings(BaseSettings):
    PROJECT_NAME: str = "ParakhMaan Quality Inspection Platform"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "1.0.0"
    # development | production. Production refuses insecure defaults (see validate_settings).
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", DEV_SECRET_KEY)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    # Comma-separated list of allowed browser origins (never "*" in production)
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    LOGIN_MAX_ATTEMPTS: int = 5  # per email+IP within LOGIN_WINDOW_SECONDS
    LOGIN_WINDOW_SECONDS: int = 300
    # Optional first administrator, created on startup when no users exist
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    # Development only: seed demo organisation, users and inspections on startup
    SEED_DEMO_DATA: bool = True
    DEMO_PASSWORD: str = "ParakhMaan@2026"

    # Database (SQLite for local development, PostgreSQL for shared deployments)
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/legal_metrology.db")
    AUTO_MIGRATE: bool = True  # run Alembic migrations on API startup

    # Storage: "local" (STORAGE_DIR) or "s3" (S3 / MinIO); files are served through signed URLs
    STORAGE_BACKEND: str = "local"
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))
    REPORTS_DIR: str = os.getenv("REPORTS_DIR", str(BASE_DIR / "storage" / "reports"))
    S3_ENDPOINT_URL: str = ""  # e.g. http://minio:9000 ; empty for AWS S3
    S3_BUCKET: str = "parakhmaan"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"
    FILE_URL_TTL_SECONDS: int = 3600
    MAX_IMAGE_MB: int = 25
    MAX_VIDEO_MB: int = 250
    MAX_IMAGE_PIXELS: int = 40_000_000  # rejects decompression bombs

    # Background jobs: Redis URL enables the RQ worker; empty runs jobs in-process (development)
    REDIS_URL: str = ""
    # "auto" (RQ when REDIS_URL is set, otherwise a background thread) or "eager" (inline; tests)
    JOB_MODE: str = "auto"
    JOB_QUEUE_NAME: str = "parakhmaan"
    JOB_TIMEOUT_SECONDS: int = 1800

    # Governed learning loop (Phase B)
    LEARNING_CLASSES: str = "scratch,crack,dent,discolouration"  # YOLO class order for datasets / training
    REVIEW_UNCERTAIN_LOW: float = 0.30   # detections in this confidence band go to review
    REVIEW_UNCERTAIN_HIGH: float = 0.60
    REVIEW_AUDIT_RATE: float = 0.02      # share of PASS images sampled to catch missed defects
    REVIEW_DRIFT_AUDIT_RATE: float = 0.20  # audit rate at stations whose input distribution drifted
    SPLIT_VAL_FRACTION: float = 0.15
    SPLIT_TEST_FRACTION: float = 0.15    # sticky "golden" test set, never used for training
    TRAIN_EPOCHS: int = 15
    TRAIN_IMGSZ: int = 320
    TRAIN_BATCH: int = 8
    TRAIN_DEVICE: str = "cpu"
    TRAIN_BASE_WEIGHTS: str = "yolov8n.pt"  # used when the active model has no .pt weights to warm-start from
    AUTO_TRAIN_MIN_NEW_VERIFIED: int = 0  # >0: queue dataset build + training after this many new verified images
    GATE_MAP_TOLERANCE: float = 0.0       # candidate mAP@0.5 may not drop more than this vs the active model
    GATE_MAX_CLASS_RECALL_DROP: float = 0.02
    GATE_MIN_CLASS_SUPPORT: int = 3       # classes with fewer test labels are reported, not gated
    GATE_CRITICAL_CLASS: str = "CRACK"
    GATE_CRITICAL_MIN_RECALL: float = 0.5
    GATE_MAX_LATENCY_RATIO: float = 1.5
    GATE_MIN_TEST_IMAGES: int = 10
    DRIFT_PSI_WATCH: float = 0.10
    DRIFT_PSI_ALERT: float = 0.25

    # Edge node (python -m uvicorn app.edge.main:app): runs inference locally and syncs to the central API
    EDGE_CENTRAL_URL: str = "http://localhost:8080"
    EDGE_DEVICE_KEY: str = ""
    EDGE_QUEUE_DB: str = str(BASE_DIR / "storage" / "edge_outbox.db")
    EDGE_SYNC_INTERVAL_SECONDS: float = 5.0
    EDGE_SYNC_BATCH: int = 10
    EDGE_KEEP_SYNCED: int = 500  # synced items retained locally for inspection
    EDGE_MODEL_CHECK_SECONDS: float = 300.0  # how often the node asks for the organisation's active model
    EDGE_MODEL_DIR: str = str(BASE_DIR / "storage" / "edge_models")

    # LLM (Configurable local provider)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5:7b")

    # Defect Inspection mode
    # DEFECT_DETECTOR_BACKEND: "hybrid" (ONNX model if present + OpenCV), "opencv", or "onnx"
    DEFECT_DETECTOR_BACKEND: str = os.getenv("DEFECT_DETECTOR_BACKEND", "hybrid")
    # Optional YOLOv8-style ONNX export (relative paths resolve against the backend folder);
    # classes come from DEFECT_MODEL_CLASSES or a .names file next to the model
    DEFECT_MODEL_PATH: str = os.getenv("DEFECT_MODEL_PATH", "")
    DEFECT_MODEL_CLASSES: str = os.getenv("DEFECT_MODEL_CLASSES", "")
    # 0 = detect the export's fixed input size automatically
    DEFECT_MODEL_INPUT_SIZE: int = int(os.getenv("DEFECT_MODEL_INPUT_SIZE", "0"))
    DEFECT_MODEL_CONF_THRESHOLD: float = float(os.getenv("DEFECT_MODEL_CONF_THRESHOLD", "0.35"))
    DEFECT_SAMPLES_DIR: str = os.getenv("DEFECT_SAMPLES_DIR", str(BASE_DIR / "storage" / "defect_samples"))

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        case_sensitive = True
        # Real environment variables (docker-compose, shell) take precedence over this file.
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"

settings = Settings()

def validate_settings() -> None:
    """Fail fast instead of running a production deployment with development conveniences."""
    if not settings.is_production:
        return
    problems = []
    if settings.SECRET_KEY == DEV_SECRET_KEY or len(settings.SECRET_KEY) < 32:
        problems.append("SECRET_KEY must be set to a random value of at least 32 characters")
    if "*" in settings.cors_origins:
        problems.append("CORS_ORIGINS must list explicit origins, not '*'")
    if settings.SEED_DEMO_DATA:
        problems.append("SEED_DEMO_DATA must be false")
    if problems:
        raise RuntimeError("Insecure production configuration: " + "; ".join(problems))

def resolve_backend_path(path: str) -> str:
    """Absolute paths are kept; relative ones are anchored at the backend folder, not the CWD."""
    if not path:
        return path
    p = Path(path)
    return str(p if p.is_absolute() else BASE_DIR / p)

# Ensure storage directories exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.REPORTS_DIR, exist_ok=True)
