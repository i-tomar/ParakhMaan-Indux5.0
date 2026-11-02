import io
import os
import zipfile

import cv2
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.all_models import (
    DatasetVersion, Image, Inspection, ModelEvent, ModelVersion, Organization, ReviewTask, ShadowPrediction, User
)
from app.services.defect_detection_service import synthesize_surface_sample
from app.services.learning import datasets
from app.services.learning.drift import classify, psi
from app.services.learning.sampler import assess
from app.services.learning.shadow import compare
from app.services.learning.training import gate_decision
from tests.helpers import client_for

ADMIN = client_for("ADMIN")
MANAGER = client_for("QUALITY_MANAGER")
OPERATOR = client_for("OPERATOR")
AUDITOR = client_for("AUDITOR")

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "models", "best.onnx")
PT_PATH = os.path.splitext(MODEL_PATH)[0] + ".pt"
requires_model = pytest.mark.skipif(not os.path.exists(MODEL_PATH), reason="trained ONNX model not present")


def _jpeg(defects=()) -> bytes:
    return cv2.imencode(".jpg", synthesize_surface_sample(list(defects)))[1].tobytes()


def _new_org(slug: str):
    """Isolated organisation with its own manager and admin, so registry tests don't affect others."""
    db = SessionLocal()
    org = Organization(name=slug, slug=slug)
    db.add(org)
    db.commit()
    users = {}
    for role in ("ADMIN", "QUALITY_MANAGER"):
        u = User(email=f"{role.lower()}@{slug}.test", full_name=f"{slug} {role}", role=role, organization_id=org.id,
                 hashed_password=get_password_hash("Password1234"))
        db.add(u)
        db.commit()
        users[role] = TestClient(app, headers={"Authorization": f"Bearer {create_access_token(u.id, role)}"})
    org_id = org.id
    db.close()
    return org_id, users


def _analyze(client, defects=(), batch=None) -> dict:
    insp = client.post("/api/v1/defects/inspections", json={"product_name": "Phase B Panel", "batch_code": batch}).json()
    res = client.post(f"/api/v1/defects/inspections/{insp['id']}/analyze",
                      files={"file": ("p.jpg", _jpeg(defects), "image/jpeg")})
    assert res.status_code == 200, res.text
    return {"inspection": insp, **res.json()}


# ---------------------------------------------------------------- sampler
def test_sampler_reasons_and_priorities():
    base = {"backend": "ONNX+OPENCV", "exposure_ok": True}
    uncertain = [{"defect_type": "SCRATCH", "confidence": 0.45, "detector": "ONNX+OPENCV"}]
    p, reasons = assess(uncertain, base, "img-1")
    assert [r["code"] for r in reasons] == ["UNCERTAIN"] and p >= 4

    single_engine = [{"defect_type": "CRACK", "confidence": 0.9, "detector": "OPENCV"}]
    assert [r["code"] for r in assess(single_engine, base, "img-2")[1]] == ["DISAGREEMENT"]
    # Dimensional anomalies are geometry rules, not a model class: no disagreement / unknown-class task
    assert assess([{"defect_type": "DIMENSIONAL_ANOMALY", "confidence": 0.9, "detector": "OPENCV"}], base, "img-3")[1] == []

    unknown = [{"defect_type": "PITTING", "confidence": 0.9, "detector": "ONNX"}]
    assert "UNKNOWN_CLASS" in [r["code"] for r in assess(unknown, base, "img-4")[1]]
    assert "QUALITY" in [r["code"] for r in assess([], {**base, "exposure_ok": False}, "img-5")[1]]
    assert "DRIFT" in [r["code"] for r in assess(single_engine, base, "img-6", drift_status="ALERT")[1]]


def test_audit_sampling_is_deterministic_and_respects_rate(monkeypatch):
    clean = {"backend": "OPENCV", "exposure_ok": True}
    monkeypatch.setattr(settings, "REVIEW_AUDIT_RATE", 0.1)
    picked = [i for i in range(2000) if assess([], clean, f"image-{i}")[1]]
    assert 120 < len(picked) < 280  # ~10%
    assert picked == [i for i in range(2000) if assess([], clean, f"image-{i}")[1]]
    monkeypatch.setattr(settings, "REVIEW_DRIFT_AUDIT_RATE", 1.0)
    assert assess([], clean, "image-1", drift_status="WATCH")[1][0]["code"] == "AUDIT"


