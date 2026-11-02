"""
ParakhMaan edge node:  python -m uvicorn app.edge.main:app --port 8090

Runs next to the camera: inference happens locally (no round trip to the server), every result is
written to a durable outbox, and a background thread forwards it to the central API with the
device key. If the network or server is down, the line keeps inspecting and results sync later.
"""
import hashlib
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import cv2
import httpx
import numpy as np
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.edge.outbox import Outbox
from app.services.defect_detection_service import DefectDetector, decode_base64_image, defect_detector

log = logging.getLogger("parakhmaan.edge")

outbox = Outbox(settings.EDGE_QUEUE_DB)
_state: Dict[str, Any] = {"last_sync_at": None, "last_sync_ok": None, "last_error": None, "device": None,
                          "model": None, "last_model_check": 0.0}
_wake = threading.Event()
_stop = threading.Event()
_detector_lock = threading.Lock()
_detector: DefectDetector = defect_detector


def current_detector() -> DefectDetector:
    with _detector_lock:
        return _detector


def _central(path: str) -> str:
    return settings.EDGE_CENTRAL_URL.rstrip("/") + settings.API_V1_STR + path


def check_model_update(client: httpx.Client) -> bool:
    """Pulls the organisation's ACTIVE model when it changes (promotion or rollback) and hot-swaps it."""
    global _detector
    if not settings.EDGE_DEVICE_KEY:
        return False
    _state["last_model_check"] = time.monotonic()
    resp = client.get(_central("/edge/model"), headers={"X-Device-Key": settings.EDGE_DEVICE_KEY})
    if resp.status_code != 200:
        return False
    info = resp.json().get("model")
    if not info or (_state["model"] or {}).get("sha256") == info["sha256"]:
        return False
    os.makedirs(settings.EDGE_MODEL_DIR, exist_ok=True)
    path = os.path.join(settings.EDGE_MODEL_DIR, f"{info['sha256']}.onnx")
    if not os.path.exists(path):
        download = client.get(settings.EDGE_CENTRAL_URL.rstrip("/") + info["download_url"])
        download.raise_for_status()
        if hashlib.sha256(download.content).hexdigest() != info["sha256"]:
            raise ValueError("Downloaded model failed its integrity check")
        with open(path + ".part", "wb") as f:
            f.write(download.content)
        os.replace(path + ".part", path)
    new = DefectDetector(model_path=path, model_classes=",".join(info.get("classes") or []))
    if not new.status()["model_loaded"]:
        raise ValueError(f"Model {info['name']} could not be loaded: {new.status()['model_error']}")
    new.model_version = f"{info['name']}@{info['sha256'][:12]}"
    with _detector_lock:
        _detector = new
    _state["model"] = {k: info[k] for k in ("id", "name", "version", "sha256")}
    log.info("Edge node switched to model %s", info["name"])
    return True


def sync_once(client: Optional[httpx.Client] = None) -> Dict[str, int]:
    """Forwards due outbox items. 4xx (other than rate limiting) are permanent; others are retried."""
    if not settings.EDGE_DEVICE_KEY:
        return {"sent": 0, "failed": 0, "retry": 0}
    own_client = client is None
    client = client or httpx.Client(timeout=30)
    stats = {"sent": 0, "failed": 0, "retry": 0}
    try:
        for item in outbox.due(settings.EDGE_SYNC_BATCH):
            try:
                resp = client.post(
                    _central("/edge/ingest"),
                    headers={"X-Device-Key": settings.EDGE_DEVICE_KEY},
                    files={"file": (f"{item['local_id']}.jpg", item["image"], "image/jpeg")},
                    data={"metadata": item["metadata"]},
                )
            except httpx.HTTPError as e:
                outbox.mark_retry(item["id"], item["attempts"] + 1, f"network: {e}")
                stats["retry"] += 1
                _state.update(last_sync_ok=False, last_error=str(e))
                break  # central unreachable: stop this round, keep order
            if resp.status_code in (200, 201):
                outbox.mark_synced(item["id"], resp.json().get("inspection_id"))
                stats["sent"] += 1
            elif 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
                outbox.mark_failed(item["id"], f"HTTP {resp.status_code}: {resp.text[:300]}")
                stats["failed"] += 1
            else:
                outbox.mark_retry(item["id"], item["attempts"] + 1, f"HTTP {resp.status_code}")
                stats["retry"] += 1
        if stats["sent"] or stats["failed"]:
            _state.update(last_sync_ok=True, last_error=None)
        _state["last_sync_at"] = datetime.now(timezone.utc).isoformat()
        outbox.prune(settings.EDGE_KEEP_SYNCED)
    finally:
        if own_client:
            client.close()
    return stats


