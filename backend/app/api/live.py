"""Continuous inspection sessions: browser camera over WebSocket, or a server-side source.

P0 Safety Controls:
1. Actuator Authorisation: Actuators default to SIMULATED. Physical actuators (SERIAL, WEBHOOK)
   require explicit hardware arming by an authorized SUPERVISOR or ADMIN. Audit events logged.
2. Session Ownership: Live sessions track their creator. Only the owner or a SUPERVISOR/ADMIN
   can inspect stats, stop the session, or connect via WebSocket.
3. WebSocket Limits: Enforces max frame payload bytes, max dimensions, pixel counts, per-session
   frame rate limits, and rejects malformed image streams.
4. RTSP Safety: Validates RTSP destinations against an allowlist, blocks loopback/cloud metadata/private
   destinations unless explicitly allowed, and handles timeouts/unreachable streams gracefully.
"""
import asyncio
import ipaddress
import logging
import os
import time
import urllib.parse
from collections import deque
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.all_models import AuditEvent, User
from app.services.realtime.pipeline import LiveSession, SessionConfig, manager
from app.services.realtime.sources import conveyor_simulation, sample_paths, video_source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["Live Inspection"])


class SessionRequest(BaseModel):
    source_kind: str = Field("BROWSER", pattern="^(BROWSER|CONVEYOR_SIM|VIDEO_FILE|CAMERA|RTSP)$")
    source: Optional[str] = None  # sample folder, video path, camera index or RTSP URL
    product_id: Optional[str] = None
    batch_id: Optional[str] = None
    machine_id: Optional[str] = None
    line_id: Optional[str] = None
    fps: float = Field(30.0, gt=0, le=120)
    trigger_x_ratio: float = Field(0.55, gt=0, lt=1)
    limit: Optional[int] = Field(None, gt=0, le=500)
    arm_hardware: bool = False  # Explicit arming: only SUPERVISOR or ADMIN may set True


def log_live_audit(
    db: Session,
    user: User,
    event_type: str,
    description: str,
    state_after: Optional[Dict[str, Any]] = None,
) -> None:
    """Records audit logs to both Python logging and AuditEvent database table."""
    logger.info("AUDIT [%s] User=%s (%s): %s", event_type, user.email, user.role, description)
    try:
        event = AuditEvent(
            inspection_id=None,
            user_id=user.id,
            event_type=event_type,
            description=description,
            state_before=None,
            state_after=state_after or {},
        )
        db.add(event)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Could not persist audit event %s: %s", event_type, e)


def verify_session_access(session: LiveSession, user: User) -> None:
    """Access control: Owner or SUPERVISOR/ADMIN permitted. Other inspectors forbidden."""
    if user.role in ("SUPERVISOR", "ADMIN"):
        return
    if session.user_id and session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: you do not own this live session",
        )


def validate_rtsp_url(url: str, allowed_hosts_str: str = "") -> str:
    """Validates RTSP source URL against SSRF rules, blocked subnets, and host allowlist."""
    if not url or not url.startswith("rtsp://"):
        raise HTTPException(status_code=422, detail="RTSP source must start with rtsp://")
    parsed = urllib.parse.urlsplit(url)
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=422, detail="RTSP source must include a valid hostname")

    lowered = hostname.lower()
    # 1. Block loopback, broadcast, and internal cloud metadata endpoints
    if lowered in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access to host '{hostname}' via RTSP is forbidden")

    is_private = False
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Access to IP '{hostname}' via RTSP is forbidden")
        if str(ip).startswith("169.254."):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to cloud metadata IP via RTSP is forbidden")
        is_private = ip.is_private
    except ValueError:
        is_private = False

    # 2. Check allowlist policy
    allowed_list = [h.strip() for h in (allowed_hosts_str or "").split(",") if h.strip()]
    if allowed_list:
        matched = False
        for allowed in allowed_list:
            if allowed.lower() == lowered:
                matched = True
                break
            try:
                network = ipaddress.ip_network(allowed, strict=False)
                if ipaddress.ip_address(hostname) in network:
                    matched = True
                    break
            except ValueError:
                pass
        if not matched:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"RTSP host '{hostname}' is not in the approved camera allowlist",
            )
    else:
        # If no explicit allowlist is configured, block private/internal subnets by default for security
        if is_private:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Private IP destinations are not allowed for RTSP sources unless explicitly listed in RTSP_ALLOWED_HOSTS",
            )

    return url


