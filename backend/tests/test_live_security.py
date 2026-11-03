import io
import time
import pytest
import cv2
import numpy as np
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.all_models import AuditEvent, User
from app.models.industrial import ProductionLine
from app.api.live import validate_rtsp_url
from app.services.realtime.pipeline import manager

client = TestClient(app)


@pytest.fixture
def auth_required():
    old = settings.AUTH_REQUIRED
    settings.AUTH_REQUIRED = True
    yield
    settings.AUTH_REQUIRED = old


@pytest.fixture
def users(auth_required):
    db = SessionLocal()
    try:
        def get_or_create(email, role):
            u = db.query(User).filter(User.email == email).first()
            if not u:
                u = User(email=email, full_name=email, role=role, hashed_password=get_password_hash("pass123"))
                db.add(u)
                db.commit()
                db.refresh(u)
            return u

        inspector1 = get_or_create("insp1@test.gov.in", "INSPECTOR")
        inspector2 = get_or_create("insp2@test.gov.in", "INSPECTOR")
        supervisor = get_or_create("super@test.gov.in", "SUPERVISOR")
        admin = get_or_create("admin@test.gov.in", "ADMIN")

        return {
            "inspector1": inspector1,
            "inspector2": inspector2,
            "supervisor": supervisor,
            "admin": admin,
            "token_insp1": create_access_token(inspector1.id, role=inspector1.role),
            "token_insp2": create_access_token(inspector2.id, role=inspector2.role),
            "token_super": create_access_token(supervisor.id, role=supervisor.role),
            "token_admin": create_access_token(admin.id, role=admin.role),
        }
    finally:
        db.close()


@pytest.fixture
def hardware_line():
    db = SessionLocal()
    try:
        line = db.query(ProductionLine).filter(ProductionLine.code == "LINE_HW_TEST").first()
        if not line:
            line = ProductionLine(
                code="LINE_HW_TEST",
                name="Hardware Webhook Line",
                belt_speed_mm_s=200.0,
                camera_to_diverter_mm=600.0,
                pitch_mm=300.0,
                actuator_kind="WEBHOOK",
                actuator_target="http://127.0.0.1:9099/reject",
            )
            db.add(line)
        else:
            line.actuator_kind = "WEBHOOK"
            line.actuator_target = "http://127.0.0.1:9099/reject"
        db.commit()
        db.refresh(line)
        return line
    finally:
        db.close()


