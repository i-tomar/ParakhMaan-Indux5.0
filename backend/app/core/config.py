import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Legal Metrology AI Compliance Platform"
    API_V1_STR: str = "/api/v1"
    VERSION: str = "1.0.0"
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "sih26034-legal-metrology-super-secret-key-2026")
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
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*"
    ]

    class Config:
        case_sensitive = True
        # Real environment variables (docker-compose, shell) take precedence over this file.
        env_file = str(BASE_DIR / ".env")
        extra = "ignore"

settings = Settings()

def resolve_backend_path(path: str) -> str:
    """Absolute paths are kept; relative ones are anchored at the backend folder, not the CWD."""
    if not path:
        return path
    p = Path(path)
    return str(p if p.is_absolute() else BASE_DIR / p)

# Ensure storage directories exist
os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.REPORTS_DIR, exist_ok=True)
