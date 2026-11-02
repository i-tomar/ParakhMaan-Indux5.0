"""Continuous-learning guarantees: fixed holdout, stable dataset hash, gate refusal, rollback. Pareto."""
import uuid
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine as db_engine
from app.models import all_models, industrial  # noqa: F401  (register tables)
from app.models.industrial import DatasetSample, ModelVersion
from app.services.analytics.quality import pareto
from app.services.learning import service


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFECT_SAMPLES_DIR", str(tmp_path / "samples"))
    loaded = []
    monkeypatch.setattr(service.engine, "load_product", lambda key, path, version: loaded.append(version))
    monkeypatch.setattr(service.engine, "load_seg", lambda path, version: loaded.append(version))
    Base.metadata.create_all(bind=db_engine)
    session = SessionLocal()
    session.loaded = loaded
    yield session
    session.close()


def image(tmp_path, i: int) -> str:
    path = str(tmp_path / f"img_{i}.png")
    cv2.imwrite(path, np.full((16, 16, 3), i % 256, np.uint8) + np.uint8(i // 256))
    return path


def test_holdout_split_is_fixed_at_insertion_and_never_moves(db, tmp_path):
    key = f"p_{uuid.uuid4().hex[:8]}"
    for i in range(10):
        service.add_sample(db, key, "GOOD", image(tmp_path, i))
    first = {s.sha256: s.split for s in db.query(DatasetSample).filter(DatasetSample.product_key == key)}
    assert sum(v == "HOLDOUT" for v in first.values()) == 2  # every fifth sample
    assert service.add_sample(db, key, "GOOD", image(tmp_path, 3)) is None  # duplicate ignored
    for i in range(10, 20):
        service.add_sample(db, key, "GOOD", image(tmp_path, i))
    after = {s.sha256: s.split for s in db.query(DatasetSample).filter(DatasetSample.product_key == key)}
    assert all(after[h] == split for h, split in first.items())  # no earlier sample changed split


def test_dataset_version_hash_is_stable_and_changes_with_content(db, tmp_path):
    key = f"p_{uuid.uuid4().hex[:8]}"
    for i in range(6):
        service.add_sample(db, key, "GOOD", image(tmp_path, 100 + i))
    v1 = service.create_dataset_version(db, key)
    assert service.create_dataset_version(db, key).id == v1.id  # same content, same version
    service.add_sample(db, key, "DEFECTIVE", image(tmp_path, 200))
    v2 = service.create_dataset_version(db, key)
    assert v2.content_hash != v1.content_hash and v2.version == v1.version + 1


def _version(db, key, name, status="CANDIDATE", passed=True):
    row = ModelVersion(kind="ANOMALY", product_key=key, version=name, path=f"/nowhere/{name}", status=status,
                       metrics={}, gate_result={"passed": passed, "checks": [{"check": "image_auroc", "passed": passed}]})
    db.add(row)
    db.commit()
    return row


def test_gate_failure_refuses_promotion_and_keeps_production(db):
    key = f"p_{uuid.uuid4().hex[:8]}"
    prod = _version(db, key, "v1")
    service.promote(db, prod.id, "test")
    worse = _version(db, key, "v2", passed=False)
    with pytest.raises(PermissionError):
        service.promote(db, worse.id, "test")
    db.refresh(worse)
    assert worse.status == "REFUSED"
    assert service.production_model(db, "ANOMALY", key).version == "v1"


def test_rollback_returns_production_pointer_to_previous_version(db):
    key = f"p_{uuid.uuid4().hex[:8]}"
    service.promote(db, _version(db, key, "v1").id, "test")
    service.promote(db, _version(db, key, "v2").id, "test")
    assert service.production_model(db, "ANOMALY", key).version == "v2"
    service.rollback(db, "ANOMALY", key, "test")
    assert service.production_model(db, "ANOMALY", key).version == "v1"
    assert db.loaded[-1] == "v1"  # the engine was switched back, not only the database row
    with pytest.raises(ValueError):
        service.rollback(db, "ANOMALY", f"none_{key}", "test")


def test_pareto_ranks_and_accumulates():
    dets = [SimpleNamespace(defect_type=t) for t in ["SCRATCH"] * 5 + ["CRACK"] * 3 + ["DENT"] * 2]
    rows = pareto(dets)
    assert [r["defect_type"] for r in rows] == ["SCRATCH", "CRACK", "DENT"]
    assert [r["count"] for r in rows] == [5, 3, 2]
    assert [r["cumulative"] for r in rows] == [0.5, 0.8, 1.0]
