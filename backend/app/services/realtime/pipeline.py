"""Continuous inspection session.

    source ─▶ frame queue (bounded, oldest dropped) ─▶ tracker (every queued frame)
                                                        │ one crop per physical unit
                                                        ▼
                                        inspection worker ─▶ decision ─▶ log ─▶ reject signal

Frames are dropped only when the tracker cannot keep up, and each drop is counted and displayed.
A unit is never dropped silently: if inspection falls behind it is logged as MANUAL_REVIEW.
"""
import logging
import queue
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional

import numpy as np

from app.core.database import SessionLocal
from app.models.industrial import Batch, Machine, Product, ProductionLine, RejectEvent
from app.services.inspection_service import record_unit, run_inspection
from app.services.line.actuator import RejectCommand, SimulatedActuator, build_actuator, fire_delay_ms, latency_budget
from app.services.line.decision import MANUAL_REVIEW, REJECT
from app.services.realtime.tracker import UnitTracker

logger = logging.getLogger(__name__)
UNIT_QUEUE = 32
RECENT = 30


@dataclass
class SessionConfig:
    product_id: Optional[str] = None
    batch_id: Optional[str] = None
    machine_id: Optional[str] = None
    line_id: Optional[str] = None
    source_kind: str = "BROWSER"  # BROWSER, CONVEYOR_SIM, VIDEO_FILE, CAMERA, RTSP
    is_synthetic: bool = False
    trigger_x_ratio: float = 0.55
    frame_queue: int = 8
    crop_pad: float = 0.0
    tracker: Dict[str, Any] = field(default_factory=dict)


