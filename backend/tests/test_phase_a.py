import hashlib
import io
import json
import os
import time

import cv2
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import config as config_module
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.all_models import Inspection, Organization, Station, User
from app.services.defect_detection_service import synthesize_surface_sample
from app.services.storage_service import _LocalBackend, storage_service
from tests.helpers import anonymous_client, client_for

ADMIN = client_for("ADMIN")
MANAGER = client_for("QUALITY_MANAGER")
OPERATOR = client_for("OPERATOR")
AUDITOR = client_for("AUDITOR")


def _jpeg(defects=("SCRATCH",)) -> bytes:
    return cv2.imencode(".jpg", synthesize_surface_sample(list(defects)))[1].tobytes()


def _new_inspection(client=OPERATOR) -> dict:
    resp = client.post("/api/v1/defects/inspections", json={"product_name": "Phase A Panel"})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------- authentication
def test_protected_endpoints_require_a_valid_token():
    anon = anonymous_client()
    for path in ("/api/v1/defects/inspections", "/api/v1/inspections", "/api/v1/dashboard/summary",
                 "/api/v1/tools/schedules", "/api/v1/org/tree", "/api/v1/auth/me"):
        assert anon.get(path).status_code == 401, path
    bad = TestClient(app, headers={"Authorization": "Bearer not-a-token"})
    assert bad.get("/api/v1/auth/me").status_code == 401
    assert anon.get("/api/health").status_code == 200


def test_login_rejects_wrong_password_and_rate_limits():
    anon = anonymous_client()
    email = "ratelimit@parakhmaan.local"
    db = SessionLocal()
    org = db.query(Organization).filter(Organization.slug == "default").first()
    db.add(User(email=email, full_name="Rate Limit", role="OPERATOR", organization_id=org.id,
                hashed_password=get_password_hash("CorrectHorse123")))
    db.commit()
    db.close()
    codes = [anon.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"}).status_code
             for _ in range(settings.LOGIN_MAX_ATTEMPTS + 1)]
    assert codes[:settings.LOGIN_MAX_ATTEMPTS] == [401] * settings.LOGIN_MAX_ATTEMPTS
    assert codes[-1] == 429


def test_legacy_hash_is_upgraded_and_plaintext_is_never_accepted():
    db = SessionLocal()
    org = db.query(Organization).filter(Organization.slug == "default").first()
    legacy = hashlib.sha256(("OldPassword1" + "sih26034_salt").encode()).hexdigest()
    db.add(User(email="legacy@parakhmaan.local", full_name="Legacy", role="INSPECTOR", organization_id=org.id,
                hashed_password=legacy))
    db.add(User(email="plain@parakhmaan.local", full_name="Plain", role="INSPECTOR", organization_id=org.id,
                hashed_password="demo"))
    db.commit()
    db.close()
    anon = anonymous_client()
    resp = anon.post("/api/v1/auth/login", json={"email": "legacy@parakhmaan.local", "password": "OldPassword1"})
    assert resp.status_code == 200
    assert resp.json()["user"]["role"] == "OPERATOR"  # legacy role mapped
    db = SessionLocal()
    assert db.query(User).filter(User.email == "legacy@parakhmaan.local").first().hashed_password.startswith("$2")
    db.close()
    assert anon.post("/api/v1/auth/login", json={"email": "plain@parakhmaan.local", "password": "demo"}).status_code == 401


def test_public_registration_is_gone():
    resp = anonymous_client().post("/api/v1/auth/register", json={
        "email": "x@y.com", "full_name": "X", "password": "whatever123", "role": "ADMIN"})
    assert resp.status_code in (404, 405)


