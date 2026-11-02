"""Startup data: optional first administrator and (development only) demo organisation and users."""
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import ADMIN, AUDITOR, OPERATOR, QUALITY_MANAGER
from app.core.security import get_password_hash
from app.models.all_models import Organization, Plant, Product, ProductionLine, Station, User

log = logging.getLogger(__name__)

DEMO_USERS = [
    {"email": "admin@parakhmaan.local", "full_name": "Plant Administrator", "role": ADMIN},
    {"email": "manager@parakhmaan.local", "full_name": "Quality Manager", "role": QUALITY_MANAGER},
    {"email": "operator@parakhmaan.local", "full_name": "Line Operator", "role": OPERATOR},
    {"email": "auditor@parakhmaan.local", "full_name": "Quality Auditor", "role": AUDITOR},
]

DEMO_STRUCTURE = {
    "plant": ("Pune Plant 1", "Chakan MIDC, Pune"),
    "lines": {
        "Press Line 2": ["Final QC", "Post-Press Inspection"],
        "Finishing Line 1": ["Coating QC"],
        "CNC Cell 3": ["Dimensional Check"],
    },
    "products": [
        ("CRS-PANEL-01", "Cold-Rolled Steel Panel", "METAL_SHEET", "CRCA Steel"),
        ("ALU-COVER-04", "Aluminium Housing Cover", "DIE_CASTING", "ADC12 Aluminium"),
        ("BRKT-C11", "Machined Bracket", "MACHINED_PART", "EN8 Steel"),
    ],
}


def get_or_create_default_org(db: Session) -> Organization:
    org = db.query(Organization).filter(Organization.slug == "default").first()
    if not org:
        org = Organization(name="Default Organization", slug="default")
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def _ensure_user(db: Session, org: Organization, email: str, full_name: str, role: str, password: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, full_name=full_name, role=role, organization_id=org.id,
                    hashed_password=get_password_hash(password))
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _ensure_demo_structure(db: Session, org: Organization) -> None:
    plant_name, location = DEMO_STRUCTURE["plant"]
    plant = db.query(Plant).filter(Plant.organization_id == org.id, Plant.name == plant_name).first()
    if not plant:
        plant = Plant(organization_id=org.id, name=plant_name, location=location)
        db.add(plant)
        db.commit()
        db.refresh(plant)
    for line_name, stations in DEMO_STRUCTURE["lines"].items():
        line = db.query(ProductionLine).filter(ProductionLine.plant_id == plant.id, ProductionLine.name == line_name).first()
        if not line:
            line = ProductionLine(plant_id=plant.id, name=line_name)
            db.add(line)
            db.commit()
            db.refresh(line)
        for station_name in stations:
            if not db.query(Station).filter(Station.line_id == line.id, Station.name == station_name).first():
                db.add(Station(line_id=line.id, name=station_name))
    for sku, name, family, material in DEMO_STRUCTURE["products"]:
        if not db.query(Product).filter(Product.organization_id == org.id, Product.sku == sku).first():
            db.add(Product(organization_id=org.id, sku=sku, name=name, family=family, material=material))
    db.commit()


def _register_models(db: Session) -> None:
    """Each organisation without a model registry entry gets the configured model as its active v1."""
    from app.services.learning.registry import registry

    for org in db.query(Organization).all():
        try:
            registry.ensure_imported(db, org.id)
        except Exception as e:
            db.rollback()
            log.warning("Model import for organisation %s failed: %s", org.slug, e)


def run_bootstrap(db: Session) -> None:
    org = get_or_create_default_org(db)
    _register_models(db)

    if settings.BOOTSTRAP_ADMIN_EMAIL and settings.BOOTSTRAP_ADMIN_PASSWORD and db.query(User).count() == 0:
        _ensure_user(db, org, settings.BOOTSTRAP_ADMIN_EMAIL.lower(), "Administrator", ADMIN,
                     settings.BOOTSTRAP_ADMIN_PASSWORD)
        log.warning("Created bootstrap administrator %s", settings.BOOTSTRAP_ADMIN_EMAIL)

    if settings.is_production or not settings.SEED_DEMO_DATA:
        return

    users = {u["role"]: _ensure_user(db, org, u["email"], u["full_name"], u["role"], settings.DEMO_PASSWORD)
             for u in DEMO_USERS}
    _ensure_demo_structure(db, org)

    from app.api import demo, defects
    try:
        demo.seed_demo_data(db, users[OPERATOR])
    except Exception as e:  # demo data must never block startup
        log.warning("Legal metrology demo seeding failed: %s", e)
    try:
        defects.seed_defect_demo_data(db, users[OPERATOR])
    except Exception as e:
        log.warning("Defect demo seeding failed: %s", e)
