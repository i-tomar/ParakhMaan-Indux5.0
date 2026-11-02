"""Continuous inspection sessions: browser camera over WebSocket, or a server-side source."""
import asyncio
import os
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.core.config import settings
from app.core.security import decode_access_token
from app.models.all_models import User
from app.services.realtime.pipeline import LiveSession, SessionConfig, manager
from app.services.realtime.sources import conveyor_simulation, sample_paths, video_source

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
    if not (req.source or "").startswith("rtsp://"):
        raise HTTPException(422, "RTSP source must start with rtsp://")
    return video_source(req.source)


@router.post("/sessions")
def start_session(req: SessionRequest, _: User = Depends(get_current_user)):
    frames = _build_frames(req)
    config = SessionConfig(product_id=req.product_id, batch_id=req.batch_id, machine_id=req.machine_id, line_id=req.line_id,
                           source_kind=req.source_kind, is_synthetic=req.source_kind == "CONVEYOR_SIM",
                           trigger_x_ratio=req.trigger_x_ratio)
    session = manager.add(LiveSession(config, frames).start())
    return session.stats()


@router.get("/sessions/{session_id}")
def get_session(session_id: str, _: User = Depends(get_current_user)):
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    return session.stats()


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: str, _: User = Depends(get_current_user)):
    session = manager.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    session.finish_source()
    return session.stats()


@router.websocket("/sessions/{session_id}/stream")
async def stream(websocket: WebSocket, session_id: str, token: str = Query("")):
    """Browser sends JPEG frames as binary messages and receives live stats as JSON."""
    if settings.AUTH_REQUIRED and not decode_access_token(token):
        await websocket.close(code=4401)
        return
    session = manager.get(session_id)
    if not session:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            frame = await asyncio.to_thread(lambda: cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR))
            if frame is not None:
                session.push(frame)
            await websocket.send_json({k: v for k, v in session.stats().items() if k != "recent"} | {"recent": list(session.recent)[:5]})
    except WebSocketDisconnect:
        session.finish_source()
