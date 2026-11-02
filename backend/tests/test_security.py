import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_and_upgrade, verify_password
from app.core.database import SessionLocal
from app.main import app
from app.models.all_models import User
import hashlib

client = TestClient(app)


@pytest.fixture
def auth_on():
    settings.AUTH_REQUIRED = True
    yield
    settings.AUTH_REQUIRED = False


def test_hash_is_bcrypt_and_plaintext_never_matches():
    hashed = get_password_hash("secret")
    assert hashed.startswith("$2")
    assert verify_password("secret", hashed)
    assert not verify_password(hashed, hashed)
    assert not verify_password("demo", "demo")


def test_legacy_hash_upgrades_once():
    legacy = hashlib.sha256(("old-password" + "sih26034_salt").encode()).hexdigest()
    ok, upgraded = verify_and_upgrade("old-password", legacy)
    assert ok and upgraded.startswith("$2")
    assert verify_and_upgrade("wrong", legacy) == (False, None)


@pytest.mark.parametrize("method,path", [
    ("post", "/api/v1/defects/inspections"), ("get", "/api/v1/production/units"), ("post", "/api/v1/learning/models/x/promote"),
    ("get", "/api/v1/analytics/overview"), ("get", "/api/v1/inspections"), ("get", "/api/v1/edge/status"),
    ("post", "/api/v1/live/sessions"),
])
def test_anonymous_requests_are_refused(auth_on, method, path):
    kwargs = {"json": {}} if method == "post" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_invalid_token_is_refused(auth_on):
    assert client.get("/api/v1/production/units", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_health_and_login_stay_public(auth_on):
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code == 400


def test_unknown_email_cannot_create_account():
    res = client.post("/api/v1/auth/login", json={"email": "new@gov.in", "password": "anything"})
    assert res.status_code == 400


def test_wrong_password_is_refused():
    res = client.post("/api/v1/auth/login", json={"email": "inspector@gov.in", "password": "wrong"})
    assert res.status_code == 400


def _token(email: str, role: str) -> str:
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(email=email, full_name=role, hashed_password="!", role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
    token = create_access_token(user.id, user.role)
    db.close()
    return token


def test_inspector_cannot_promote_or_register(auth_on):
    headers = {"Authorization": f"Bearer {_token('rbac-inspector@x.in', 'INSPECTOR')}"}
    assert client.post("/api/v1/learning/models/x/promote", headers=headers).status_code == 403
    assert client.post("/api/v1/production/products", headers=headers, json={"name": "x"}).status_code == 403
    assert client.post("/api/v1/auth/register", headers=headers, json={
        "email": "z@x.in", "full_name": "z", "password": "pw", "role": "ADMIN"}).status_code == 403


def test_supervisor_reaches_promotion_logic(auth_on):
    headers = {"Authorization": f"Bearer {_token('rbac-super@x.in', 'SUPERVISOR')}"}
    assert client.post("/api/v1/learning/models/missing/promote", headers=headers).status_code == 404


def test_upload_type_and_size_limits():
    insp = client.post("/api/v1/defects/inspections", json={"product_name": "x"}).json()
    bad = client.post(f"/api/v1/defects/inspections/{insp['id']}/analyze", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 415
    limit = settings.MAX_UPLOAD_MB
    settings.MAX_UPLOAD_MB = 0
    big = client.post(f"/api/v1/defects/inspections/{insp['id']}/analyze", files={"file": ("x.jpg", b"123", "image/jpeg")})
    settings.MAX_UPLOAD_MB = limit
    assert big.status_code == 413


def test_live_source_cannot_escape_storage():
    res = client.post("/api/v1/live/sessions", json={"source_kind": "VIDEO_FILE", "source": "/etc/passwd"})
    assert res.status_code == 403


def test_cors_does_not_allow_arbitrary_origin():
    res = client.options("/api/v1/production/units", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert res.headers.get("access-control-allow-origin") != "https://evil.example"


def test_stored_files_need_login_and_only_images_or_pdfs_are_served(auth_on, tmp_path):
    import os
    root = settings.STORAGE_DIR
    os.makedirs(os.path.join(root, "units"), exist_ok=True)
    os.makedirs(os.path.join(root, "models"), exist_ok=True)
    with open(os.path.join(root, "units", "probe.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    with open(os.path.join(root, "probe.db"), "wb") as f:
        f.write(b"SQLite format 3\x00")
    with open(os.path.join(root, "models", "probe.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
    headers = {"Authorization": f"Bearer {_token('files-inspector@x.in', 'INSPECTOR')}"}
    assert client.get("/storage/probe.db").status_code == 404  # no public static mount any more
    assert client.get("/api/v1/files/units/probe.png").status_code == 401
    ok = client.get("/api/v1/files/units/probe.png", headers=headers)
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/png"
    assert client.get("/api/v1/files/storage/units/probe.png", headers=headers).status_code == 200
    assert client.get("/api/v1/files/probe.db", headers=headers).status_code == 403
    assert client.get("/api/v1/files/models/probe.png", headers=headers).status_code == 403
    assert client.get("/api/v1/files/..%2F..%2Fetc%2Fpasswd", headers=headers).status_code in (403, 404)
    assert client.get("/api/v1/files/units/../../../../etc/hosts", headers=headers).status_code in (403, 404)