def _allowed_folder(path: str) -> str:
    """Server-side sources may only be read from inside storage, never from arbitrary paths."""
    root = os.path.realpath(settings.STORAGE_DIR)
    real = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    if not real.startswith(root + os.sep):
        raise HTTPException(403, "Source must be inside the storage directory")
    return real


def _build_frames(req: SessionRequest):
    if req.source_kind == "BROWSER":
        return None
    if req.source_kind == "CONVEYOR_SIM":
        if not req.source:
            raise HTTPException(422, "CONVEYOR_SIM needs a sample folder")
        folder = _allowed_folder(req.source)
        if not os.path.isdir(folder):
            raise HTTPException(404, "Sample folder not found")
        return conveyor_simulation(sample_paths(folder, req.limit), fps=req.fps)
    if req.source_kind == "VIDEO_FILE":
        return video_source(_allowed_folder(req.source or ""))
    if req.source_kind == "CAMERA":
        return video_source(int(req.source or 0))
    if req.source_kind == "RTSP":
        if not req.source:
            raise HTTPException(422, "RTSP source must be provided")
        sanitized_url = validate_rtsp_url(req.source, settings.RTSP_ALLOWED_HOSTS)
        try:
            return video_source(sanitized_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return None


@router.post("/sessions")
def start_session(
    req: SessionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Actuator Authorisation Check
    if req.arm_hardware and current_user.role not in ("SUPERVISOR", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only SUPERVISOR or ADMIN roles can arm physical actuators",
        )

    frames = _build_frames(req)
    config = SessionConfig(
        product_id=req.product_id,
        batch_id=req.batch_id,
        machine_id=req.machine_id,
        line_id=req.line_id,
        source_kind=req.source_kind,
        is_synthetic=req.source_kind == "CONVEYOR_SIM",
        trigger_x_ratio=req.trigger_x_ratio,
        user_id=current_user.id,
        user_role=current_user.role,
        arm_hardware=req.arm_hardware,
    )
    session = manager.add(LiveSession(config, frames).start())

    log_live_audit(
        db,
        current_user,
        "LIVE_SESSION_STARTED",
        f"Session {session.id} started with source {req.source_kind} (hardware_armed={session.hardware_armed})",
        {
            "session_id": session.id,
            "line_id": req.line_id,
            "source": req.source_kind,
            "hardware_armed": session.hardware_armed,
            "actuator": session.actuator.kind,
        },
    )
    return session.stats()


@router.get("/sessions")
def list_sessions(current_user: User = Depends(get_current_user)):
    """List active sessions. Supervisors/Admins see all; Inspectors see only their own."""
    all_sessions = [s.stats() for s in manager.sessions.values()]
    if current_user.role in ("SUPERVISOR", "ADMIN"):
        return all_sessions
    return [s for s in all_sessions if s.get("user_id") == current_user.id]


@router.get("/sessions/{session_id}")
def get_session(session_id: str, current_user: User = Depends(get_current_user)):
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    verify_session_access(session, current_user)
    return session.stats()


@router.post("/sessions/{session_id}/stop")
def stop_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    verify_session_access(session, current_user)
    session.finish_source()

    log_live_audit(
        db,
        current_user,
        "LIVE_SESSION_STOPPED",
        f"Session {session_id} stopped by {current_user.email}",
        {"session_id": session_id},
    )
    return session.stats()


@router.post("/sessions/{session_id}/arm")
def arm_session_hardware(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Explicitly arm physical actuator for this session. Requires SUPERVISOR or ADMIN."""
    if current_user.role not in ("SUPERVISOR", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only SUPERVISOR or ADMIN roles can arm physical actuators",
        )
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    verify_session_access(session, current_user)

    try:
        res = session.arm_hardware(current_user.id)
        log_live_audit(
            db,
            current_user,
            "HARDWARE_ARMED",
            f"Actuator {res['actuator']} armed for session {session_id}",
            res,
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot arm hardware: {e}")


@router.post("/sessions/{session_id}/disarm")
def disarm_session_hardware(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disarm physical actuator back to SIMULATED. Requires SUPERVISOR or ADMIN."""
    if current_user.role not in ("SUPERVISOR", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only SUPERVISOR or ADMIN roles can disarm physical actuators",
        )
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    verify_session_access(session, current_user)

    res = session.disarm_hardware(current_user.id)
    log_live_audit(
        db,
        current_user,
        "HARDWARE_DISARMED",
        f"Actuator disarmed to SIMULATED for session {session_id}",
        res,
    )
    return res


@router.websocket("/sessions/{session_id}/stream")
async def stream(websocket: WebSocket, session_id: str, token: str = Query("")):
    """Browser sends JPEG frames as binary messages and receives live stats as JSON.

    P0 Safety & Limits:
    - Verifies token and session ownership (code 4401 or 4403).
    - Enforces maximum encoded frame payload size (code 4413).
    - Enforces per-session maximum frame rate (code 4429).
    - Rejects malformed or undecodable image bytes (code 4422).
    - Enforces maximum decoded dimensions and pixel caps (code 4422).
    """
    payload = decode_access_token(token) if token else None
    if settings.AUTH_REQUIRED and not payload:
        await websocket.close(code=4401)
        return

    session = manager.get(session_id)
    if not session:
        await websocket.close(code=4404)
        return

    # Enforce Session Access Control on WebSocket
    if payload:
        user_id = payload.get("sub")
        user_role = payload.get("role")
        if user_role not in ("SUPERVISOR", "ADMIN") and session.user_id and session.user_id != user_id:
            await websocket.close(code=4403)
            return

    await websocket.accept()

    # Track frame rate timestamps for rate limiting
    rate_window: deque = deque(maxlen=int(settings.WS_MAX_FPS) + 1)

    try:
        while True:
            data = await websocket.receive_bytes()

            # 1. Enforce payload size limit
            if len(data) > settings.WS_MAX_FRAME_BYTES:
                await websocket.close(code=4413, reason="Payload Too Large")
                return

            # 2. Enforce frame rate limit (sliding window)
            now = time.time()
            rate_window.append(now)
            if len(rate_window) > settings.WS_MAX_FPS:
                elapsed = now - rate_window[0]
                if elapsed < 1.0:
                    await websocket.close(code=4429, reason="Frame Rate Exceeded")
                    return

            # 3. Decode frame and validate against malformed data
            frame = await asyncio.to_thread(lambda: cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR))
            if frame is None:
                await websocket.close(code=4422, reason="Malformed Image Data")
                return

            # 4. Enforce decoded dimensions and maximum pixel count
            h, w = frame.shape[:2]
            if w > settings.WS_MAX_DIMENSION or h > settings.WS_MAX_DIMENSION:
                await websocket.close(code=4422, reason="Frame Dimensions Exceeded")
                return

            if (w * h) > settings.WS_MAX_PIXELS:
                await websocket.close(code=4422, reason="Frame Pixels Exceeded")
                return

            session.push(frame)
            await websocket.send_json(
                {k: v for k, v in session.stats().items() if k != "recent"}
                | {"recent": list(session.recent)[:5]}
            )
    except WebSocketDisconnect:
        session.finish_source()