# ---------------------------------------------------------------- RBAC
def test_role_permissions_are_enforced_server_side():
    insp = _new_inspection(OPERATOR)
    assert AUDITOR.post("/api/v1/defects/inspections", json={}).status_code == 403
    assert AUDITOR.get(f"/api/v1/defects/inspections/{insp['id']}").status_code == 200
    assert AUDITOR.get("/api/v1/defects/analytics").status_code == 200

    assert OPERATOR.get("/api/v1/defects/analytics").status_code == 403
    assert OPERATOR.post(f"/api/v1/defects/inspections/{insp['id']}/finalize", json={}).status_code == 403
    assert OPERATOR.post("/api/v1/org/plants", json={"name": "Nope"}).status_code == 403
    assert OPERATOR.get("/api/v1/admin/users").status_code == 403
    assert OPERATOR.post("/api/v1/demo/seed").status_code == 403

    assert MANAGER.post(f"/api/v1/defects/inspections/{insp['id']}/finalize", json={}).status_code == 200
    assert MANAGER.get("/api/v1/admin/users").status_code == 403


def test_admin_manages_users_and_cannot_lock_themselves_out():
    resp = ADMIN.post("/api/v1/admin/users", json={
        "email": "new.operator@parakhmaan.local", "full_name": "New Operator",
        "password": "SecurePass123", "role": "OPERATOR"})
    assert resp.status_code == 201, resp.text
    assert ADMIN.post("/api/v1/admin/users", json={
        "email": "bad@parakhmaan.local", "full_name": "Bad", "password": "SecurePass123", "role": "ROOT"}
    ).status_code == 400
    me = ADMIN.get("/api/v1/auth/me").json()
    assert ADMIN.patch(f"/api/v1/admin/users/{me['id']}", json={"role": "OPERATOR"}).status_code == 400
    login = anonymous_client().post("/api/v1/auth/login",
                                    json={"email": "new.operator@parakhmaan.local", "password": "SecurePass123"})
    assert login.status_code == 200


# ---------------------------------------------------------------- organisation isolation
def test_other_organisation_cannot_see_or_touch_data():
    insp = _new_inspection(OPERATOR)
    analyzed = OPERATOR.post(f"/api/v1/defects/inspections/{insp['id']}/analyze",
                             files={"file": ("p.jpg", _jpeg(), "image/jpeg")}).json()
    detection_id = analyzed["detections"][0]["id"]

    db = SessionLocal()
    other = Organization(name="Other Co", slug="other-co")
    db.add(other)
    db.commit()
    intruder = User(email="intruder@other.co", full_name="Intruder", role="ADMIN", organization_id=other.id,
                    hashed_password=get_password_hash("IntruderPass1"))
    db.add(intruder)
    db.commit()
    token = create_access_token(intruder.id, intruder.role)
    db.close()
    foreign = TestClient(app, headers={"Authorization": f"Bearer {token}"})

    assert insp["id"] not in {i["id"] for i in foreign.get("/api/v1/defects/inspections").json()}
    assert foreign.get(f"/api/v1/defects/inspections/{insp['id']}").status_code == 404
    assert foreign.post(f"/api/v1/defects/detections/{detection_id}/feedback", json={"action": "REJECT"}).status_code == 404
    assert foreign.get(f"/api/v1/inspections/{insp['id']}/report").status_code == 404
    assert foreign.get("/api/v1/defects/analytics").json()["totals"]["inspections"] == 0
    assert foreign.get("/api/v1/org/tree").json() == []


# ---------------------------------------------------------------- storage
def test_uploads_are_validated_by_content():
    insp = _new_inspection()
    url = f"/api/v1/defects/inspections/{insp['id']}/analyze"
    assert OPERATOR.post(url, files={"file": ("evil.jpg", b"<?php echo 1; ?>", "image/jpeg")}).status_code == 415
    assert OPERATOR.post(url, files={"file": ("empty.jpg", b"", "image/jpeg")}).status_code == 400
    original = settings.MAX_IMAGE_MB
    settings.MAX_IMAGE_MB = 0
    try:
        assert OPERATOR.post(url, files={"file": ("big.jpg", _jpeg(), "image/jpeg")}).status_code == 413
    finally:
        settings.MAX_IMAGE_MB = original
    video_url = f"/api/v1/defects/inspections/{insp['id']}/video"
    assert OPERATOR.post(video_url, files={"file": ("img.mp4", _jpeg(), "video/mp4")}).status_code == 415