def _sync_loop() -> None:
    with httpx.Client(timeout=30) as client:
        while not _stop.is_set():
            try:
                sync_once(client)
            except Exception as e:  # never let the sync thread die
                log.warning("Edge sync error: %s", e)
            if time.monotonic() - _state["last_model_check"] >= settings.EDGE_MODEL_CHECK_SECONDS:
                try:
                    check_model_update(client)
                except Exception as e:
                    log.warning("Edge model update failed (keeping current model): %s", e)
            _wake.wait(settings.EDGE_SYNC_INTERVAL_SECONDS)
            _wake.clear()


def _fetch_device_identity() -> None:
    if not settings.EDGE_DEVICE_KEY:
        return
    try:
        resp = httpx.get(_central("/edge/ping"), headers={"X-Device-Key": settings.EDGE_DEVICE_KEY}, timeout=5)
        if resp.status_code == 200:
            _state["device"] = resp.json()
    except httpx.HTTPError:
        pass  # offline at boot is fine; identity is only informational


@asynccontextmanager
async def lifespan(_: FastAPI):
    _fetch_device_identity()
    thread = threading.Thread(target=_sync_loop, name="edge-sync", daemon=True)
    thread.start()
    yield
    _stop.set()
    _wake.set()


app = FastAPI(title="ParakhMaan Edge Node", version=settings.VERSION, lifespan=lifespan)


def _inspect(image: np.ndarray, raw_jpeg: Optional[bytes], max_side: int, context: Dict[str, Any]) -> Dict[str, Any]:
    detector = current_detector()
    scan = detector.detect(image, max_side=max_side)
    model_version = detector.model_version if "ONNX" in scan["backend"] else None
    scan_meta = {k: scan[k] for k in ("latency_ms", "fps", "backend", "image_size", "product_mask_used",
                                      "reference_used", "mean_brightness", "exposure_ok", "outcome")}
    scan_meta["detection_count"] = len(scan["detections"])
    scan_meta["model_version"] = model_version
    jpeg = raw_jpeg if raw_jpeg and raw_jpeg.startswith(b"\xff\xd8\xff") else cv2.imencode(
        ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
    local_id = outbox.add(jpeg, {**context, "outcome": scan["outcome"], "detections": scan["detections"], "scan": scan_meta})
    _wake.set()
    return {"local_id": local_id, "outcome": scan["outcome"], "detections": scan["detections"], **scan_meta, "queued": True}


@app.post("/infer")
async def infer(
    file: UploadFile = File(...),
    product_id: Optional[str] = Form(None),
    batch_code: Optional[str] = Form(None),
    shift: Optional[str] = Form(None),
    max_side: int = Form(1024),
):
    data = await file.read(settings.MAX_IMAGE_MB * 1024 * 1024 + 1)
    if len(data) > settings.MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image too large")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Unreadable image")
    context = {"product_id": product_id, "batch_code": batch_code, "shift": shift}
    return _inspect(image, data, max(160, min(max_side, 1920)), context)


@app.post("/infer/frame")
def infer_frame(payload: dict = Body(...)):
    """Base64 frame from a camera loop; same pipeline as /infer."""
    image = decode_base64_image(str(payload.get("image_base64", "")))
    if image is None:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")
    context = {k: payload.get(k) for k in ("product_id", "batch_code", "shift")}
    return _inspect(image, None, int(payload.get("max_side", 960)), context)


@app.post("/sync")
def trigger_sync():
    return sync_once()


@app.get("/queue")
def get_queue(status: Optional[str] = None, limit: int = 50):
    return {"counts": outbox.counts(), "items": outbox.recent(status, max(1, min(limit, 500)))}


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "role": "edge",
        "central_url": settings.EDGE_CENTRAL_URL,
        "device_key_configured": bool(settings.EDGE_DEVICE_KEY),
        "device": _state["device"],
        "detector": current_detector().status(),
        "registry_model": _state["model"],
        "queue": outbox.counts(),
        "last_sync_at": _state["last_sync_at"],
        "last_sync_ok": _state["last_sync_ok"],
        "last_error": _state["last_error"],
    }