class LiveSession:
    def __init__(self, config: SessionConfig, frames: Optional[Iterable[np.ndarray]] = None):
        self.id = uuid.uuid4().hex[:12]
        self.config = config
        self.frames = frames
        self.frame_queue: Deque[np.ndarray] = deque(maxlen=config.frame_queue)
        self.frame_ready = threading.Condition()
        self.unit_queue: "queue.Queue[Any]" = queue.Queue(maxsize=UNIT_QUEUE)
        self.tracker = UnitTracker(trigger_x_ratio=config.trigger_x_ratio, **config.tracker)
        self.stop_event = threading.Event()
        self.source_done = threading.Event()
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.frames_in = 0
        self.frames_tracked = 0
        self.frames_dropped = 0
        self.units_overflowed = 0
        self.decisions: Dict[str, int] = {}
        self.units_inspected = 0
        self.inspect_ms: Deque[float] = deque(maxlen=500)
        self.track_ms: Deque[float] = deque(maxlen=500)
        self.recent: Deque[Dict[str, Any]] = deque(maxlen=RECENT)
        self.overlay_rows: List[Dict[str, Any]] = []
        self.last_frame_size: Optional[List[int]] = None
        self.errors: List[str] = []
        self.actuator: Any = SimulatedActuator()
        self.budget: Optional[Dict[str, Any]] = None
        self._threads: List[threading.Thread] = []

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> "LiveSession":
        db = SessionLocal()
        try:
            if self.config.line_id:
                line = db.get(ProductionLine, self.config.line_id)
                if line:
                    self.actuator = build_actuator(line.actuator_kind, line.actuator_target or "")
                    self.budget = latency_budget(line.belt_speed_mm_s, line.camera_to_diverter_mm, line.pitch_mm)
        finally:
            db.close()
        targets: List[Callable[[], None]] = [self._track_loop, self._inspect_loop]
        if self.frames is not None:
            targets.insert(0, self._capture_loop)
        for target in targets:
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        return self

    def stop(self) -> None:
        self.source_done.set()
        self.stop_event.set()
        with self.frame_ready:
            self.frame_ready.notify_all()

    def finish_source(self) -> None:
        """The source ended: finish what is queued, then stop."""
        self.source_done.set()
        with self.frame_ready:
            self.frame_ready.notify_all()

    def join(self, timeout: float = 120.0) -> None:
        for t in self._threads:
            t.join(timeout)

    # ------------------------------------------------------------------ stages
    def push(self, frame: np.ndarray) -> None:
        with self.frame_ready:
            if len(self.frame_queue) == self.frame_queue.maxlen:
                self.frames_dropped += 1
            self.frame_queue.append(frame)
            self.frames_in += 1
            self.frame_ready.notify()

    def _capture_loop(self) -> None:
        try:
            for frame in self.frames:
                if self.stop_event.is_set():
                    break
                self.push(frame)
        except Exception as e:
            self.errors.append(f"Source failed: {e}")
            logger.exception("frame source")
        self.finish_source()

    def _track_loop(self) -> None:
        while True:
            with self.frame_ready:
                while not self.frame_queue and not self.source_done.is_set():
                    self.frame_ready.wait(0.5)
                if not self.frame_queue:
                    break
                frame = self.frame_queue.popleft()
            t = time.perf_counter()
            triggered, rows = self.tracker.update(frame)
            self.track_ms.append((time.perf_counter() - t) * 1000)
            self.frames_tracked += 1
            self.overlay_rows, self.last_frame_size = rows, [frame.shape[1], frame.shape[0]]
            for track in triggered:
                item = {"crop": track.best_crop, "track_id": track.track_id, "triggered_at": time.time()}
                try:
                    self.unit_queue.put_nowait(item)
                except queue.Full:
                    self.units_overflowed += 1
                    self._log_overflow(item)
        self.unit_queue.put(None)

    def _inspect_loop(self) -> None:
        db = SessionLocal()
        try:
            context = self._context(db)
            while True:
                item = self.unit_queue.get()
                if item is None:
                    break
                try:
                    self._inspect_one(db, item, context)
                except Exception as e:
                    db.rollback()
                    self.errors.append(f"Unit {item['track_id']}: {e}")
                    logger.exception("unit inspection")
        finally:
            self.finished_at = time.time()
            db.close()

    def _context(self, db) -> Dict[str, Any]:
        c = self.config
        return {
            "product": db.get(Product, c.product_id) if c.product_id else None,
            "batch": db.get(Batch, c.batch_id) if c.batch_id else None,
            "machine": db.get(Machine, c.machine_id) if c.machine_id else None,
            "line": db.get(ProductionLine, c.line_id) if c.line_id else None,
        }

    def _source_label(self) -> str:
        return "SIMULATED" if self.config.is_synthetic else "LIVE"

    def _inspect_one(self, db, item: Dict[str, Any], ctx: Dict[str, Any]) -> None:
        t = time.perf_counter()
        result = run_inspection(db, item["crop"], ctx["product"])
        unit = record_unit(db, result, item["crop"], batch=ctx["batch"], machine=ctx["machine"], line=ctx["line"],
                           source=self._source_label(), is_synthetic=self.config.is_synthetic)
        elapsed_ms = (time.perf_counter() - t) * 1000
        self.inspect_ms.append(result["latency_ms"])
        self.units_inspected += 1
        self.decisions[result["decision"]] = self.decisions.get(result["decision"], 0) + 1

        fired = None
        if result["decision"] == REJECT:
            waited_ms = (time.time() - item["triggered_at"]) * 1000
            line = ctx["line"]
            delay = fire_delay_ms(line.belt_speed_mm_s, line.camera_to_diverter_mm, waited_ms) if line else 0.0
            if delay is None:
                # Too late to divert: this must be visible, because the part stayed on the belt.
                fired = {"actuator": self.actuator.kind, "status": "MISSED_WINDOW", "fire_after_ms": None}
            else:
                fired = self.actuator.fire(RejectCommand(unit.unit_code, delay, "; ".join(result["reasons"])[:200]))
            db.add(RejectEvent(unit_id=unit.id, actuator=fired["actuator"], status=fired["status"],
                               fire_after_ms=fired.get("fire_after_ms"), reason="; ".join(result["reasons"])[:500]))
            db.commit()
        self.recent.appendleft({
            "unit_code": unit.unit_code, "unit_id": unit.id, "track_id": item["track_id"], "decision": result["decision"],
            "reasons": result["reasons"], "latency_ms": result["latency_ms"], "total_ms": round(elapsed_ms, 1),
            "defects": [{"type": d["defect_type"], "severity": d["severity"], "confidence": d["confidence"]} for d in result["detections"][:6]],
            "reject": fired["status"] if fired else None, "at": datetime.now(timezone.utc).isoformat(),
        })

    def _log_overflow(self, item: Dict[str, Any]) -> None:
        db = SessionLocal()
        try:
            ctx = self._context(db)
            result = {"decision": MANUAL_REVIEW, "reasons": ["Inspection queue full: unit was not inspected"], "model_versions": {},
                      "streams": [], "latency_ms": None, "product_id": self.config.product_id, "detections": []}
            record_unit(db, result, item["crop"], batch=ctx["batch"], machine=ctx["machine"], line=ctx["line"],
                        source=self._source_label(), is_synthetic=self.config.is_synthetic)
            self.decisions[MANUAL_REVIEW] = self.decisions.get(MANUAL_REVIEW, 0) + 1
        finally:
            db.close()

    # ------------------------------------------------------------------ telemetry
    def stats(self) -> Dict[str, Any]:
        end = self.finished_at or time.time()
        elapsed = max(1e-6, end - self.started_at)
        inspect = sorted(self.inspect_ms)
        track = sorted(self.track_ms)

        def pct(values: List[float], q: float) -> Optional[float]:
            return round(values[min(len(values) - 1, int(q * len(values)))], 1) if values else None

        return {
            "session_id": self.id,
            "mode": "CONTINUOUS_TRACKED",
            "source": self.config.source_kind,
            "simulation": self.config.is_synthetic,
            "running": self.finished_at is None,
            "elapsed_s": round(elapsed, 1),
            "frames_received": self.frames_in,
            "frames_tracked": self.frames_tracked,
            "frames_dropped": self.frames_dropped,
            "ingest_fps": round(self.frames_in / elapsed, 1),
            "tracking_fps": round(self.frames_tracked / elapsed, 1),
            "tracker_ms_p50": pct(track, 0.5),
            "inspect_ms_p50": pct(inspect, 0.5),
            "inspect_ms_p95": pct(inspect, 0.95),
            "units_seen": self.tracker.units_seen,
            "units_inspected": self.units_inspected,
            "units_overflowed": self.units_overflowed,
            "decisions": dict(self.decisions),
            "throughput_units_min": round(self.units_inspected / elapsed * 60, 1),
            "actuator": self.actuator.kind,
            "budget": self.budget,
            "recent": list(self.recent),
            "tracks": self.overlay_rows,
            "frame_size": self.last_frame_size,
            "errors": self.errors[-5:],
        }


class SessionManager:
    def __init__(self) -> None:
        self.sessions: Dict[str, LiveSession] = {}
        self._lock = threading.Lock()

    def add(self, session: LiveSession) -> LiveSession:
        with self._lock:
            self.sessions[session.id] = session
            while len(self.sessions) > 8:  # keep recent finished sessions for the UI
                finished = next((k for k, s in self.sessions.items() if s.finished_at), None)
                if finished is None:
                    break
                del self.sessions[finished]
        return session

    def get(self, session_id: str) -> Optional[LiveSession]:
        return self.sessions.get(session_id)


manager = SessionManager()