# ---------------------------------------------------------------- drift / gate / shadow units
def test_psi_and_drift_classification():
    assert psi([50, 50, 0], [50, 50, 0]) == 0.0
    assert psi([90, 10], [10, 90]) > settings.DRIFT_PSI_ALERT
    assert classify(0.05) == "OK" and classify(0.15) == "WATCH" and classify(0.4) == "ALERT"


def _metrics(map50, recalls, latency=100.0):
    return {"map50": map50, "avg_latency_ms": latency,
            "per_class": {k: {"gt": 10, "recall": v, "precision": 0.8} for k, v in recalls.items()}}


def test_gate_decision_rules():
    champion = _metrics(0.60, {"SCRATCH": 0.70, "CRACK": 0.60})
    passed = gate_decision(_metrics(0.65, {"SCRATCH": 0.72, "CRACK": 0.62}), champion, test_images=40)
    assert passed["passed"] is True

    worse_map = gate_decision(_metrics(0.55, {"SCRATCH": 0.72, "CRACK": 0.62}), champion, 40)
    assert not worse_map["passed"] and "map50_not_worse" in [c["name"] for c in worse_map["checks"] if not c["passed"]]

    recall_drop = gate_decision(_metrics(0.70, {"SCRATCH": 0.60, "CRACK": 0.62}), champion, 40)
    assert [c["name"] for c in recall_drop["checks"] if not c["passed"]] == ["recall_scratch"]

    weak_crack = gate_decision(_metrics(0.70, {"SCRATCH": 0.72, "CRACK": 0.40}), None, 40)
    assert "critical_class_recall" in [c["name"] for c in weak_crack["checks"] if not c["passed"]]

    tiny = gate_decision(_metrics(0.90, {"SCRATCH": 0.9, "CRACK": 0.9}), champion, test_images=3)
    assert "golden_set_size" in [c["name"] for c in tiny["checks"] if not c["passed"]]

    slow = gate_decision(_metrics(0.70, {"SCRATCH": 0.72, "CRACK": 0.62}, latency=200), champion, 40)
    assert "latency" in [c["name"] for c in slow["checks"] if not c["passed"]]


def test_shadow_comparison_matching():
    a = [{"defect_type": "SCRATCH", "bbox": [0, 0, 100, 10], "confidence": 0.9}]
    b = [{"defect_type": "SCRATCH", "bbox": [5, 0, 100, 12], "confidence": 0.8},
         {"defect_type": "CRACK", "bbox": [200, 200, 260, 260], "confidence": 0.7}]
    c = compare(a, b)
    assert c == {"matched": 1, "champion_only": 0, "shadow_only": 1, "agreement": 0.5}
    assert compare([], [])["agreement"] == 1.0


# ---------------------------------------------------------------- review loop
def test_review_task_annotation_and_verification(monkeypatch):
    monkeypatch.setattr(settings, "REVIEW_AUDIT_RATE", 1.0)  # clean result -> audit task
    res = _analyze(OPERATOR, defects=(), batch="LOT-B1")
    image_id = res["image"]["id"]
    queue = OPERATOR.get("/api/v1/review/queue").json()
    task = next(t for t in queue if t["image_id"] == image_id)
    assert task["reasons"][0]["code"] == "AUDIT"
    detail = OPERATOR.get(f"/api/v1/review/tasks/{task['id']}").json()
    assert detail["image_size"] == [960, 720] and detail["image_url"]

    url = f"/api/v1/review/images/{image_id}/annotations"
    assert OPERATOR.post(url, json={"defect_type": "DENT", "bbox": [10, 10, 5000, 5000]}).status_code == 400
    assert AUDITOR.post(url, json={"defect_type": "DENT", "bbox": [10, 10, 80, 80]}).status_code == 403
    drawn = OPERATOR.post(url, json={"defect_type": "dent", "bbox": [100, 120, 220, 230], "note": "missed"})
    assert drawn.status_code == 201
    assert drawn.json()["detector"] == "HUMAN" and drawn.json()["reviewer_status"] == "CONFIRMED"
    # The missed defect changes the outcome of a clean inspection
    assert OPERATOR.get(f"/api/v1/defects/inspections/{res['inspection']['id']}").json()["overall_outcome"] != "PASS"

    done = OPERATOR.post(f"/api/v1/review/images/{image_id}/complete", json={}).json()
    assert done["review_status"] == "VERIFIED" and done["dataset_split"] in ("train", "val", "test")
    assert all(t["image_id"] != image_id for t in OPERATOR.get("/api/v1/review/queue").json())

    db = SessionLocal()
    img = db.get(Image, image_id)
    assert img.review_status == "VERIFIED" and img.reviewed_by_id
    db.close()


