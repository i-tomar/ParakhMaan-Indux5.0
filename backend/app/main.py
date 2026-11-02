import os
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base, run_lightweight_migrations
from app.api import auth, inspections, reviews, reports, dashboard, demo, rag, llm, tools, defects
from app.api import analytics_api, edge, files, learning, live, metrology_api, production
from app.models import industrial  # noqa: F401  (registers the manufacturing tables)

# Create database tables
Base.metadata.create_all(bind=engine)
run_lightweight_migrations()

app = FastAPI(
    title="ParakhMaan Industrial Visual Inspection Platform",
    description="AI and computer-vision surface and product defect inspection, with the Legal Metrology rule engine as a separate optional module",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.BACKEND_CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Stored images and PDFs are served only through the authenticated /files router. There is
# deliberately no public static mount: STORAGE_DIR can hold the database, models and part images.
os.makedirs(settings.STORAGE_DIR, exist_ok=True)

# Login is the only unauthenticated API; everything else requires a token.
app.include_router(auth.router, prefix=settings.API_V1_STR)
_protected = [Depends(auth.get_current_user)]
for module in (inspections, reviews, reports, dashboard, demo, rag, llm, tools, defects,
               analytics_api, edge, files, learning, metrology_api, production):
    app.include_router(module.router, prefix=settings.API_V1_STR, dependencies=_protected)
app.include_router(live.router, prefix=settings.API_V1_STR)  # checks its own token (REST + WebSocket)

@app.get("/api/health")
def health_check():
    from app.services.inference.engine import engine
    status = engine.status()
    return {
        "status": "healthy",
        "service": "ParakhMaan Industrial Inspection (with Legal Metrology module)",
        "version": settings.VERSION,
        "rule_engine": "ACTIVE",
        "segmentation_model": status["segmentation"]["version"] or "NOT LOADED",
        "anomaly_products": status["anomaly"]["products"],
        "storage": "ONLINE",
    }


@app.on_event("startup")
def startup_event():
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        auth.ensure_demo_accounts(db)
        production.ensure_products_for_models(db)
        if settings.DEMO_MODE:  # sample records never appear unless demo mode is switched on
            demo.seed_demo_data(db)
            defects.seed_defect_demo_data(db)
    except Exception:
        logging.getLogger(__name__).exception("Startup seeding failed")
    finally:
        db.close()