def test_signed_file_urls_expire_and_resist_tampering():
    insp = _new_inspection()
    res = OPERATOR.post(f"/api/v1/defects/inspections/{insp['id']}/analyze",
                        files={"file": ("p.jpg", _jpeg(), "image/jpeg")}).json()
    url = res["image"]["file_url"]
    anon = anonymous_client()
    assert anon.get(url).status_code == 200
    assert anon.get(url.replace("sig=", "sig=ff")).status_code == 403
    encoded = url.split("/files/")[1].split("?")[0]
    expired = int(time.time()) - 10
    assert anon.get(f"/api/v1/files/{encoded}?exp={expired}&sig={storage_service._sign(encoded, expired)}").status_code == 403


def test_local_backend_blocks_path_traversal(tmp_path):
    backend = _LocalBackend(str(tmp_path / "store"))
    with pytest.raises(Exception):
        backend.path("../outside.txt")
    with pytest.raises(Exception):
        backend.path(str(tmp_path / "elsewhere" / "x.jpg"))
    assert backend.path("uploads/a/b.jpg").startswith(str((tmp_path / "store").resolve()))


def test_s3_backend_round_trip():
    moto = pytest.importorskip("moto")
    from app.services.storage_service import _S3Backend

    with moto.mock_aws():
        backend = _S3Backend()
        backend.put("uploads/x/sample.jpg", b"\xff\xd8\xffdata", "image/jpeg")
        assert backend.exists("uploads/x/sample.jpg")
        assert backend.read("uploads/x/sample.jpg") == b"\xff\xd8\xffdata"
        cached = backend.cache
        os.remove(os.path.join(cached, "uploads/x/sample.jpg"))
        assert open(backend.local_path("uploads/x/sample.jpg"), "rb").read() == b"\xff\xd8\xffdata"
        backend.delete("uploads/x/sample.jpg")
        assert not backend.exists("uploads/x/sample.jpg")


# ---------------------------------------------------------------- jobs
def test_failed_job_is_reported_not_raised(tmp_path):
    insp = _new_inspection()
    bogus = tmp_path / "broken.mp4"
    bogus.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)  # valid signature, undecodable video
    resp = OPERATOR.post(f"/api/v1/defects/inspections/{insp['id']}/video",
                         files={"file": ("broken.mp4", bogus.read_bytes(), "video/mp4")})
    assert resp.status_code == 202
    job = OPERATOR.get(f"/api/v1/jobs/{resp.json()['id']}").json()
    assert job["status"] == "FAILED"
    assert "decode" in job["error"].lower()


# ---------------------------------------------------------------- edge devices
def _station_id() -> str:
    tree = ADMIN.get("/api/v1/org/tree").json()
    return tree[0]["lines"][0]["stations"][0]["id"]


def test_edge_ingest_is_authenticated_and_idempotent():
    created = ADMIN.post("/api/v1/admin/devices", json={"name": "Cam-01", "station_id": _station_id()})
    assert created.status_code == 201, created.text
    key = created.json()["device_key"]
    anon = anonymous_client()

    meta = {"local_id": "abc123", "detections": [{"defect_type": "SCRATCH", "severity": "HIGH", "confidence": 0.9,
                                                  "bbox": [10, 10, 200, 40], "detector": "OPENCV"}],
            "scan": {"latency_ms": 42.0, "backend": "OPENCV", "exposure_ok": True}}
    files = {"file": ("c.jpg", _jpeg(), "image/jpeg")}
    assert anon.post("/api/v1/edge/ingest", files=files, data={"metadata": json.dumps(meta)},
                     headers={"X-Device-Key": "pmk_wrong"}).status_code == 401

    first = anon.post("/api/v1/edge/ingest", files={"file": ("c.jpg", _jpeg(), "image/jpeg")},
                      data={"metadata": json.dumps(meta)}, headers={"X-Device-Key": key})
    assert first.status_code == 201, first.text
    again = anon.post("/api/v1/edge/ingest", files={"file": ("c.jpg", _jpeg(), "image/jpeg")},
                      data={"metadata": json.dumps(meta)}, headers={"X-Device-Key": key})
    assert again.json()["inspection_id"] == first.json()["inspection_id"]

    detail = ADMIN.get(f"/api/v1/defects/inspections/{first.json()['inspection_id']}").json()
    assert detail["source"] == "EDGE"
    assert detail["station_id"] == _station_id()
    assert detail["overall_outcome"] == "DEFECTIVE"

    device_id = created.json()["device"]["id"]
    ADMIN.patch(f"/api/v1/admin/devices/{device_id}", json={"is_active": False})
    assert anon.get("/api/v1/edge/ping", headers={"X-Device-Key": key}).status_code == 401