def test_complete_requires_resolving_pending_when_requested():
    res = _analyze(OPERATOR, defects=("SCRATCH",))
    image_id = res["image"]["id"]
    blocked = OPERATOR.post(f"/api/v1/review/images/{image_id}/complete", json={"accept_pending": False})
    assert blocked.status_code == 409
    for d in res["detections"]:
        OPERATOR.post(f"/api/v1/defects/detections/{d['id']}/feedback", json={"action": "REJECT"})
    assert OPERATOR.post(f"/api/v1/review/images/{image_id}/complete", json={"accept_pending": False}).status_code == 200


def test_only_reviewer_boxes_can_be_deleted():
    res = _analyze(OPERATOR, defects=("CRACK",))
    model_det = res["detections"][0]["id"]
    assert OPERATOR.delete(f"/api/v1/review/annotations/{model_det}").status_code == 400
    drawn = OPERATOR.post(f"/api/v1/review/images/{res['image']['id']}/annotations",
                          json={"defect_type": "SCRATCH", "bbox": [10, 10, 300, 40]}).json()
    assert OPERATOR.delete(f"/api/v1/review/annotations/{drawn['id']}").status_code == 204


def test_review_queue_is_organisation_scoped(monkeypatch):
    monkeypatch.setattr(settings, "REVIEW_AUDIT_RATE", 1.0)
    res = _analyze(OPERATOR)
    _, other = _new_org("review-iso")
    assert all(t["image_id"] != res["image"]["id"] for t in other["ADMIN"].get("/api/v1/review/queue").json())
    assert other["ADMIN"].post(f"/api/v1/review/images/{res['image']['id']}/complete", json={}).status_code == 404


# ---------------------------------------------------------------- datasets
def test_splits_are_sticky_and_grouped_by_batch(monkeypatch):
    db = SessionLocal()
    org = db.query(Organization).filter(Organization.slug == "default").first()
    insp_a = Inspection(inspection_number="SPLIT-A", inspection_mode="DEFECT", organization_id=org.id, batch_code="LOT-SAME", category="X")
    insp_b = Inspection(inspection_number="SPLIT-B", inspection_mode="DEFECT", organization_id=org.id, batch_code="LOT-SAME", category="X")
    db.add_all([insp_a, insp_b])
    db.commit()
    img_a = Image(inspection_id=insp_a.id, file_path="x", original_filename="a.jpg")
    img_b = Image(inspection_id=insp_b.id, file_path="y", original_filename="b.jpg")
    first = datasets.assign_split(img_a, insp_a)
    assert datasets.assign_split(img_b, insp_b) == first  # same batch -> same split (no leakage)
    monkeypatch.setattr(settings, "SPLIT_TEST_FRACTION", 0.0 if first == "test" else 1.0)
    assert datasets.assign_split(img_a, insp_a) == first  # once assigned, never moves
    db.rollback()
    db.close()