def make_jpeg_bytes(w: int = 100, h: int = 100, color: tuple = (120, 120, 120)) -> bytes:
    img = np.full((h, w, 3), color, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


# =====================================================================
# 1. Actuator Authorisation & Hardware Arming Tests
# =====================================================================

def test_inspector_cannot_arm_hardware_at_start(users, hardware_line):
    headers = {"Authorization": f"Bearer {users['token_insp1']}"}
    res = client.post(
        "/api/v1/live/sessions",
        headers=headers,
        json={"source_kind": "BROWSER", "line_id": hardware_line.id, "arm_hardware": True},
    )
    assert res.status_code == 403
    assert "Only SUPERVISOR or ADMIN" in res.json()["detail"]


def test_default_session_keeps_simulated_actuator_even_with_hardware_line(users, hardware_line):
    headers = {"Authorization": f"Bearer {users['token_insp1']}"}
    res = client.post(
        "/api/v1/live/sessions",
        headers=headers,
        json={"source_kind": "BROWSER", "line_id": hardware_line.id, "arm_hardware": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["actuator"] == "SIMULATED"
    assert data["hardware_armed"] is False


def test_inspector_cannot_call_arm_or_disarm_endpoint(users, hardware_line):
    # Start an unarmed session as inspector
    headers_insp = {"Authorization": f"Bearer {users['token_insp1']}"}
    res = client.post(
        "/api/v1/live/sessions",
        headers=headers_insp,
        json={"source_kind": "BROWSER", "line_id": hardware_line.id},
    )
    assert res.status_code == 200
    session_id = res.json()["session_id"]

    # Try arming as inspector
    arm_res = client.post(f"/api/v1/live/sessions/{session_id}/arm", headers=headers_insp)
    assert arm_res.status_code == 403

    # Try disarming as inspector
    disarm_res = client.post(f"/api/v1/live/sessions/{session_id}/disarm", headers=headers_insp)
    assert disarm_res.status_code == 403


def test_supervisor_can_arm_and_disarm_with_audit_logging(users, hardware_line):
    headers_super = {"Authorization": f"Bearer {users['token_super']}"}
    # 1. Start session as supervisor
    res = client.post(
        "/api/v1/live/sessions",
        headers=headers_super,
        json={"source_kind": "BROWSER", "line_id": hardware_line.id, "arm_hardware": False},
    )
    assert res.status_code == 200
    session_id = res.json()["session_id"]
    assert res.json()["hardware_armed"] is False

    # 2. Arm hardware as supervisor (fake serial link in test environment)
    # SerialActuator in actuator.py catches optional serial or factory
    session = manager.get(session_id)
    assert session is not None

    arm_res = client.post(f"/api/v1/live/sessions/{session_id}/arm", headers=headers_super)
    assert arm_res.status_code == 200
    arm_data = arm_res.json()
    assert arm_data["hardware_armed"] is True
    assert arm_data["armed_by"] == users["supervisor"].id

    # 3. Disarm hardware as supervisor
    disarm_res = client.post(f"/api/v1/live/sessions/{session_id}/disarm", headers=headers_super)
    assert disarm_res.status_code == 200
    disarm_data = disarm_res.json()
    assert disarm_data["hardware_armed"] is False
    assert disarm_data["actuator"] == "SIMULATED"

    # 4. Verify audit entries in database
    db = SessionLocal()
    try:
        events = db.query(AuditEvent).filter(
            AuditEvent.event_type.in_(["LIVE_SESSION_STARTED", "HARDWARE_ARMED", "HARDWARE_DISARMED"])
        ).all()
        types = [e.event_type for e in events]
        assert "LIVE_SESSION_STARTED" in types
        assert "HARDWARE_ARMED" in types
        assert "HARDWARE_DISARMED" in types
    finally:
        db.close()


def test_arm_hardware_fails_cleanly_on_unreachable_actuator(users):
    db = SessionLocal()
    try:
        line = db.query(ProductionLine).filter(ProductionLine.code == "LINE_SERIAL_FAIL").first()
        if not line:
            line = ProductionLine(
                code="LINE_SERIAL_FAIL",
                name="Hardware Missing Serial Line",
                belt_speed_mm_s=200.0,
                camera_to_diverter_mm=600.0,
                pitch_mm=300.0,
                actuator_kind="SERIAL",
                actuator_target="COM999",
            )
            db.add(line)
            db.commit()
            db.refresh(line)
        line_id = line.id
    finally:
        db.close()

    headers_super = {"Authorization": f"Bearer {users['token_super']}"}
    res = client.post(
        "/api/v1/live/sessions",
        headers=headers_super,
        json={"source_kind": "BROWSER", "line_id": line_id, "arm_hardware": False},
    )
    assert res.status_code == 200
    session_id = res.json()["session_id"]

    # Attempting to arm with missing driver / unreachable serial port returns clean HTTP 400
    arm_res = client.post(f"/api/v1/live/sessions/{session_id}/arm", headers=headers_super)
    assert arm_res.status_code == 400
    assert "Cannot arm hardware" in arm_res.json()["detail"]

    # Verify session remains safe and in simulation mode
    session = manager.get(session_id)
    assert session.hardware_armed is False
    assert session.actuator.kind == "SIMULATED"



# =====================================================================
# 2. Live Session Ownership & Multi-Tenant Access Tests
# =====================================================================

def test_cross_user_session_access_is_forbidden(users):
    # Inspector 1 starts a session
    headers_insp1 = {"Authorization": f"Bearer {users['token_insp1']}"}
    res = client.post("/api/v1/live/sessions", headers=headers_insp1, json={"source_kind": "BROWSER"})
    assert res.status_code == 200
    session_id = res.json()["session_id"]

    # Inspector 2 tries to view Inspector 1's session
    headers_insp2 = {"Authorization": f"Bearer {users['token_insp2']}"}
    get_res = client.get(f"/api/v1/live/sessions/{session_id}", headers=headers_insp2)
    assert get_res.status_code == 403
    assert "do not own this live session" in get_res.json()["detail"]

    # Inspector 2 tries to stop Inspector 1's session
    stop_res = client.post(f"/api/v1/live/sessions/{session_id}/stop", headers=headers_insp2)
    assert stop_res.status_code == 403
    assert "do not own this live session" in stop_res.json()["detail"]

    # Inspector 1 (owner) can view and stop
    assert client.get(f"/api/v1/live/sessions/{session_id}", headers=headers_insp1).status_code == 200

    # Supervisor / Admin can also view and stop (supervisory oversight)
    headers_admin = {"Authorization": f"Bearer {users['token_admin']}"}
    assert client.get(f"/api/v1/live/sessions/{session_id}", headers=headers_admin).status_code == 200


# =====================================================================
# 3. WebSocket Security, Authentication & Limits Tests
# =====================================================================

def test_websocket_token_authentication_and_cross_user_rejection(users):
    headers_insp1 = {"Authorization": f"Bearer {users['token_insp1']}"}
    res = client.post("/api/v1/live/sessions", headers=headers_insp1, json={"source_kind": "BROWSER"})
    session_id = res.json()["session_id"]

    # 1. Missing token -> 4401
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/v1/live/sessions/{session_id}/stream?token="):
            pass
    assert exc.value.code == 4401

    # 2. Token from another inspector (Inspector 2) -> 4403
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/v1/live/sessions/{session_id}/stream?token={users['token_insp2']}"):
            pass
    assert exc.value.code == 4403

    # 3. Token from owner (Inspector 1) -> accepted
    jpeg = make_jpeg_bytes(160, 120)
    with client.websocket_connect(f"/api/v1/live/sessions/{session_id}/stream?token={users['token_insp1']}") as ws:
        ws.send_bytes(jpeg)
        resp = ws.receive_json()
        assert resp["session_id"] == session_id
        assert resp["frames_received"] >= 1


def test_websocket_rejects_malformed_image_data(users):
    headers_insp1 = {"Authorization": f"Bearer {users['token_insp1']}"}
    res = client.post("/api/v1/live/sessions", headers=headers_insp1, json={"source_kind": "BROWSER"})
    session_id = res.json()["session_id"]

    garbage_bytes = b"NOT_AN_IMAGE_THIS_IS_CORRUPTED_BINARY_PAYLOAD_1234567890"
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/v1/live/sessions/{session_id}/stream?token={users['token_insp1']}") as ws:
            ws.send_bytes(garbage_bytes)
            ws.receive_json()
    assert exc.value.code == 4422


def test_websocket_enforces_payload_size_limit(users):
    headers_insp1 = {"Authorization": f"Bearer {users['token_insp1']}"}
    res = client.post("/api/v1/live/sessions", headers=headers_insp1, json={"source_kind": "BROWSER"})
    session_id = res.json()["session_id"]

    # Payload larger than WS_MAX_FRAME_BYTES
    oversized = b"X" * (settings.WS_MAX_FRAME_BYTES + 1024)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/v1/live/sessions/{session_id}/stream?token={users['token_insp1']}") as ws:
            ws.send_bytes(oversized)
            ws.receive_json()
    assert exc.value.code == 4413


def test_websocket_enforces_frame_rate_limit(users):
    headers_insp1 = {"Authorization": f"Bearer {users['token_insp1']}"}
    res = client.post("/api/v1/live/sessions", headers=headers_insp1, json={"source_kind": "BROWSER"})
    session_id = res.json()["session_id"]

    jpeg = make_jpeg_bytes(80, 80)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/v1/live/sessions/{session_id}/stream?token={users['token_insp1']}") as ws:
            # Send frames in a tight loop exceeding WS_MAX_FPS
            for _ in range(int(settings.WS_MAX_FPS) + 5):
                ws.send_bytes(jpeg)
                ws.receive_json()
    assert exc.value.code == 4429


# =====================================================================
# 4. RTSP Ingestion & SSRF Safety Tests
# =====================================================================

@pytest.mark.parametrize("blocked_url", [
    "rtsp://localhost:554/cam",
    "rtsp://127.0.0.1:554/cam",
    "rtsp://0.0.0.0:554/cam",
    "rtsp://169.254.169.254/latest/meta-data",
    "rtsp://10.0.0.1:554/feed",
    "rtsp://192.168.1.100:554/live",
])
def test_rtsp_disallows_loopback_metadata_and_unapproved_private_ips(blocked_url):
    with pytest.raises(Exception) as exc:
        validate_rtsp_url(blocked_url, allowed_hosts_str="")
    assert exc.value.status_code == 403


def test_rtsp_rejects_non_rtsp_scheme():
    with pytest.raises(Exception) as exc:
        validate_rtsp_url("http://camera.factory.com/stream", allowed_hosts_str="")
    assert exc.value.status_code == 422


def test_rtsp_allowlist_permits_approved_camera_host():
    allowlist = "camera-line1.plant.internal, 192.168.10.0/24"
    # Approved hostname
    url1 = "rtsp://camera-line1.plant.internal:554/h264"
    assert validate_rtsp_url(url1, allowed_hosts_str=allowlist) == url1

    # Approved CIDR subnet
    url2 = "rtsp://192.168.10.42:554/live"
    assert validate_rtsp_url(url2, allowed_hosts_str=allowlist) == url2

    # Unapproved host
    with pytest.raises(Exception) as exc:
        validate_rtsp_url("rtsp://rogue-camera.plant.internal:554/live", allowed_hosts_str=allowlist)
    assert exc.value.status_code == 403


def test_rtsp_unreachable_source_returns_clean_http_error(users):
    headers = {"Authorization": f"Bearer {users['token_admin']}"}
    # Allow test camera domain in settings
    old_allow = settings.RTSP_ALLOWED_HOSTS
    try:
        settings.RTSP_ALLOWED_HOSTS = "safe-public-test-camera.org"
        res = client.post(
            "/api/v1/live/sessions",
            headers=headers,
            json={"source_kind": "RTSP", "source": "rtsp://safe-public-test-camera.org:554/stream"},
        )
        # Should gracefully fail with 400 (Cannot open video source) rather than 500
        assert res.status_code == 400
        assert "Cannot open video source" in res.json()["detail"]
    finally:
        settings.RTSP_ALLOWED_HOSTS = old_allow
