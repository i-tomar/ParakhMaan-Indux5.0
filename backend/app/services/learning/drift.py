"""
Input-drift monitoring per station with the Population Stability Index (PSI).

For each station the recent window is compared with a baseline window on three distributions that
need no labels: image brightness, the strongest detection confidence per image, and detections per
image. PSI < 0.10 is stable, 0.10-0.25 worth watching, > 0.25 a significant shift (new lighting,
camera moved, new material batch...). Drifting stations get a higher review sampling rate.
"""
import math
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.all_models import DefectDetection, Image, Inspection, Station

BRIGHTNESS_BINS = [0, 35, 70, 105, 140, 175, 210, 240, 256]
CONFIDENCE_BINS = [0.0, 0.01, 0.3, 0.5, 0.7, 0.9, 1.01]  # first bin = no detection
COUNT_BINS = [0, 1, 2, 3, 1000]
MIN_BASELINE = 20
MIN_RECENT = 10


def _histogram(values: List[float], edges: List[float]) -> List[int]:
    counts = [0] * (len(edges) - 1)
    for v in values:
        for i in range(len(edges) - 1):
            if edges[i] <= v < edges[i + 1]:
                counts[i] += 1
                break
    return counts


def psi(expected: List[int], actual: List[int], eps: float = 1e-4) -> float:
    e_total, a_total = sum(expected), sum(actual)
    if not e_total or not a_total:
        return 0.0
    value = 0.0
    for e, a in zip(expected, actual):
        pe, pa = max(e / e_total, eps), max(a / a_total, eps)
        value += (pa - pe) * math.log(pa / pe)
    return round(value, 4)


def classify(value: float) -> str:
    if value >= settings.DRIFT_PSI_ALERT:
        return "ALERT"
    if value >= settings.DRIFT_PSI_WATCH:
        return "WATCH"
    return "OK"


def station_drift(db: Session, organization_id: str, recent_hours: int = 24, baseline_days: int = 14,
                  now: Optional[datetime] = None) -> List[Dict]:
    now = now or datetime.now(timezone.utc)
    recent_start = (now - timedelta(hours=recent_hours)).replace(tzinfo=None)
    baseline_start = (now - timedelta(days=baseline_days)).replace(tzinfo=None)

    rows = (
        db.query(Image.id, Image.created_at, Image.quality_metadata, Inspection.station_id)
        .join(Inspection, Inspection.id == Image.inspection_id)
        .filter(Inspection.organization_id == organization_id, Inspection.inspection_mode == "DEFECT",
                Image.surface_type != "REFERENCE", Image.created_at >= baseline_start)
        .all()
    )
    image_ids = [r[0] for r in rows]
    det_conf: Dict[str, List[float]] = defaultdict(list)
    if image_ids:
        for image_id, conf, status in db.query(DefectDetection.image_id, DefectDetection.confidence,
                                               DefectDetection.reviewer_status).filter(
                DefectDetection.image_id.in_(image_ids), DefectDetection.detector != "HUMAN"):
            det_conf[image_id].append(conf or 0.0)

    windows: Dict[Optional[str], Dict[str, Dict[str, list]]] = defaultdict(
        lambda: {"baseline": defaultdict(list), "recent": defaultdict(list)})
    for image_id, created_at, meta, station_id in rows:
        created = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
        window = "recent" if created >= recent_start else "baseline"
        scan = (meta or {}).get("defect_scan", {})
        bucket = windows[station_id][window]
        if isinstance(scan.get("mean_brightness"), (int, float)):
            bucket["brightness"].append(float(scan["mean_brightness"]))
        confs = det_conf.get(image_id, [])
        bucket["confidence"].append(max(confs) if confs else 0.0)
        bucket["count"].append(len(confs))

    names = {s.id: s.name for s in db.query(Station).filter(Station.id.in_([k for k in windows if k])).all()}
    result = []
    for station_id, w in windows.items():
        n_base, n_recent = len(w["baseline"]["count"]), len(w["recent"]["count"])
        entry = {"station_id": station_id, "station": names.get(station_id, "Unassigned"),
                 "baseline_images": n_base, "recent_images": n_recent, "features": {}}
        if n_base < MIN_BASELINE or n_recent < MIN_RECENT:
            entry.update(status="INSUFFICIENT_DATA", psi=None)
            result.append(entry)
            continue
        for feature, edges in (("brightness", BRIGHTNESS_BINS), ("confidence", CONFIDENCE_BINS), ("count", COUNT_BINS)):
            base, recent = w["baseline"][feature], w["recent"][feature]
            if base and recent:
                value = psi(_histogram(base, edges), _histogram(recent, edges))
                entry["features"][feature] = {"psi": value, "status": classify(value)}
        worst = max((f["psi"] for f in entry["features"].values()), default=0.0)
        entry.update(psi=worst, status=classify(worst))
        result.append(entry)
    return sorted(result, key=lambda e: -(e["psi"] or 0))


class _DriftCache:
    """Sampler-side cache: drift status per station, refreshed at most every ttl seconds per organisation."""

    def __init__(self, ttl: float = 600.0):
        self.ttl = ttl
        self._data: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    def status(self, organization_id: Optional[str], station_id: Optional[str]) -> str:
        if not organization_id:
            return "OK"
        with self._lock:
            cached = self._data.get(organization_id)
        if not cached or time.monotonic() - cached[0] > self.ttl:
            db = SessionLocal()
            try:
                stations = {e["station_id"]: e["status"] for e in station_drift(db, organization_id)}
            except Exception:
                stations = {}
            finally:
                db.close()
            cached = (time.monotonic(), stations)
            with self._lock:
                self._data[organization_id] = cached
        return cached[1].get(station_id, "OK")

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


drift_cache = _DriftCache()
