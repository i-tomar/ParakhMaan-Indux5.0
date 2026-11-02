import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings, validate_settings
from app.core.database import SessionLocal, engine, migrate_database
from app.api import (
    admin, auth, dashboard, defects, demo, edge, files, inspections, jobs, learning, llm, org, rag, reports, review,
    reviews, tools
)

log = logging.getLogger(__name__)

validate_settings()
if settings.AUTO_MIGRATE:
    migrate_database()


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.core.bootstrap import run_bootstrap

    db = SessionLocal()
    try:
        run_bootstrap(db)
    except Exception as e:  # bootstrap data must never prevent the API from starting
        log.warning("Startup bootstrap failed: %s", e)
    finally:
        db.close()
    yield


app = FastAPI(
    title="ParakhMaan Quality Inspection Platform",
    description="AI & computer-vision product defect inspection with an optional Legal Metrology compliance module",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-Key"],
)

for module in (auth, inspections, reviews, reports, dashboard, demo, rag, llm, tools, defects,
               files, org, admin, jobs, edge, review, learning):
    app.include_router(module.router, prefix=settings.API_V1_STR)


@app.get("/api/health")
def health_check():
    database = "ONLINE"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        database = "UNAVAILABLE"
    detector = defects.defect_detector.status()
    return {
        "status": "healthy" if database == "ONLINE" else "degraded",
        "service": "ParakhMaan Quality Inspection Platform (Legal Metrology module enabled)",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": f"{database} ({engine.dialect.name})",
        "storage": settings.STORAGE_BACKEND.upper(),
        "job_queue": "REDIS" if settings.REDIS_URL and settings.JOB_MODE == "auto" else settings.JOB_MODE.upper(),
        "rule_engine": "ACTIVE (40+ Statutory Rules)",
        "defect_detector": f"ACTIVE ({detector['backend']}, model {'loaded' if detector['model_loaded'] else 'not loaded'})",
    }
