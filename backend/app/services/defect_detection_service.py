import base64
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.core.config import resolve_backend_path, settings

DEFECT_TYPES = ["SCRATCH", "CRACK", "DENT", "DISCOLOURATION", "DIMENSIONAL_ANOMALY"]
SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

# Class names used by public surface-defect datasets (NEU-DET, GC10-DET, MVTec AD, ...)
# mapped onto the platform's canonical defect taxonomy.
MODEL_CLASS_ALIASES = {
    "scratch": "SCRATCH", "scratches": "SCRATCH", "abrasion": "SCRATCH",
    "crack": "CRACK", "cracks": "CRACK", "crazing": "CRACK", "crease": "CRACK",
    "dent": "DENT", "dents": "DENT", "pitted_surface": "DENT", "pit": "DENT", "punching_hole": "DENT",
    "discolouration": "DISCOLOURATION", "discoloration": "DISCOLOURATION", "stain": "DISCOLOURATION",
    "oil_spot": "DISCOLOURATION", "patches": "DISCOLOURATION", "rolled-in_scale": "DISCOLOURATION",
    "rust": "DISCOLOURATION", "contamination": "DISCOLOURATION",
    "deformation": "DIMENSIONAL_ANOMALY", "misshapen": "DIMENSIONAL_ANOMALY", "dimensional": "DIMENSIONAL_ANOMALY",
}


def _odd(n: int) -> int:
    n = max(3, int(n))
    return n if n % 2 == 1 else n + 1


def _iou(a: List[float], b: List[float]) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(1e-6, area_a + area_b - inter)


