"""One inspection of one image: three independent evidence streams fused into a single result.

    Learned class    YOLO segmentation           what the defect is, and its mask
    Anomaly          per-product memory bank     that something is wrong, even if never labelled
    Classical        OpenCV pipeline             works with no model and supports golden comparison

Each stream can be absent. The result always says which streams actually ran.
"""
import base64
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.core.config import resolve_backend_path, settings
from app.services.defect_detection_service import DefectDetector, grade_severity
from app.services.inference.anomaly_engine import (
    FeatureExtractor, ProductModel, anomaly_regions, image_score, nearest_distance, score_map, to_patches,
)
from app.services.inference.seg_detector import SegDetector, mask_to_polygon

logger = logging.getLogger(__name__)
UNKNOWN = "UNKNOWN_ANOMALY"
# A classical finding needs anomaly-map evidence of at least this fraction of the pixel threshold.
CLASSICAL_CORROBORATION = 1.2  # chosen on the val split (docs/MODELS.md); at this value golden comparison never raised false rejects on val


def _overlap_ratio(mask: np.ndarray, other: np.ndarray) -> float:
    area = int(mask.sum())
    return float((mask & other).sum()) / area if area else 0.0


class InspectionEngine:
    def __init__(self) -> None:
        self.seg: Optional[SegDetector] = None
        self.seg_version: Optional[str] = None
        self.seg_error: Optional[str] = None
        self.extractor: Optional[FeatureExtractor] = None
        self.anomaly_error: Optional[str] = None
        self.products: Dict[str, ProductModel] = {}
        self.product_versions: Dict[str, str] = {}
        self.classical = DefectDetector(model_path="", backend="opencv")
        self.review_conf = settings.INSPECT_REVIEW_CONFIDENCE
        self._lock = threading.Lock()
        self.load_default_models()

    # ------------------------------------------------------------------ models
    def load_default_models(self) -> None:
        self.load_seg(resolve_backend_path(settings.SEG_MODEL_PATH), settings.SEG_MODEL_VERSION)
        backbone = resolve_backend_path(settings.ANOMALY_BACKBONE_PATH)
        if backbone and os.path.exists(backbone):
            try:
                self.extractor = FeatureExtractor(backbone)
            except Exception as e:  # corrupt or incompatible model must not stop the service
                self.anomaly_error = f"Backbone failed to load: {e}"
                logger.exception("anomaly backbone")
        else:
            self.anomaly_error = f"Backbone not found: {backbone}"
        folder = resolve_backend_path(settings.ANOMALY_PRODUCTS_DIR)
        if folder and os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                if os.path.exists(os.path.join(folder, name, "memory_bank.npz")):
                    self.load_product(name, os.path.join(folder, name), f"{name}-base")

    def load_seg(self, path: str, version: Optional[str]) -> bool:
        if not path or not os.path.exists(path):
            self.seg, self.seg_version, self.seg_error = None, None, f"Segmentation model not found: {path}"
            return False
        try:
            self.seg = SegDetector(path, conf=settings.SEG_CONF_THRESHOLD)
            self.seg_version, self.seg_error = version or os.path.basename(path), None
            return True
        except Exception as e:
            self.seg, self.seg_version, self.seg_error = None, None, f"Segmentation model failed: {e}"
            logger.exception("seg model")
            return False

    def load_product(self, key: str, folder: str, version: str) -> None:
        model = ProductModel.load(folder)
        with self._lock:
            self.products[key] = model
            self.product_versions[key] = version

    def unload_product(self, key: str) -> None:
        with self._lock:
            self.products.pop(key, None)
            self.product_versions.pop(key, None)

    def status(self) -> Dict[str, Any]:
        return {
            "segmentation": {"loaded": self.seg is not None, "version": self.seg_version, "error": self.seg_error,
                             "classes": self.seg.classes if self.seg else [],
                             "input_size": self.seg.input_size if self.seg else None,
                             "providers": self.seg.providers if self.seg else []},
            "anomaly": {"loaded": self.extractor is not None, "error": self.anomaly_error,
                        "input_size": self.extractor.input_size if self.extractor else None,
                        "products": sorted(self.products), "versions": dict(self.product_versions)},
            "classical": {"loaded": True, "opencv": cv2.__version__},
        }

    # ------------------------------------------------------------------ identification
    def identify_product(self, image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Nearest product prototype by cosine similarity of global appearance."""
        if self.extractor is None or not self.products:
            return None
        features = self.extractor([image])
        best_key, best, second = None, -1.0, -1.0
        for key, model in self.products.items():
            patches, _ = to_patches(features, model.projection)
            g = patches.mean(axis=0)
            sim = float(g @ model.prototype / max(1e-9, np.linalg.norm(g) * np.linalg.norm(model.prototype)))
            if sim > best:
                best_key, second, best = key, best, sim
            elif sim > second:
                second = sim
        return {"product_key": best_key, "similarity": round(best, 4), "margin": round(best - second, 4)}

    # ------------------------------------------------------------------ inspection
    def inspect(
        self,
        image: np.ndarray,
        product_key: Optional[str] = None,
        reference: Optional[np.ndarray] = None,
        use_classical: Optional[bool] = None,
        want_heatmap: bool = True,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        h, w = image.shape[:2]
        timings: Dict[str, float] = {}
        streams: List[str] = []
        identification = None
        if product_key is None:
            identification = self.identify_product(image)
            if identification and identification["similarity"] >= settings.PRODUCT_ID_MIN_SIMILARITY:
                product_key = identification["product_key"]

        seg_dets: List[Dict[str, Any]] = []
        if self.seg is not None:
            t = time.perf_counter()
            seg_dets = self.seg.detect(image)
            timings["segmentation_ms"] = round((time.perf_counter() - t) * 1000, 1)
            streams.append("YOLO_SEG")

        amap, a_score, a_norm, regions = None, None, None, []
        suppressed_classical = 0
        anomalous_area = np.zeros((h, w), dtype=bool)
        model = self.products.get(product_key) if product_key else None
        if model is not None and self.extractor is not None:
            t = time.perf_counter()
            amap = score_map(self.extractor, model, image)
            a_score = image_score(amap)
            a_norm = a_score / max(model.image_threshold, 1e-9)
            s = amap.shape[0]
            if a_score >= model.image_threshold:
                for region in anomaly_regions(amap, model.pixel_threshold, (w / s, h / s)):
                    region["mask"] = cv2.resize(region["mask"].astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
                    region["peak_norm"] = region["peak"] / max(model.pixel_threshold, 1e-9)
                    regions.append(region)
                    anomalous_area |= region["mask"]
            timings["anomaly_ms"] = round((time.perf_counter() - t) * 1000, 1)
            streams.append("ANOMALY")

        detections: List[Dict[str, Any]] = []
        for d in seg_dets:
            detection = dict(d)
            metrics = {"method": "yolo_segmentation", "model_confidence": round(d["confidence"], 3)}
            mask = d["mask"]
            if model is not None:
                agreement = _overlap_ratio(mask, anomalous_area)
                metrics["anomaly_overlap"] = round(agreement, 3)
                if agreement >= 0.1:
                    detection["detector"] = "YOLO_SEG+ANOMALY"
                    detection["confidence"] = 1 - (1 - d["confidence"]) * (1 - min(0.8, (a_norm or 1) - 0.5))
                elif a_norm is not None and a_norm < 1.0:
                    # The product-specific model sees a normal part: downgrade instead of rejecting.
                    detection["confidence"] = d["confidence"] * max(0.35, a_norm)
                    metrics["unconfirmed_by_anomaly_model"] = True
            metrics["mask_area_px"] = int(mask.sum())
            detection["metrics"] = metrics
            detections.append(detection)

        for region in regions:
            if any(_overlap_ratio(region["mask"], d["mask"]) >= 0.2 for d in detections):
                continue
            conf = float(min(0.95, 0.5 + 0.2 * (region["peak_norm"] - 1)))
            detections.append({
                "defect_type": UNKNOWN, "bbox": region["bbox"], "confidence": conf, "detector": "ANOMALY",
                "mask": region["mask"],
                "metrics": {"method": "memory_bank_anomaly", "peak_over_threshold": round(region["peak_norm"], 2),
                            "mask_area_px": int(region["mask"].sum())},
            })

        run_classical = use_classical if use_classical is not None else (self.seg is None and model is None) or reference is not None
        if run_classical:
            t = time.perf_counter()
            classical = self.classical.detect(image, reference)
            timings["classical_ms"] = round((time.perf_counter() - t) * 1000, 1)
            streams.append("OPENCV")
            for c in classical["detections"]:
                if any(_box_overlap(c["bbox"], d["bbox"]) > 0.3 for d in detections):
                    continue
                if amap is not None and model is not None:
                    # The classical/golden detector was built for flat labels and is unvalidated on
                    # parts: on MVTec test goods it rejected rotated parts. With a learned anomaly
                    # model present, a classical finding counts only where the anomaly map agrees.
                    support = _anomaly_support(amap, c["bbox"], w, h) / max(model.pixel_threshold, 1e-9)
                    if support < CLASSICAL_CORROBORATION:
                        suppressed_classical += 1
                        continue
                    c = {**c, "metrics": {**(c.get("metrics") or {}), "anomaly_support": round(support, 2)}}
                detections.append({**c, "mask": None})

        final = [self._finish(d, w, h) for d in detections]
        final.sort(key=lambda d: (-_SEV[d["severity"]], -d["confidence"]))
        brightness = float(image.mean())
        latency = (time.perf_counter() - t0) * 1000
        return {
            "detections": final[:40],
            "product_key": product_key,
            "identification": identification,
            "anomaly": None if a_score is None else {
                "score": round(a_score, 4), "threshold": round(model.image_threshold, 4),
                "normalised": round(a_norm, 3), "is_anomalous": a_score >= model.image_threshold,
                "model_version": self.product_versions.get(product_key),
            },
            "heatmap_jpeg": _heatmap_jpeg(image, amap, model) if want_heatmap and amap is not None else None,
            "streams": streams,
            "model_versions": {"segmentation": self.seg_version,
                               "anomaly": self.product_versions.get(product_key) if model else None},
            "timings": timings,
            "latency_ms": round(latency, 1),
            "fps": round(1000.0 / latency, 1) if latency else None,
            "image_size": [w, h],
            "mean_brightness": round(brightness, 1),
            "exposure_ok": 35.0 <= brightness <= 240.0,
            "reference_used": reference is not None,
            "classical_suppressed": suppressed_classical,
        }

    def _finish(self, d: Dict[str, Any], w: int, h: int) -> Dict[str, Any]:
        x1, y1, x2, y2 = d["bbox"]
        x1, x2 = max(0.0, min(float(w), x1)), max(0.0, min(float(w), x2))
        y1, y2 = max(0.0, min(float(h), y1)), max(0.0, min(float(h), y2))
        mask = d.pop("mask", None)
        metrics = d.setdefault("metrics", {})
        area_ratio = ((x2 - x1) * (y2 - y1)) / float(w * h)
        if mask is not None:
            metrics["mask_polygon"] = mask_to_polygon(mask)
            metrics["mask_area_ratio"] = round(float(mask.sum()) / (w * h), 6)
            metrics.setdefault("surface_area_ratio", metrics["mask_area_ratio"])
            contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                c = max(contours, key=cv2.contourArea)
                (_, _), (a, b), _ = cv2.minAreaRect(c)
                metrics["length_px"] = round(float(max(a, b)), 1)
                metrics["width_px"] = round(float(min(a, b)), 1)
                metrics.setdefault("length_ratio", round(float(max(a, b)) / float(np.hypot(w, h)), 4))
        metrics["bbox_norm"] = [round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4)]
        d.update(bbox=[round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)], area_ratio=round(area_ratio, 5),
                 confidence=round(float(d["confidence"]), 3))
        d["severity"] = grade_severity(d)
        d.setdefault("reviewer_status", "PENDING")
        return d


_SEV = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _anomaly_support(amap: np.ndarray, bbox: List[float], w: int, h: int) -> float:
    """Peak anomaly score inside an image-space box, read from the (s x s) anomaly map."""
    s = amap.shape[0]
    x1, y1, x2, y2 = bbox
    c1, r1 = int(np.floor(x1 / w * s)), int(np.floor(y1 / h * s))
    c2, r2 = max(c1 + 1, int(np.ceil(x2 / w * s))), max(r1 + 1, int(np.ceil(y2 / h * s)))
    region = amap[max(0, r1):min(s, r2), max(0, c1):min(s, c2)]
    return float(region.max()) if region.size else 0.0


def _box_overlap(a: List[float], b: List[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / smaller if smaller > 0 else 0.0


def _heatmap_jpeg(image: np.ndarray, amap: np.ndarray, model: ProductModel) -> Optional[bytes]:
    h, w = image.shape[:2]
    low, high = float(np.percentile(amap, 5)), max(model.pixel_threshold * 1.5, float(amap.max()))
    norm = np.clip((amap - low) / max(high - low, 1e-6), 0, 1)
    colour = cv2.applyColorMap((cv2.resize(norm, (w, h)) * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    ok, buf = cv2.imencode(".jpg", cv2.addWeighted(image, 0.5, colour, 0.5, 0), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok else None


def heatmap_data_url(jpeg: Optional[bytes]) -> Optional[str]:
    return f"data:image/jpeg;base64,{base64.b64encode(jpeg).decode()}" if jpeg else None


engine = InspectionEngine()
