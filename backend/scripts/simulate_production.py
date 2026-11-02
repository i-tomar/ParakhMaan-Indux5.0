"""SIMULATED production run with a known injected fault.

Real held-out part images pass through the real inference and decision code. What is simulated is
the production context: machines, shifts, dates, and which image a machine "produced". One machine
receives extra defective parts, so analytics can be checked against a fault whose answer is known.
Every row is stored with is_synthetic=True and shown as SIMULATED.

    python -m scripts.simulate_production --product metal_nut --samples storage/demo_samples/metal_nut --units 240
"""
import argparse
import json
import os
import random
from datetime import datetime, timedelta, timezone

import cv2

from app.core.database import Base, SessionLocal, engine as db_engine, run_lightweight_migrations
from app.models import industrial  # noqa: F401
from app.models.all_models import DefectDetection, Inspection
from app.models.industrial import Batch, Machine, Product, ProductionLine, ProductionUnit, RejectEvent
from app.services.inspection_service import record_unit, run_inspection


def get_or_create(db, model, key: str, value: str, **fields):
    row = db.query(model).filter(getattr(model, key) == value).first()
    if row is None:
        row = model(**{key: value}, **fields)
        db.add(row)
        db.commit()
    return row


def reset_simulated(db) -> None:
    """Removes only rows this script created (source SIMULATED, inspection numbers SIM-...)."""
    units = db.query(ProductionUnit).filter(ProductionUnit.source == "SIMULATED", ProductionUnit.is_synthetic.is_(True)).all()
    unit_ids = [u.id for u in units]
    for start in range(0, len(unit_ids), 500):
        chunk = unit_ids[start:start + 500]
        db.query(RejectEvent).filter(RejectEvent.unit_id.in_(chunk)).delete(synchronize_session=False)
        db.query(DefectDetection).filter(DefectDetection.unit_id.in_(chunk)).delete(synchronize_session=False)
        db.query(ProductionUnit).filter(ProductionUnit.id.in_(chunk)).delete(synchronize_session=False)
    sim = db.query(Inspection).filter(Inspection.inspection_number.like("SIM-%")).all()
    for insp in sim:
        db.delete(insp)
    db.query(Batch).filter(Batch.code.like("SIM-%"), Batch.is_synthetic.is_(True)).delete(synchronize_session=False)
    db.commit()
    print(json.dumps({"reset_units": len(unit_ids), "reset_inspections": len(sim)}))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", required=True)
    ap.add_argument("--samples", required=True, help="folder with good/ and defect/ images")
    ap.add_argument("--units", type=int, default=240)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--base-defect-rate", type=float, default=0.08)
    ap.add_argument("--fault-defect-rate", type=float, default=0.45)
    ap.add_argument("--fault-machine", default="M-02")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--reset", action="store_true", help="delete earlier SIMULATED rows first (real rows are kept)")
    args = ap.parse_args()

    Base.metadata.create_all(bind=db_engine)
    run_lightweight_migrations()
    rng = random.Random(args.seed)
    db = SessionLocal()
    if args.reset:
        reset_simulated(db)
    product = db.query(Product).filter(Product.key == args.product).first()
    if product is None:
        raise SystemExit(f"Unknown product {args.product}: fit its anomaly model first")
    good = [os.path.join(args.samples, "good", n) for n in sorted(os.listdir(os.path.join(args.samples, "good")))]
    bad = [os.path.join(args.samples, "defect", n) for n in sorted(os.listdir(os.path.join(args.samples, "defect")))]
    line = get_or_create(db, ProductionLine, "code", "SIM-L1", name="Simulated Line 1")
    machines = [get_or_create(db, Machine, "code", code, name=f"Simulated machine {code}", line_id=line.id) for code in ("M-01", "M-02", "M-03")]
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%y%m%d%H%M")
    batches = [get_or_create(db, Batch, "code", f"SIM-{args.product[:6].upper()}-{stamp}-{i}", product_id=product.id, is_synthetic=True,
                             notes="Simulated batch") for i in range(1, 5)]

    shifts_for = {"A": 8, "B": 16, "C": 23}
    seen = {"units": 0, "bad_images": 0, "fault_machine_bad": 0}
    cache = {}
    for i in range(args.units):
        machine = rng.choice(machines)
        rate = args.fault_defect_rate if machine.code == args.fault_machine else args.base_defect_rate
        defective = rng.random() < rate
        path = rng.choice(bad if defective else good)
        image = cache.setdefault(path, cv2.imread(path))
        day = rng.randrange(args.days)
        shift = rng.choice("ABC")
        when = (now - timedelta(days=day)).replace(hour=shifts_for[shift], minute=rng.randrange(60))
        result = run_inspection(db, image, product)
        insp = Inspection(inspection_number=f"SIM-{stamp}-{i:05d}", inspection_mode="DEFECT", product_name=product.name,
                          category=product.category, notes="Simulated production unit", status="ANALYZED",
                          overall_outcome={"ACCEPT": "PASS", "REJECT": "DEFECTIVE"}.get(result["decision"], "REVIEW"), created_at=when)
        db.add(insp)
        db.flush()
        record_unit(db, result, image, batch=batches[day * len(batches) // args.days], machine=machine, line=line, source="SIMULATED",
                    is_synthetic=True, inspection_id=insp.id, when=when, shift=shift)
        seen["units"] += 1
        seen["bad_images"] += defective
        seen["fault_machine_bad"] += defective and machine.code == args.fault_machine
    db.close()
    print(json.dumps({**seen, "fault_machine": args.fault_machine, "note": "simulated context, real images and real inference"}))


if __name__ == "__main__":
    main()