def test_dataset_build_exports_verified_labels_only():
    org_id, users = _new_org("dataset-org")
    mgr = users["QUALITY_MANAGER"]
    verified = _analyze(mgr, defects=("SCRATCH",), batch="LOT-D1")
    for d in verified["detections"]:
        mgr.post(f"/api/v1/defects/detections/{d['id']}/feedback", json={"action": "CONFIRM"})
    mgr.post(f"/api/v1/review/images/{verified['image']['id']}/annotations",
             json={"defect_type": "DENT", "bbox": [100, 100, 200, 200]})
    mgr.post(f"/api/v1/review/images/{verified['image']['id']}/complete", json={})
    rejected = _analyze(mgr, defects=("CRACK",), batch="LOT-D2")
    for d in rejected["detections"]:
        mgr.post(f"/api/v1/defects/detections/{d['id']}/feedback", json={"action": "REJECT"})
    mgr.post(f"/api/v1/review/images/{rejected['image']['id']}/complete", json={})
    _analyze(mgr, defects=("CRACK",), batch="LOT-D3")  # never verified -> excluded

    job = mgr.post("/api/v1/learning/datasets").json()
    assert job["status"] == "SUCCEEDED", job
    ds = mgr.get("/api/v1/learning/datasets").json()[0]
    assert ds["status"] == "READY" and ds["image_count"] == 2
    assert ds["class_counts"]["dent"] == 1 and ds["class_counts"]["crack"] == 0
    zip_bytes = mgr.get(f"/api/v1/learning/datasets/{ds['id']}/download").content
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "data.yaml" in names and "manifest.json" in names
        label_files = [n for n in names if n.startswith("labels/") and n.endswith(".txt")]
        rows = [r for n in label_files for r in zf.read(n).decode().splitlines() if r]
        assert len(rows) == ds["label_count"]
        for r in rows:
            cls, cx, cy, w, h = r.split()
            assert 0 <= int(cls) < 4 and all(0 <= float(v) <= 1 for v in (cx, cy, w, h))
    assert OPERATOR.post("/api/v1/learning/datasets").status_code == 403


# ---------------------------------------------------------------- registry governance
def _register(org_id: str, version: int, status: str, onnx_key="models/fake.onnx", gate_passed=None) -> str:
    db = SessionLocal()
    mv = ModelVersion(organization_id=org_id, version=version, name=f"v{version}", status=status, onnx_key=onnx_key,
                      classes=["scratch", "crack", "dent", "discolouration"],
                      gate_report={"passed": gate_passed} if gate_passed is not None else None)
    db.add(mv)
    db.commit()
    mv_id = mv.id
    db.close()
    return mv_id


def test_promotion_requires_gate_or_admin_override_and_rollback_works():
    org_id, users = _new_org("registry-org")
    mgr, admin = users["QUALITY_MANAGER"], users["ADMIN"]
    v1 = _register(org_id, 1, "ACTIVE")
    failed = _register(org_id, 2, "GATE_FAILED", gate_passed=False)
    passed = _register(org_id, 3, "GATE_PASSED", gate_passed=True)

    assert mgr.post(f"/api/v1/learning/models/{failed}/promote", json={}).status_code == 403
    assert admin.post(f"/api/v1/learning/models/{failed}/promote", json={}).status_code == 400  # reason required
    assert OPERATOR.post(f"/api/v1/learning/models/{passed}/promote", json={}).status_code == 403

    assert mgr.post(f"/api/v1/learning/models/{passed}/shadow", json={}).json()["status"] == "SHADOW"
    promoted = mgr.post(f"/api/v1/learning/models/{passed}/promote", json={})
    assert promoted.status_code == 200 and promoted.json()["status"] == "ACTIVE"
    models = {m["id"]: m["status"] for m in mgr.get("/api/v1/learning/models").json()}
    assert models[v1] == "RETIRED" and models[passed] == "ACTIVE"

    back = mgr.post(f"/api/v1/learning/models/{v1}/rollback")
    assert back.status_code == 200 and back.json()["status"] == "ACTIVE"
    assert {m["id"]: m["status"] for m in mgr.get("/api/v1/learning/models").json()}[passed] == "RETIRED"
    assert mgr.post(f"/api/v1/learning/models/{failed}/rollback").status_code == 409

    forced = admin.post(f"/api/v1/learning/models/{failed}/promote",
                        json={"override_reason": "Accepted risk for line trial on station 3"})
    assert forced.status_code == 200
    db = SessionLocal()
    types = [e.event_type for e in db.query(ModelEvent).filter(ModelEvent.organization_id == org_id)]
    db.close()
    assert types.count("MODEL_PROMOTED") == 2 and "MODEL_ROLLBACK" in types and "SHADOW_STARTED" in types
    assert AUDITOR.get("/api/v1/learning/models").status_code == 200
    assert OPERATOR.get("/api/v1/learning/models").status_code == 403