def _masked_blur(values: np.ndarray, mask: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur that only averages pixels inside the mask (normalized convolution)."""
    m = (mask > 0).astype(np.float32)
    h, w = values.shape[:2]
    # Wide kernels are smooth anyway; blurring at reduced resolution keeps this real-time.
    factor = max(1, int(sigma // 6))
    if factor > 1:
        small = (max(1, w // factor), max(1, h // factor))
        v_small = cv2.resize(values * m, small, interpolation=cv2.INTER_AREA)
        m_small = cv2.resize(m, small, interpolation=cv2.INTER_AREA)
        num = cv2.resize(cv2.GaussianBlur(v_small, (0, 0), sigma / factor), (w, h), interpolation=cv2.INTER_LINEAR)
        den = cv2.resize(cv2.GaussianBlur(m_small, (0, 0), sigma / factor), (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        num = cv2.GaussianBlur(values * m, (0, 0), sigma)
        den = cv2.GaussianBlur(m, (0, 0), sigma)
    return num / np.maximum(den, 1e-3)


def _line_kernels(length: int, orientations: int = 12) -> List[np.ndarray]:
    kernels = []
    c = length // 2
    for i in range(orientations):
        a = math.pi * i / orientations
        k = np.zeros((length, length), np.float32)
        dx, dy = math.cos(a) * c, math.sin(a) * c
        cv2.line(k, (int(round(c - dx)), int(round(c - dy))), (int(round(c + dx)), int(round(c + dy))), 1.0, 1, cv2.LINE_AA)
        kernels.append(k / k.sum())
    return kernels


def _oriented_line_response(resp: np.ndarray, length: int) -> np.ndarray:
    """
    Max over orientations of a mean filter along a line segment. Thin linear structures
    keep their strength, while isotropic texture (grain, pits, brushing noise) averages out.
    Computed at half resolution for speed.
    """
    h, w = resp.shape
    small = cv2.resize(resp.astype(np.float32), (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
    out = np.zeros_like(small)
    for k in _line_kernels(_odd(length // 2)):
        np.maximum(out, cv2.filter2D(small, -1, k), out=out)
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR)


def decode_base64_image(data: str) -> Optional[np.ndarray]:
    if "," in data:
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data)
    except Exception:
        return None
    arr = np.frombuffer(raw, dtype=np.uint8)
    if arr.size == 0:
        return None
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


class DefectDetector:
    """
    Hybrid product-surface defect detector.

    OpenCV baseline (no training data needed):
      - SCRATCH / CRACK: morphological black-hat / top-hat line extraction, classified by
        stroke straightness (scratches are straight, cracks are tortuous / branching).
      - DENT: local shading anomaly against a masked large-scale illumination model.
      - DISCOLOURATION: CIELAB colour deviation from a golden reference sample or the
        surface's own median colour.
      - DIMENSIONAL_ANOMALY: product contour vs golden reference (aspect, area, shape),
        or convexity defects (chipped / deformed edges) when no reference exists.

    Deep-learning plug-in: if DEFECT_MODEL_PATH points to a YOLOv8 ONNX export it runs
    through OpenCV DNN (no torch needed); in "hybrid" mode its detections take priority and
    OpenCV fills in classes the model does not cover.
    """

    WORK_MAX_SIDE = 1024
    MAX_DETECTIONS = 40

    def __init__(self, model_path: Optional[str] = None, model_classes: Optional[str] = None, backend: Optional[str] = None):
        self.backend = (backend or settings.DEFECT_DETECTOR_BACKEND or "hybrid").lower()
        self._model_path = resolve_backend_path(settings.DEFECT_MODEL_PATH if model_path is None else model_path)
        self._class_spec = settings.DEFECT_MODEL_CLASSES if model_classes is None else model_classes
        self._net = None
        self._input_size = 0
        self._classes: List[str] = []
        self._model_error: Optional[str] = None
        # cv2.dnn.Net is not thread-safe and FastAPI serves sync endpoints from a thread pool.
        self._net_lock = threading.Lock()
        self._load_model()

    # ------------------------------------------------------------------ model plug-in
    def _load_model(self) -> None:
        path = self._model_path
        if not path:
            return
        if not os.path.exists(path):
            self._model_error = f"Model file not found: {path}"
            return
        try:
            net = cv2.dnn.readNetFromONNX(path)
        except Exception as e:
            self._model_error = f"Failed to load ONNX model: {e}"
            return

        if self._class_spec:
            self._classes = [c.strip() for c in self._class_spec.split(",") if c.strip()]
        else:
            folder = os.path.dirname(path)
            candidates = [os.path.splitext(path)[0] + ".names"] + sorted(
                os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".names")
            )
            names_path = next((p for p in candidates if os.path.exists(p)), None)
            if names_path:
                with open(names_path, "r", encoding="utf-8") as f:
                    self._classes = [line.strip() for line in f if line.strip()]

        # Exports usually have a fixed input size; probe for it instead of relying on configuration.
        sizes = [settings.DEFECT_MODEL_INPUT_SIZE] if settings.DEFECT_MODEL_INPUT_SIZE > 0 else []
        sizes += [s for s in (640, 320, 416, 512, 1280) if s not in sizes]
        previous_log_level = cv2.setLogLevel(0)  # wrong sizes make OpenCV log shape errors
        try:
            for size in sizes:
                try:
                    net.setInput(cv2.dnn.blobFromImage(np.zeros((size, size, 3), np.uint8), 1 / 255.0, (size, size), swapRB=True))
                    out = np.squeeze(net.forward())
                except cv2.error:
                    continue
                if out.ndim == 2:
                    self._net, self._input_size = net, size
                    outputs = min(out.shape) - 4
                    if self._classes and outputs not in (len(self._classes), len(self._classes) + 1):
                        self._model_error = f"Model has {outputs} class outputs but {len(self._classes)} class names were given"
                    break
        finally:
            cv2.setLogLevel(previous_log_level)
        if self._net is None:
            self._model_error = f"ONNX model did not accept any input size in {sizes}"

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.backend,
            "opencv_version": cv2.__version__,
            "model_loaded": self._net is not None,
            "model_path": self._model_path or None,
            "model_input_size": self._input_size or None,
            "model_classes": self._classes,
            "model_error": self._model_error,
            "defect_types": DEFECT_TYPES,
        }

    @staticmethod
    def canonical_type(name: str) -> str:
        key = name.strip().lower().replace(" ", "_")
        if key in MODEL_CLASS_ALIASES:
            return MODEL_CLASS_ALIASES[key]
        return "".join(ch if ch.isalnum() else "_" for ch in name.strip().upper()) or "UNKNOWN"

    # ------------------------------------------------------------------ public API
    def detect_file(self, image_path: str, reference_path: Optional[str] = None, max_side: Optional[int] = None) -> Dict[str, Any]:
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Unable to decode image: {image_path}")
        ref = cv2.imread(reference_path) if reference_path and os.path.exists(reference_path) else None
        return self.detect(img, ref, max_side=max_side)

    def detect(self, image: np.ndarray, reference: Optional[np.ndarray] = None, max_side: Optional[int] = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        h0, w0 = image.shape[:2]
        limit = max_side or self.WORK_MAX_SIDE
        scale = min(1.0, limit / float(max(h0, w0)))
        work = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1.0 else image
        ref_work = None
        if reference is not None:
            ref_work = cv2.resize(reference, (work.shape[1], work.shape[0]), interpolation=cv2.INTER_AREA)

        detections: List[Dict[str, Any]] = []
        backends: List[str] = []

        use_model = self._net is not None and self.backend in ("onnx", "hybrid")
        if use_model:
            detections.extend(self._detect_onnx(image))
            backends.append("ONNX")

        product_mask_used = False
        if self.backend in ("opencv", "hybrid") or not use_model:
            cv_dets, product_mask_used = self._detect_opencv(work, ref_work)
            for d in cv_dets:
                d["bbox"] = [v / scale for v in d["bbox"]]
            detections = self._fuse(detections, cv_dets)
            backends.append("OPENCV")

        detections = [self._finalize(d, w0, h0) for d in detections]
        detections = [d for d in detections if d is not None]
        detections.sort(key=lambda d: (SEVERITY_ORDER.get(d["severity"], 0), d["confidence"]), reverse=True)
        detections = detections[: self.MAX_DETECTIONS]

        brightness = float(work.mean())
        exposure_ok = 35.0 <= brightness <= 240.0
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "detections": detections,
            "outcome": compute_outcome(detections, quality_issue=not exposure_ok),
            "mean_brightness": round(brightness, 1),
            "exposure_ok": exposure_ok,
            "latency_ms": round(latency_ms, 1),
            "fps": round(1000.0 / latency_ms, 1) if latency_ms > 0 else None,
            "backend": "+".join(backends),
            "image_size": [w0, h0],
            "product_mask_used": product_mask_used,
            "reference_used": reference is not None,
        }

    # ------------------------------------------------------------------ OpenCV pipeline
    def _detect_opencv(self, img: np.ndarray, ref: Optional[np.ndarray]) -> Tuple[List[Dict[str, Any]], bool]:
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask, mask_used, contour = self._segment_product(img)

        # Stay away from the product silhouette so its outline is not read as a scratch/crack.
        erode_k = _odd(max(3, int(0.012 * min(h, w)))) if mask_used else 3
        inner = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_k, erode_k)))
        if cv2.countNonZero(inner) < 0.02 * h * w:
            return [], mask_used

        edges = cv2.Canny(gray, 60, 160)

        dets: List[Dict[str, Any]] = []
        line_dets = self._detect_linear_defects(gray, inner)
        dets.extend(line_dets)
        colour_dets, colour_mask = self._detect_discolouration(img, inner, edges, ref)
        dets.extend(colour_dets)
        for dent in self._detect_dents(gray, inner, edges, colour_mask):
            # The shading of a scratch/crack stroke itself is not a dent.
            dx1, dy1, dx2, dy2 = dent["bbox"]
            dent_area = max(1.0, (dx2 - dx1) * (dy2 - dy1))
            covered = max(
                (max(0.0, min(dx2, l["bbox"][2]) - max(dx1, l["bbox"][0])) *
                 max(0.0, min(dy2, l["bbox"][3]) - max(dy1, l["bbox"][1])) for l in line_dets),
                default=0.0,
            )
            if covered < 0.6 * dent_area:
                dets.append(dent)
        if ref is not None:
            dets = self._suppress_with_reference(img, ref, dets)
        dets.extend(self._detect_dimensional(img, contour, mask_used, ref))
        return self._nms(dets, 0.4), mask_used

    @staticmethod
    def _align_reference(ref: np.ndarray, img: np.ndarray) -> np.ndarray:
        """Warps the golden sample onto the test image; identity if features cannot be matched."""
        h, w = img.shape[:2]
        try:
            orb = cv2.ORB_create(1500)
            k1, d1 = orb.detectAndCompute(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), None)
            k2, d2 = orb.detectAndCompute(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None)
            if d1 is None or d2 is None or len(k1) < 15 or len(k2) < 15:
                return ref
            matches = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2), key=lambda m: m.distance)[:300]
            if len(matches) < 15:
                return ref
            src = np.float32([k1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
            dst = np.float32([k2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
            H, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
            if H is None or inliers is None or int(inliers.sum()) < 15:
                return ref
            return cv2.warpPerspective(ref, H, (w, h), borderMode=cv2.BORDER_REPLICATE)
        except cv2.error:
            return ref

    def _suppress_with_reference(self, img: np.ndarray, ref: np.ndarray, dets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Drops candidates whose region looks the same on the defect-free golden sample (printing, design features)."""
        if not dets:
            return dets
        aligned = self._align_reference(ref, img)
        a = cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), 1), cv2.COLOR_BGR2LAB).astype(np.float32)
        b = cv2.cvtColor(cv2.GaussianBlur(aligned, (0, 0), 1), cv2.COLOR_BGR2LAB).astype(np.float32)
        # Envelope comparison: a pixel only differs if it falls outside the reference's local
        # min/max, which tolerates a few pixels of residual misalignment.
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        upper, lower = cv2.dilate(b, k), cv2.erode(b, k)
        excess = np.maximum(a - upper, 0) + np.maximum(lower - a, 0)
        diff = np.linalg.norm(excess, axis=2)
        kept = []
        for d in dets:
            x1, y1, x2, y2 = [int(round(v)) for v in d["bbox"]]
            region = diff[max(0, y1):y2, max(0, x1):x2]
            if region.size == 0:
                continue
            # Thin line defects cover a tiny share of their box, so judge them on the strongest pixels.
            pct = 99 if d["defect_type"] in ("SCRATCH", "CRACK") else 80
            score = float(np.percentile(region, pct))
            if score >= 10.0:
                d["metrics"]["reference_diff"] = round(score, 1)
                kept.append(d)
        return kept

    def _segment_product(self, img: np.ndarray) -> Tuple[np.ndarray, bool, Optional[np.ndarray]]:
        """Separates a product from a plain background; falls back to the full frame for close-up surfaces."""
        h, w = img.shape[:2]
        full = np.full((h, w), 255, dtype=np.uint8)
        lab = cv2.cvtColor(cv2.GaussianBlur(img, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
        b = max(4, int(0.03 * min(h, w)))
        border = np.concatenate([
            lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3),
            lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3),
        ])
        bg = np.median(border, axis=0)
        spread = float(np.median(np.linalg.norm(border - bg, axis=1)))
        dist = np.linalg.norm(lab - bg, axis=2)
        fg = (dist > max(18.0, 4.0 * spread)).astype(np.uint8) * 255

        k = _odd(int(0.02 * min(h, w)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return full, False, None
        largest = max(contours, key=cv2.contourArea)
        ratio = cv2.contourArea(largest) / float(h * w)
        hull_area = cv2.contourArea(cv2.convexHull(largest))
        solidity = cv2.contourArea(largest) / hull_area if hull_area > 0 else 0.0
        if 0.15 <= ratio <= 0.95 and solidity >= 0.75:
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(mask, [largest], -1, 255, thickness=cv2.FILLED)
            return mask, True, largest
        return full, False, None

    def _detect_linear_defects(self, gray: np.ndarray, mask: np.ndarray) -> List[Dict[str, Any]]:
        h, w = gray.shape
        diag = math.hypot(w, h)
        smooth = cv2.GaussianBlur(gray, (3, 3), 0)
        k = _odd(max(9, int(min(h, w) * 0.02)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        responses = (
            ("DARK", cv2.morphologyEx(smooth, cv2.MORPH_BLACKHAT, kernel)),
            ("BRIGHT", cv2.morphologyEx(smooth, cv2.MORPH_TOPHAT, kernel)),
        )
        min_len = 0.04 * diag
        max_thickness = max(3.0, 0.008 * diag)
        join = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

        candidates: List[Dict[str, Any]] = []
        for polarity, resp in responses:
            line_resp = _oriented_line_response(resp, int(0.03 * diag))
            vals = line_resp[mask > 0][::7]
            if vals.size == 0:
                continue
            # Median/MAD of the oriented response: texture sets the noise floor, so only
            # structures that stay strong along a line clear it.
            med = float(np.median(vals))
            mad = 1.4826 * float(np.median(np.abs(vals - med)))
            thr = max(6.0, med + 8.0 * mad)
            binary = ((line_resp > thr) & (resp > thr) & (mask > 0)).astype(np.uint8) * 255
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, join)

            n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
            found: List[Dict[str, Any]] = []
            for i in range(1, n):
                x, y, bw, bh, area = stats[i]
                if area < 12 or math.hypot(bw, bh) < min_len:
                    continue
                comp = labels[y:y + bh, x:x + bw] == i
                ys, xs = np.nonzero(comp)
                pts = np.column_stack([xs + x, ys + y]).astype(np.float32)
                (_, _), (rw, rh), _ = cv2.minAreaRect(pts)
                length = float(max(rw, rh))
                if length < min_len:
                    continue
                thickness = area / max(length, 1.0)
                if thickness > max_thickness or length / max(thickness, 1.0) < 8.0:
                    continue

                vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
                perp = np.abs((pts[:, 0] - x0) * vy - (pts[:, 1] - y0) * vx)
                tortuosity = float(np.percentile(perp, 90)) / max(length, 1.0)
                contrast = float(resp[y:y + bh, x:x + bw][comp].mean())

                if polarity == "BRIGHT" or tortuosity <= 0.035:
                    dtype = "SCRATCH"
                else:
                    dtype = "CRACK"
                length_ratio = length / diag
                confidence = 0.45 + 0.3 * min(1.0, (contrast - thr) / max(thr, 1.0) + 0.3) + 0.2 * min(1.0, length_ratio / 0.2)
                found.append({
                    "defect_type": dtype,
                    "bbox": [float(x), float(y), float(x + bw), float(y + bh)],
                    "confidence": min(0.97, confidence),
                    "detector": "OPENCV",
                    "metrics": {
                        "method": "morphological_line_extraction",
                        "polarity": polarity,
                        "length_px": round(length, 1),
                        "length_ratio": round(length_ratio, 4),
                        "mean_thickness_px": round(thickness, 2),
                        "tortuosity": round(tortuosity, 4),
                        "contrast": round(contrast, 1),
                    },
                })
            # Dense line fields are texture or printing, not isolated defects: keep only the most salient.
            found.sort(key=lambda d: d["metrics"]["length_px"] * d["metrics"]["contrast"], reverse=True)
            candidates.extend(found[:12])
        return candidates

    def _reference_colour(self, ref: Optional[np.ndarray]) -> Optional[np.ndarray]:
        if ref is None:
            return None
        ref_mask, _, _ = self._segment_product(ref)
        ref_lab = self._lab(ref)
        return np.median(ref_lab[ref_mask > 0], axis=0)

    @staticmethod
    def _lab(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        sigma = max(2.0, min(h, w) / 200.0)
        lab = cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), sigma), cv2.COLOR_BGR2LAB).astype(np.float32)
        lab[..., 0] *= 100.0 / 255.0
        lab[..., 1] -= 128.0
        lab[..., 2] -= 128.0
        return lab

    def _detect_discolouration(
        self, img: np.ndarray, mask: np.ndarray, edges: np.ndarray, ref: Optional[np.ndarray]
    ) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        h, w = img.shape[:2]
        lab = self._lab(img)
        inside = mask > 0
        ref_colour = self._reference_colour(ref)
        reference_kind = "GOLDEN_SAMPLE" if ref_colour is not None else "SURFACE_MEDIAN"
        target = ref_colour if ref_colour is not None else np.median(lab[inside][::7], axis=0)

        diff = lab - target
        # Lightness is down-weighted so plain shading (dents, lighting) is not read as colour change.
        delta_e = np.sqrt((0.5 * diff[..., 0]) ** 2 + diff[..., 1] ** 2 + diff[..., 2] ** 2)
        thr = 10.0 if ref_colour is not None else 14.0
        # Rust, oxidation and stains on near-neutral metal shift hue far more than lightness,
        # so a chroma shift beyond the surface's own variation is flagged as well.
        chroma = np.sqrt(diff[..., 1] ** 2 + diff[..., 2] ** 2)
        c_vals = chroma[inside][::7]
        c_med = float(np.median(c_vals))
        c_mad = 1.4826 * float(np.median(np.abs(c_vals - c_med)))
        chroma_thr = max(6.0, c_med + 6.0 * c_mad)
        if ref_colour is not None:
            candidates = (delta_e > thr) | (chroma > chroma_thr)
        else:
            # Without a golden sample, lightness changes are indistinguishable from shadows and
            # uneven lighting, so only hue/chroma shifts count.
            candidates = chroma > chroma_thr
        binary = (candidates & inside).astype(np.uint8) * 255
        empty = np.zeros((h, w), dtype=np.uint8)

        mask_area = float(np.count_nonzero(inside))
        # A multi-coloured surface (printed artwork) has no single "normal" colour to compare against.
        if ref_colour is None and np.count_nonzero(binary) > 0.35 * mask_area:
            return [], empty

        k = _odd(int(0.01 * min(h, w)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        dets: List[Dict[str, Any]] = []
        kept = np.zeros((h, w), dtype=np.uint8)
        # Printed text / artwork is far busier than the surrounding surface texture.
        edge_limit = max(0.15, 1.5 * float(np.count_nonzero(edges[inside])) / max(mask_area, 1.0))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            area_frac = area / mask_area
            if area_frac < 0.003 or (ref_colour is None and area_frac > 0.35):
                continue
            comp = labels[y:y + bh, x:x + bw] == i
            edge_density = float(np.count_nonzero(edges[y:y + bh, x:x + bw][comp])) / max(area, 1)
            if edge_density > edge_limit:
                continue
            de = delta_e[y:y + bh, x:x + bw][comp]
            mean_de = float(de.mean())
            kept[y:y + bh, x:x + bw][comp] = 255
            dets.append({
                "defect_type": "DISCOLOURATION",
                "bbox": [float(x), float(y), float(x + bw), float(y + bh)],
                "confidence": min(0.95, 0.4 + mean_de / 60.0 + min(0.2, area_frac * 4)),
                "detector": "OPENCV",
                "metrics": {
                    "method": "cielab_colour_deviation",
                    "reference": reference_kind,
                    "mean_delta_e": round(mean_de, 2),
                    "max_delta_e": round(float(de.max()), 2),
                    "surface_area_ratio": round(area_frac, 4),
                },
            })
        return dets, kept

    def _detect_dents(
        self, gray: np.ndarray, mask: np.ndarray, edges: np.ndarray, colour_mask: np.ndarray
    ) -> List[Dict[str, Any]]:
        h, w = gray.shape
        g = gray.astype(np.float32)
        background = _masked_blur(g, mask, max(15.0, min(h, w) / 8.0))
        local = _masked_blur(g, mask, max(2.0, min(h, w) / 120.0))
        shade = local - background

        inside = mask > 0
        vals = shade[inside][::7]
        robust_std = 1.4826 * float(np.median(np.abs(vals - np.median(vals))))
        thr = max(14.0, 3.5 * robust_std)
        binary = ((np.abs(shade) > thr) & inside & (colour_mask == 0)).astype(np.uint8) * 255

        # A dent under directional light has a dark and a bright lobe; close them into one region.
        k = _odd(int(0.03 * min(h, w)))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))

        mask_area = float(np.count_nonzero(inside))
        edge_limit = max(0.12, 1.5 * float(np.count_nonzero(edges[inside])) / max(mask_area, 1.0))
        dets: List[Dict[str, Any]] = []
        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            area_frac = area / mask_area
            if area_frac < 0.002 or area_frac > 0.2:
                continue
            if max(bw, bh) / max(1, min(bw, bh)) > 4.0:
                continue
            comp = labels[y:y + bh, x:x + bw] == i
            edge_density = float(np.count_nonzero(edges[y:y + bh, x:x + bw][comp])) / max(area, 1)
            if edge_density > edge_limit:
                continue
            depth = float(np.abs(shade[y:y + bh, x:x + bw][comp]).max())
            dets.append({
                "defect_type": "DENT",
                "bbox": [float(x), float(y), float(x + bw), float(y + bh)],
                "confidence": min(0.93, 0.4 + 0.25 * min(1.0, depth / thr - 1.0) + min(0.2, area_frac * 5)),
                "detector": "OPENCV",
                "metrics": {
                    "method": "shading_anomaly",
                    "shading_depth": round(depth, 1),
                    "threshold": round(thr, 1),
                    "surface_area_ratio": round(area_frac, 4),
                },
            })
        return self._merge_dent_lobes(dets)

    @staticmethod
    def _merge_dent_lobes(dets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Under directional light one dent shows a dark and a bright lobe side by side; report it once."""
        merged = True
        while merged and len(dets) > 1:
            merged = False
            for i in range(len(dets)):
                for j in range(i + 1, len(dets)):
                    a, b = dets[i]["bbox"], dets[j]["bbox"]
                    gap = 0.5 * max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1])
                    if a[0] - gap < b[2] and b[0] - gap < a[2] and a[1] - gap < b[3] and b[1] - gap < a[3]:
                        ma, mb = dets[i]["metrics"], dets[j]["metrics"]
                        dets[i] = {
                            **dets[i],
                            "bbox": [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])],
                            "confidence": max(dets[i]["confidence"], dets[j]["confidence"]),
                            "metrics": {
                                **ma,
                                "shading_depth": max(ma["shading_depth"], mb["shading_depth"]),
                                "surface_area_ratio": round(ma["surface_area_ratio"] + mb["surface_area_ratio"], 4),
                            },
                        }
                        del dets[j]
                        merged = True
                        break
                if merged:
                    break
        return dets

    def _detect_dimensional(
        self, img: np.ndarray, contour: Optional[np.ndarray], mask_used: bool, ref: Optional[np.ndarray]
    ) -> List[Dict[str, Any]]:
        if contour is None or not mask_used:
            return []
        h, w = img.shape[:2]
        area = cv2.contourArea(contour)
        (_, _), (rw, rh), _ = cv2.minAreaRect(contour)
        aspect = max(rw, rh) / max(1.0, min(rw, rh))
        bx, by, bw, bh = cv2.boundingRect(contour)
        dets: List[Dict[str, Any]] = []

        if ref is not None:
            _, ref_used, ref_contour = self._segment_product(ref)
            if ref_used and ref_contour is not None:
                ref_area = cv2.contourArea(ref_contour)
                (_, _), (rrw, rrh), _ = cv2.minAreaRect(ref_contour)
                ref_aspect = max(rrw, rrh) / max(1.0, min(rrw, rrh))
                aspect_dev = abs(aspect - ref_aspect) / ref_aspect
                area_dev = abs(area - ref_area) / max(ref_area, 1.0)
                shape_dist = float(cv2.matchShapes(contour, ref_contour, cv2.CONTOURS_MATCH_I1, 0.0))
                worst = max(aspect_dev, area_dev, shape_dist)
                if aspect_dev > 0.05 or area_dev > 0.08 or shape_dist > 0.08:
                    dets.append({
                        "defect_type": "DIMENSIONAL_ANOMALY",
                        "bbox": [float(bx), float(by), float(bx + bw), float(by + bh)],
                        "confidence": min(0.95, 0.55 + worst),
                        "detector": "OPENCV",
                        "metrics": {
                            "method": "golden_contour_comparison",
                            "aspect_ratio": round(aspect, 3),
                            "reference_aspect_ratio": round(ref_aspect, 3),
                            "aspect_deviation": round(aspect_dev, 4),
                            "area_deviation": round(area_dev, 4),
                            "shape_distance": round(shape_dist, 4),
                        },
                    })

        # Local notches / chipped edges on an otherwise convex part.
        hull_pts = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull_pts)
        solidity = area / hull_area if hull_area > 0 else 0.0
        if solidity < 0.9:
            return dets
        approx = cv2.approxPolyDP(contour, 0.002 * cv2.arcLength(contour, True), True)
        if len(approx) < 4:
            return dets
        try:
            hull_idx = cv2.convexHull(approx, returnPoints=False)
            defects = cv2.convexityDefects(approx, hull_idx)
        except cv2.error:
            return dets
        if defects is None:
            return dets

        size = max(rw, rh)
        for s, e, f, d in defects[:, 0]:
            depth = d / 256.0
            if depth < 0.04 * size:
                continue
            pts = approx[[s, e, f], 0]
            pad = depth * 0.5
            x1, y1 = pts.min(axis=0) - pad
            x2, y2 = pts.max(axis=0) + pad
            depth_ratio = depth / size
            dets.append({
                "defect_type": "DIMENSIONAL_ANOMALY",
                "bbox": [float(max(0, x1)), float(max(0, y1)), float(min(w, x2)), float(min(h, y2))],
                "confidence": min(0.9, 0.5 + depth_ratio * 3),
                "detector": "OPENCV",
                "metrics": {
                    "method": "contour_convexity_defect",
                    "notch_depth_px": round(depth, 1),
                    "notch_depth_ratio": round(depth_ratio, 4),
                    "solidity": round(solidity, 4),
                },
            })
        return dets

    # ------------------------------------------------------------------ ONNX (YOLOv8 export)
    def _detect_onnx(self, img: np.ndarray) -> List[Dict[str, Any]]:
        size = self._input_size
        h, w = img.shape[:2]
        r = size / float(max(h, w))
        resized = cv2.resize(img, (int(round(w * r)), int(round(h * r))), interpolation=cv2.INTER_AREA)
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized

        blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (size, size), swapRB=True, crop=False)
        with self._net_lock:
            self._net.setInput(blob)
            out = np.squeeze(self._net.forward())
        if out.ndim != 2:
            return []
        if out.shape[0] < out.shape[1]:
            out = out.T  # YOLOv8 emits (4 + classes, N)

        boxes, scores = out[:, :4], out[:, 4:]
        if self._classes and scores.shape[1] == len(self._classes) + 1:
            scores = scores[:, 1:] * scores[:, :1]  # YOLOv5 layout with objectness
        class_ids = scores.argmax(axis=1)
        confs = scores.max(axis=1)
        keep = confs >= settings.DEFECT_MODEL_CONF_THRESHOLD
        boxes, class_ids, confs = boxes[keep], class_ids[keep], confs[keep]
        if len(confs) == 0:
            return []

        xywh = []
        for cx, cy, bw, bh in boxes:
            xywh.append([float((cx - bw / 2) / r), float((cy - bh / 2) / r), float(bw / r), float(bh / r)])
        idxs = cv2.dnn.NMSBoxes(xywh, confs.astype(float).tolist(), settings.DEFECT_MODEL_CONF_THRESHOLD, 0.45)

        dets = []
        for i in np.array(idxs).flatten():
            x, y, bw, bh = xywh[i]
            cid = int(class_ids[i])
            name = self._classes[cid] if cid < len(self._classes) else f"class_{cid}"
            dets.append({
                "defect_type": self.canonical_type(name),
                "bbox": [x, y, x + bw, y + bh],
                "confidence": float(confs[i]),
                "detector": "ONNX",
                "metrics": {"method": "yolo_onnx", "model_class": name},
            })
        return dets

    # ------------------------------------------------------------------ post-processing
    @staticmethod
    def _fuse(model_dets: List[Dict[str, Any]], cv_dets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Hybrid merge. A model and an OpenCV detection of the same type on the same region are one
        defect: OpenCV's measurements are kept (they drive severity grading) and the independent
        agreement raises confidence. Everything else from either engine is kept as-is.
        """
        def overlaps(a: List[float], b: List[float]) -> bool:
            if _iou(a, b) >= 0.3:
                return True
            ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
            iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
            smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            return smaller > 0 and ix * iy >= 0.6 * smaller

        fused: List[Dict[str, Any]] = []
        matched_cv = set()
        for m in model_dets:
            match = next(
                (i for i, c in enumerate(cv_dets)
                 if i not in matched_cv and c["defect_type"] == m["defect_type"] and overlaps(m["bbox"], c["bbox"])),
                None,
            )
            if match is None:
                fused.append(m)
                continue
            matched_cv.add(match)
            c = cv_dets[match]
            fused.append({
                **c,
                "confidence": min(0.99, 1.0 - (1.0 - c["confidence"]) * (1.0 - m["confidence"])),
                "detector": "ONNX+OPENCV",
                "metrics": {**c.get("metrics", {}), "model_class": m["metrics"].get("model_class"),
                            "model_confidence": round(m["confidence"], 3)},
            })
        fused.extend(c for i, c in enumerate(cv_dets) if i not in matched_cv)
        return fused

    @staticmethod
    def _nms(dets: List[Dict[str, Any]], iou_thr: float) -> List[Dict[str, Any]]:
        def area(b: List[float]) -> float:
            return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])

        def contained(inner: List[float], outer: List[float]) -> bool:
            ix = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0]))
            iy = max(0.0, min(inner[3], outer[3]) - max(inner[1], outer[1]))
            return ix * iy >= 0.7 * area(inner)

        # Largest first so fragments nested inside an already-kept box of the same type are dropped.
        dets = sorted(dets, key=lambda d: (area(d["bbox"]) * d["confidence"]), reverse=True)
        kept: List[Dict[str, Any]] = []
        for d in dets:
            same = [k for k in kept if k["defect_type"] == d["defect_type"]]
            if all(_iou(k["bbox"], d["bbox"]) < iou_thr and not contained(d["bbox"], k["bbox"]) for k in same):
                kept.append(d)
        return kept

    def _finalize(self, det: Dict[str, Any], w: int, h: int) -> Optional[Dict[str, Any]]:
        x1, y1, x2, y2 = det["bbox"]
        x1, x2 = max(0.0, min(float(w), x1)), max(0.0, min(float(w), x2))
        y1, y2 = max(0.0, min(float(h), y1)), max(0.0, min(float(h), y2))
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None
        det["bbox"] = [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]
        det["area_ratio"] = round(((x2 - x1) * (y2 - y1)) / float(w * h), 5)
        det["confidence"] = round(float(det["confidence"]), 3)
        metrics = det.setdefault("metrics", {})
        metrics["bbox_norm"] = [round(x1 / w, 4), round(y1 / h, 4), round(x2 / w, 4), round(y2 / h, 4)]
        det["severity"] = grade_severity(det)
        det.setdefault("reviewer_status", "PENDING")
        return det