def test_edge_node_queues_offline_and_syncs_later():
    import app.edge.main as edge

    created = ADMIN.post("/api/v1/admin/devices", json={"name": "Cam-02", "station_id": _station_id()}).json()
    settings.EDGE_DEVICE_KEY = created["device_key"]
    try:
        node = TestClient(edge.app)
        result = node.post("/infer", files={"file": ("x.jpg", _jpeg(("CRACK",)), "image/jpeg")}).json()
        assert result["queued"] is True and result["outcome"] == "DEFECTIVE"

        class Offline(httpx.Client):
            def post(self, *a, **k):
                raise httpx.ConnectError("central unreachable")

        stats = edge.sync_once(Offline())
        assert stats["retry"] == 1
        assert edge.outbox.counts()["PENDING"] >= 1

        with edge.outbox._lock:  # skip the retry backoff
            edge.outbox._conn.execute("UPDATE outbox SET next_attempt_at = 0")
        stats = edge.sync_once(anonymous_client())
        assert stats["sent"] >= 1
        synced = [i for i in edge.outbox.recent("SYNCED", 10) if i["local_id"] == result["local_id"]]
        assert synced and synced[0]["central_inspection_id"]
        detail = ADMIN.get(f"/api/v1/defects/inspections/{synced[0]['central_inspection_id']}").json()
        assert "CRACK" in {d["defect_type"] for d in detail["defect_detections"]}
    finally:
        settings.EDGE_DEVICE_KEY = ""


# ---------------------------------------------------------------- migrations & configuration
def test_phase_a_migration_moves_legacy_data_into_default_org(tmp_path):
    from alembic import command
    from sqlalchemy import create_engine, text
    from app.core.database import _alembic_config

    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    cfg = _alembic_config()
    cfg.attributes["url"] = url
    command.upgrade(cfg, "0001")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, full_name, hashed_password, role, is_active) "
                          "VALUES ('u1', 'old@x.in', 'Old', 'h', 'SUPERVISOR', 1)"))
        conn.execute(text("INSERT INTO inspections (id, inspection_number, inspection_mode, brand_name, category, "
                          "status, overall_outcome) VALUES ('i1', 'DEF-1', 'DEFECT', 'LOT-9', 'X', 'DRAFT', 'PENDING')"))
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        org_id = conn.execute(text("SELECT id FROM organizations WHERE slug='default'")).scalar()
        assert conn.execute(text("SELECT role, organization_id FROM users")).one() == ("QUALITY_MANAGER", org_id)
        assert conn.execute(text("SELECT organization_id, batch_code FROM inspections")).one() == (org_id, "LOT-9")
    command.downgrade(cfg, "0001")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT role FROM users")).scalar() == "SUPERVISOR"
    engine.dispose()


def test_production_refuses_insecure_defaults(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SECRET_KEY", config_module.DEV_SECRET_KEY)
    with pytest.raises(RuntimeError):
        config_module.validate_settings()
    monkeypatch.setattr(settings, "SECRET_KEY", "x" * 48)
    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://qc.example.com")
    config_module.validate_settings()