@requires_model
def test_shadow_model_runs_on_live_traffic_without_changing_outcomes():
    from app.services.learning.registry import sha256_of
    from app.services.storage_service import storage_service

    org_id, users = _new_org("shadow-org")
    mgr = users["QUALITY_MANAGER"]
    key = storage_service.put_file(f"models/{org_id}/shadow.onnx", MODEL_PATH)
    db = SessionLocal()
    db.add(ModelVersion(organization_id=org_id, version=1, name="v1", status="SHADOW", onnx_key=key,
                        sha256=sha256_of(MODEL_PATH), classes=["scratch", "crack", "dent", "discolouration"]))
    db.commit()
    db.close()
    res = _analyze(mgr, defects=("DISCOLOURATION",))
    assert all(d["detector"] == "OPENCV" for d in res["detections"])  # active detector unchanged (no active model)
    db = SessionLocal()
    rows = db.query(ShadowPrediction).filter(ShadowPrediction.image_id == res["image"]["id"]).all()
    db.close()
    assert len(rows) == 1 and "agreement" in rows[0].agreement
    shadow = next(m for m in mgr.get("/api/v1/learning/models").json() if m["status"] == "SHADOW")
    assert mgr.get(f"/api/v1/learning/models/{shadow['id']}").json()["shadow_stats"]["images"] == 1


@requires_model
def test_edge_node_pulls_active_model_after_promotion():
    import app.edge.main as edge
    from app.services.learning.registry import sha256_of
    from app.services.storage_service import storage_service

    org_id, users = _new_org("edge-model-org")
    admin = users["ADMIN"]
    key = storage_service.put_file(f"models/{org_id}/v1.onnx", MODEL_PATH)
    db = SessionLocal()
    db.add(ModelVersion(organization_id=org_id, version=1, name="v1", status="ACTIVE", onnx_key=key,
                        sha256=sha256_of(MODEL_PATH), classes=["scratch", "crack", "dent", "discolouration"]))
    db.commit()
    db.close()
    device_key = admin.post("/api/v1/admin/devices", json={"name": "Model Cam"}).json()["device_key"]
    settings.EDGE_DEVICE_KEY = device_key
    try:
        central = TestClient(app)
        original = edge.current_detector()
        assert edge.check_model_update(central) is True
        assert edge.current_detector() is not original and edge._state["model"]["name"] == "v1"
        assert edge.check_model_update(central) is False  # unchanged -> no re-download
    finally:
        settings.EDGE_DEVICE_KEY = ""
        with edge._detector_lock:
            edge._detector = original
        edge._state["model"] = None


# ---------------------------------------------------------------- training (real, short)
@requires_model
def test_training_job_produces_gated_candidate(monkeypatch):
    pytest.importorskip("ultralytics")
    org_id, users = _new_org("training-org")
    admin = users["ADMIN"]
    monkeypatch.setattr(settings, "TRAIN_EPOCHS", 1)
    monkeypatch.setattr(settings, "TRAIN_BASE_WEIGHTS", PT_PATH)
    monkeypatch.setattr(settings, "GATE_MIN_TEST_IMAGES", 1)
    assert admin.post("/api/v1/learning/demo/seed-reviewed", json={"count": 24}).status_code == 200
    job = admin.post("/api/v1/learning/models/train", json={}).json()
    assert job["status"] == "SUCCEEDED", job.get("error")
    models = admin.get("/api/v1/learning/models").json()
    cand = models[0]
    assert cand["status"] in ("GATE_PASSED", "GATE_FAILED") and cand["gate_report"]["checks"]
    assert cand["sha256"] and cand["model_card"]["dataset_version"] == 1
    db = SessionLocal()
    assert db.query(DatasetVersion).filter(DatasetVersion.organization_id == org_id, DatasetVersion.status == "READY").count() == 1
    db.close()
