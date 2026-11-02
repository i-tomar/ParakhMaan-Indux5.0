import os
import secrets
import warnings
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "ParakhMaan Industrial Visual Inspection Platform"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")  # development | production

    # Security. No built-in secret: production refuses to start without one (see check below).
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    AUTH_REQUIRED: bool = os.getenv("AUTH_REQUIRED", "true").lower() == "true"
    # Demo mode seeds demo accounts using DEMO_PASSWORD. It is off unless explicitly enabled.
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"
    DEMO_PASSWORD: str = os.getenv("DEMO_PASSWORD", "")
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "25"))
    MAX_VIDEO_MB: int = int(os.getenv("MAX_VIDEO_MB", "300"))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/legal_metrology.db")
    
    # Storage
    STORAGE_DIR: str = os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))
    REPORTS_DIR: str = os.getenv("REPORTS_DIR", str(BASE_DIR / "storage" / "reports"))
    
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

    # Inspection engine (ONNX Runtime). Empty paths mean "stream not available", shown in the UI.
    SEG_MODEL_PATH: str = os.getenv("SEG_MODEL_PATH", "storage/models/segmentation/production.onnx")
    SEG_MODEL_VERSION: str = os.getenv("SEG_MODEL_VERSION", "")
    SEG_CONF_THRESHOLD: float = float(os.getenv("SEG_CONF_THRESHOLD", "0.25"))
    ANOMALY_BACKBONE_PATH: str = os.getenv("ANOMALY_BACKBONE_PATH", "storage/models/anomaly/backbone.onnx")
    ANOMALY_PRODUCTS_DIR: str = os.getenv("ANOMALY_PRODUCTS_DIR", "storage/models/anomaly/products")
    PRODUCT_ID_MIN_SIMILARITY: float = float(os.getenv("PRODUCT_ID_MIN_SIMILARITY", "0.85"))
    INSPECT_REVIEW_CONFIDENCE: float = float(os.getenv("INSPECT_REVIEW_CONFIDENCE", "0.5"))
    
    # CORS: comma separated list, read in main.py
    BACKEND_CORS_ORIGINS: str = os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    class Config:
        case_sensitive = True
        # Real environment variables (docker-compose, shell) take precedence over this file.
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"

settings = Settings()

if not settings.SECRET_KEY:
    if settings.ENVIRONMENT == "production":
        raise RuntimeError("SECRET_KEY must be set when ENVIRONMENT=production")
    # Tokens stop working on restart, which is acceptable outside production and safer than a shared default.
    settings.SECRET_KEY = secrets.token_urlsafe(48)
    warnings.warn("SECRET_KEY not set: using a random per-process key")

def resolve_backend_path(path: str) -> str:
    """Absolute paths are kept; relative ones are anchored at the backend folder, not the CWD."""
    if not path:
        return path
    p = Path(path)
    return str(p if p.is_absolute() else BASE_DIR / p)

# Ensure storage directories exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.REPORTS_DIR, exist_ok=True)
