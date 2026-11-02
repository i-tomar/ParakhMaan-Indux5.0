"""Measured edge-node telemetry. Values are read from the running process, never configured."""
import json
import os
import platform
try:
    import resource
except ImportError:
    resource = None
import sys
import time
from typing import Any, Dict

import cv2
import numpy as np
from fastapi import APIRouter

from app.core.config import settings
from app.services.inference.engine import engine
from app.services.line.actuator import latency_budget
from app.services.realtime.pipeline import manager

router = APIRouter(prefix="/edge", tags=["Edge Runtime"])
STARTED = time.time()


def _memory_mb() -> float:
    if resource is not None:
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024, 1)
    return 0.0


@router.get("/status")
def status() -> Dict[str, Any]:
    import onnxruntime as ort

    return {
        "device": {"machine": platform.machine(), "system": platform.system(), "release": platform.release(),
                   "processor": platform.processor(), "cpu_count": os.cpu_count(), "python": platform.python_version()},
        "runtime": {"onnxruntime": ort.__version__, "available_providers": ort.get_available_providers(), "opencv": cv2.__version__},
        "models": engine.status(),
        "process": {"peak_memory_mb": _memory_mb(), "uptime_s": round(time.time() - STARTED, 1)},
        "sessions": [s.stats() for s in manager.sessions.values() if s.finished_at is None],
        "verified_hardware": ["Apple M1 Pro (development machine)"],
        "unverified_hardware": ["NVIDIA Jetson", "Raspberry Pi", "Industrial PCs"],
    }


@router.post("/benchmark")
def benchmark(runs: int = 20, size: int = 640, product_key: str = "") -> Dict[str, Any]:
    """Times the real pipeline on this device with a synthetic noise frame (timing only)."""
    runs = max(5, min(runs, 200))
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (size, size, 3), dtype=np.uint8)
    key = product_key or None
    engine.inspect(frame, key, want_heatmap=False)  # warm-up, not counted
    times = []
    started = time.perf_counter()
    for _ in range(runs):
        times.append(engine.inspect(frame, key, want_heatmap=False)["latency_ms"])
    elapsed = time.perf_counter() - started
    times.sort()
    return {"runs": runs, "frame_size": size, "product_key": key, "p50_ms": times[len(times) // 2],
            "p95_ms": times[int(len(times) * 0.95) - 1], "fps": round(runs / elapsed, 1), "note": "Input is a noise frame; timing only"}


@router.get("/evaluation")
def evaluation() -> Dict[str, Any]:
    """Stored model reports produced by ml/. Nothing here is computed or defaulted."""
    out: Dict[str, Any] = {}
    for key, name in (("anomaly", "eval_anomaly.json"), ("segmentation", "eval_segmentation.json"), ("benchmark", "benchmark_edge.json")):
        path = os.path.join(settings.REPORTS_DIR, name)
        out[key] = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
    # Every stored benchmark (benchmark_*.json), each describing the device it was measured on.
    out["benchmarks"] = []
    if os.path.isdir(settings.REPORTS_DIR):
        for name in sorted(os.listdir(settings.REPORTS_DIR)):
            if name.startswith("benchmark_") and name.endswith(".json"):
                with open(os.path.join(settings.REPORTS_DIR, name), encoding="utf-8") as f:
                    out["benchmarks"].append({"file": name, **json.load(f)})
    return out


@router.get("/budget")
def budget(belt_speed_mm_s: float, camera_to_diverter_mm: float, pitch_mm: float) -> Dict[str, Any]:
    return latency_budget(belt_speed_mm_s, camera_to_diverter_mm, pitch_mm)