def grade_severity(det: Dict[str, Any]) -> str:
    dtype = det["defect_type"]
    m = det.get("metrics", {})
    area = det.get("area_ratio", 0.0)
    if dtype == "CRACK":
        return "CRITICAL" if m.get("length_ratio", 0.0) >= 0.15 or area >= 0.05 else "HIGH"
    if dtype == "SCRATCH":
        lr = m.get("length_ratio", math.sqrt(area))
        return "HIGH" if lr >= 0.25 else ("MEDIUM" if lr >= 0.1 else "LOW")
    if dtype == "DENT":
        sa = m.get("surface_area_ratio", area)
        return "HIGH" if sa >= 0.04 or m.get("shading_depth", 0) >= 45 else ("MEDIUM" if sa >= 0.01 else "LOW")
    if dtype == "DISCOLOURATION":
        sa = m.get("surface_area_ratio", area)
        de = m.get("mean_delta_e", 0.0)
        return "HIGH" if de >= 30 or sa >= 0.1 else ("MEDIUM" if de >= 20 or sa >= 0.03 else "LOW")
    if dtype == "DIMENSIONAL_ANOMALY":
        worst = max(m.get("aspect_deviation", 0.0), m.get("area_deviation", 0.0), m.get("notch_depth_ratio", 0.0))
        return "CRITICAL" if worst >= 0.15 else "HIGH"
    # Unmapped model classes
    return "HIGH" if det.get("confidence", 0) >= 0.7 else "MEDIUM"


