from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings

# For SQLite, enable check_same_thread=False
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# create_all() never alters existing tables, so columns added after a database
# was first created are back-filled here: (table, column, DDL type + default).
_ADDED_COLUMNS = [
    ("inspections", "inspection_mode", "VARCHAR(30) DEFAULT 'LEGAL_METROLOGY'"),
    ("defect_detections", "unit_id", "VARCHAR(36)"),
    ("defect_detections", "model_version", "VARCHAR(120)"),
    ("defect_detections", "length_mm", "FLOAT"),
    ("defect_detections", "width_mm", "FLOAT"),
    ("defect_detections", "area_mm2", "FLOAT"),
]

def run_lightweight_migrations() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in existing_tables:
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column not in columns:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        if "inspections" in existing_tables:
            conn.execute(text(
                "UPDATE inspections SET inspection_mode = 'LEGAL_METROLOGY' WHERE inspection_mode IS NULL"
            ))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
