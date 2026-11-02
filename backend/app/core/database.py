import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import BASE_DIR, settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    # Connection pooling for PostgreSQL; pre-ping drops connections the server has closed.
    **({} if _is_sqlite else {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}),
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

BASELINE_REVISION = "0001"


def _alembic_config():
    from alembic.config import Config

    cfg = Config(os.path.join(BASE_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BASE_DIR, "alembic"))
    cfg.attributes["url"] = settings.DATABASE_URL
    cfg.attributes["configure_logger"] = False
    return cfg


def migrate_database() -> None:
    """
    Brings the schema to the latest Alembic revision. Databases created before Alembic was
    introduced (via create_all) are stamped at the baseline first, then upgraded.
    """
    from alembic import command

    cfg = _alembic_config()
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "inspections" in tables:
        columns = {c["name"] for c in inspect(engine).get_columns("inspections")}
        with engine.begin() as conn:
            if "inspection_mode" not in columns:
                conn.execute(text("ALTER TABLE inspections ADD COLUMN inspection_mode VARCHAR(30) DEFAULT 'LEGAL_METROLOGY'"))
            conn.execute(text("UPDATE inspections SET inspection_mode = 'LEGAL_METROLOGY' WHERE inspection_mode IS NULL"))
            if "defect_detections" not in tables:
                # Baseline shape only; later revisions add their own columns.
                from sqlalchemy import MetaData, Table
                current = Base.metadata.tables["defect_detections"]
                baseline_cols = [c._copy() for c in current.columns if c.name != "model_version"]
                Table("defect_detections", MetaData(), *baseline_cols).create(conn)
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
