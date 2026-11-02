"""Memory-bank visual anomaly detection (PatchCore family) without PyTorch at runtime.

A pretrained CNN exported to ONNX turns an image into a grid of patch features. Fitting stores a
compact coreset of patches from GOOD parts only. Scoring measures how far each patch of a new
image lies from that bank, which gives a pixel heatmap and flags defect kinds nobody labelled.

Fitting needs no labels, no GPU and no training framework, so a new product can be onboarded on
the edge device itself (requirement R-32).
"""
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PROJECTION_SEED = 1234


class FeatureExtractor:
    """ONNX backbone: (N, 3, S, S) float image -> (N, D, H, W) patch features."""

    def __init__(self, model_path: str, threads: int = 0):
        import onnxruntime as ort

        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(model_path, options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        shape = self.session.get_inputs()[0].shape
        self.input_size = shape[2] if isinstance(shape[2], int) else 256
        self.providers = self.session.get_providers()
        self.lock = threading.Lock()

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        s = self.input_size
        rgb = cv2.cvtColor(cv2.resize(image, (s, s), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        x = (rgb.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
        return x.transpose(2, 0, 1)

    def __call__(self, images: List[np.ndarray]) -> np.ndarray:
        batch = np.stack([self.preprocess(i) for i in images])
        with self.lock:
            return self.session.run(None, {self.input_name: batch})[0]


def to_patches(features: np.ndarray, projection: Optional[np.ndarray]) -> Tuple[np.ndarray, Tuple[int, int]]:
    n, d, h, w = features.shape
    patches = features.transpose(0, 2, 3, 1).reshape(n * h * w, d)
    if projection is not None:
        patches = patches @ projection
    return patches, (h, w)


def make_projection(in_dim: int, out_dim: int) -> Optional[np.ndarray]:
    if out_dim >= in_dim:
        return None
    rng = np.random.default_rng(PROJECTION_SEED)
    return (rng.standard_normal((in_dim, out_dim)) / np.sqrt(out_dim)).astype(np.float32)


def greedy_coreset(patches: np.ndarray, size: int, seed: int = 0) -> np.ndarray:
    """Greedy k-center selection: the bank keeps the rare patches that random sampling loses."""
    n = len(patches)
    if n <= size:
        return patches
    rng = np.random.default_rng(seed)
    current = int(rng.integers(n))
    distance = np.full(n, np.inf, dtype=np.float32)
    chosen = np.zeros(size, dtype=np.int64)
    for i in range(size):
        chosen[i] = current
        diff = patches - patches[current]
        distance = np.minimum(distance, np.einsum("ij,ij->i", diff, diff))
        current = int(np.argmax(distance))
    return patches[chosen]


def nearest_distance(query: np.ndarray, bank: np.ndarray, chunk: int = 2048) -> np.ndarray:
    """Euclidean distance from each query patch to its nearest bank patch."""
    bank_sq = np.einsum("ij,ij->i", bank, bank)
    out = np.empty(len(query), dtype=np.float32)
    for start in range(0, len(query), chunk):
        q = query[start:start + chunk]
        q_sq = np.einsum("ij,ij->i", q, q)
        d2 = q_sq[:, None] - 2.0 * (q @ bank.T) + bank_sq[None, :]
        out[start:start + chunk] = np.sqrt(np.maximum(d2.min(axis=1), 0.0))
    return out


@dataclass
class ProductModel:
    bank: np.ndarray
    projection: Optional[np.ndarray]
    grid: Tuple[int, int]
    image_threshold: float
    pixel_threshold: float
    prototype: np.ndarray
    meta: Dict[str, Any]

    def save(self, folder: str) -> None:
        os.makedirs(folder, exist_ok=True)
        arrays = {"bank": self.bank, "prototype": self.prototype}
        if self.projection is not None:
            arrays["projection"] = self.projection
        np.savez_compressed(os.path.join(folder, "memory_bank.npz"), **arrays)
        with open(os.path.join(folder, "anomaly_model.json"), "w", encoding="utf-8") as f:
            json.dump({"grid": list(self.grid), "image_threshold": self.image_threshold,
                       "pixel_threshold": self.pixel_threshold, **self.meta}, f, indent=2)

    @classmethod
    def load(cls, folder: str) -> "ProductModel":
        with open(os.path.join(folder, "anomaly_model.json"), encoding="utf-8") as f:
            meta = json.load(f)
        data = np.load(os.path.join(folder, "memory_bank.npz"))
        return cls(
            bank=data["bank"], projection=data["projection"] if "projection" in data else None,
            grid=tuple(meta.pop("grid")), image_threshold=float(meta.pop("image_threshold")),
            pixel_threshold=float(meta.pop("pixel_threshold")), prototype=data["prototype"], meta=meta,
        )


def score_map(extractor: FeatureExtractor, model: ProductModel, image: np.ndarray) -> np.ndarray:
    """Anomaly map at the backbone input resolution."""
    patches, grid = to_patches(extractor([image]), model.projection)
    grid_map = nearest_distance(patches, model.bank).reshape(grid)
    s = extractor.input_size
    upscaled = cv2.resize(grid_map, (s, s), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(upscaled, (0, 0), s / 64.0)


def image_score(amap: np.ndarray) -> float:
    """Mean of the strongest 0.1% of pixels: as local as the maximum, far less noisy."""
    top = max(1, int(amap.size * 0.001))
    return float(np.partition(amap.ravel(), -top)[-top:].mean())


def fit_product(
    extractor: FeatureExtractor,
    images: Iterable[np.ndarray],
    coreset_size: int = 3000,
    projection_dim: int = 192,
    max_patches: int = 60000,
    calibration_fraction: float = 0.2,
    threshold_margin: float = 1.15,
    seed: int = 0,
    progress: Optional[Callable[[str], None]] = None,
) -> ProductModel:
    """Fits on good images. A held-back good fraction sets thresholds, so no defects are needed."""
    images = list(images)
    if len(images) < 5:
        raise ValueError("At least 5 good images are needed to fit an anomaly model")
    started = time.perf_counter()
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(images))
    n_cal = max(1, int(round(len(images) * calibration_fraction)))
    calibration, fit_ids = order[:n_cal], order[n_cal:]

    projection, grid, chunks, globals_ = None, (0, 0), [], []
    per_image = max(32, max_patches // len(fit_ids))
    for idx in fit_ids:
        features = extractor([images[int(idx)]])
        if projection is None:
            projection = make_projection(features.shape[1], projection_dim)
        patches, grid = to_patches(features, projection)
        globals_.append(patches.mean(axis=0))
        chunks.append(patches[rng.choice(len(patches), min(per_image, len(patches)), replace=False)])
    pool = np.concatenate(chunks).astype(np.float32)
    if progress:
        progress(f"selecting coreset from {len(pool)} patches")
    bank = greedy_coreset(pool, coreset_size, seed).astype(np.float32)
    model = ProductModel(bank, projection, grid, 0.0, 0.0, np.mean(globals_, axis=0).astype(np.float32), {})

    maps = [score_map(extractor, model, images[int(i)]) for i in calibration]
    scores = np.array([image_score(m) for m in maps])
    pixels = np.concatenate([m.ravel()[::7] for m in maps])
    model.image_threshold = float(scores.max() * threshold_margin)
    model.pixel_threshold = float(np.quantile(pixels, 0.9995) * threshold_margin)
    model.meta = {
        "fit_images": int(len(fit_ids)), "calibration_images": int(n_cal), "coreset_size": int(len(bank)),
        "projection_dim": int(bank.shape[1]), "seed": seed, "threshold_margin": threshold_margin,
        "threshold_source": "held-back good images only",
        "fit_seconds": round(time.perf_counter() - started, 2),
    }
    return model


def anomaly_regions(amap: np.ndarray, threshold: float, scale_xy: Tuple[float, float], min_area_ratio: float = 0.0002) -> List[Dict[str, Any]]:
    """Connected regions above threshold, as boxes in original-image pixels with binary masks."""
    binary = (amap > threshold).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    regions = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area_ratio * amap.size:
            continue
        peak = float(amap[labels == i].max())
        regions.append({
            "bbox": [x * scale_xy[0], y * scale_xy[1], (x + w) * scale_xy[0], (y + h) * scale_xy[1]],
            "peak": peak, "area_ratio": float(area) / amap.size, "mask": (labels == i),
        })
    return regions