def compute_outcome(detections: List[Dict[str, Any]], quality_issue: bool = False) -> str:
    """PASS / REVIEW / DEFECTIVE from detections, ignoring ones an inspector rejected."""
    active = [d for d in detections if d.get("reviewer_status") != "REJECTED"]
    for d in active:
        confirmed = d.get("reviewer_status") in ("CONFIRMED", "RELABELED")
        if d.get("severity") in ("CRITICAL", "HIGH") and (confirmed or d.get("confidence", 0) >= 0.5):
            return "DEFECTIVE"
    if any(d.get("severity") in ("MEDIUM", "HIGH", "CRITICAL") for d in active) or quality_issue:
        return "REVIEW"
    return "PASS"


def synthesize_surface_sample(
    defects: List[str],
    size: Tuple[int, int] = (720, 960),
    seed: int = 7,
    product_on_background: bool = False,
    notch: bool = False,
) -> np.ndarray:
    """Renders a brushed-metal surface with controllable synthetic defects (demo seeding and tests)."""
    rng = np.random.default_rng(seed)
    h, w = size
    noise = cv2.GaussianBlur(rng.normal(0, 6, (h, w)).astype(np.float32), (0, 0), sigmaX=6, sigmaY=0.8)
    gradient = np.linspace(-8, 8, w, dtype=np.float32)[None, :]
    surface = 160.0 + noise + gradient

    if "DENT" in defects:
        cy, cx, sigma = int(h * 0.7), int(w * 0.3), 0.045 * w
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        g = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))
        surface += 45.0 * ((xx - cx) / sigma) * g - 25.0 * g

    img = cv2.merge([surface, surface + 3, surface + 6])
    img = np.clip(img, 0, 255).astype(np.uint8)

    if "SCRATCH" in defects:
        cv2.line(img, (int(w * 0.12), int(h * 0.18)), (int(w * 0.55), int(h * 0.3)), (228, 230, 233), 2, cv2.LINE_AA)
    if "CRACK" in defects:
        x, y = float(w * 0.62), float(h * 0.45)
        pts = [(int(x), int(y))]
        for _ in range(28):
            x += rng.uniform(4, 12)
            y += rng.uniform(-9, 15)
            pts.append((int(x), int(y)))
        cv2.polylines(img, [np.array(pts, dtype=np.int32)], False, (55, 55, 58), 2, cv2.LINE_AA)
    if "DISCOLOURATION" in defects:
        patch = np.zeros((h, w), dtype=np.float32)
        cv2.ellipse(patch, (int(w * 0.8), int(h * 0.25)), (int(w * 0.07), int(h * 0.08)), 20, 0, 360, 1.0, -1)
        patch = cv2.GaussianBlur(patch, (0, 0), 6)[..., None] * 0.6
        rust = np.array([45, 95, 160], dtype=np.float32)
        img = (img.astype(np.float32) * (1 - patch) + rust * patch).astype(np.uint8)

    if product_on_background:
        canvas = np.full((h, w, 3), (38, 34, 30), dtype=np.uint8)
        part = np.zeros((h, w), dtype=np.uint8)
        cv2.rectangle(part, (int(w * 0.15), int(h * 0.15)), (int(w * 0.85), int(h * 0.85)), 255, -1)
        if notch:
            cv2.circle(part, (int(w * 0.85), int(h * 0.5)), int(h * 0.09), 0, -1)
        canvas[part > 0] = img[part > 0]
        img = canvas
    return img


defect_detector = DefectDetector()
