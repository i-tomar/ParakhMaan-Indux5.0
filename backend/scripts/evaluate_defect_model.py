"""
Accuracy benchmark for the Defect Inspection detectors (ONNX model, OpenCV, hybrid).

Usage (from the backend folder):
    python -m scripts.evaluate_defect_model                       # labelled synthetic benchmark
    python -m scripts.evaluate_defect_model --dataset path/to/val # YOLO-format images/ + labels/

A YOLO dataset folder must contain `images/` and `labels/` (one `<image>.txt` per image with
`class cx cy w h` normalised rows). Class indices follow DEFECT_MODEL_CLASSES / the .names file.
"""
import argparse
import glob
import json
import math
import os
import time
from collections import defaultdict
from typing import Dict, List, Tuple

import cv2
import numpy as np

from app.core.config import settings
from app.services.defect_detection_service import DefectDetector, _iou

CLASSES = ["SCRATCH", "CRACK", "DENT", "DISCOLOURATION"]
Box = List[float]


# ---------------------------------------------------------------- synthetic benchmark
def _surface(rng: np.random.Generator, h: int, w: int) -> np.ndarray:
    base = rng.uniform(120, 190)
    noise_sigma = rng.uniform(3, 10)
    noise = cv2.GaussianBlur(rng.normal(0, noise_sigma, (h, w)).astype(np.float32), (0, 0),
                             sigmaX=rng.uniform(3, 8), sigmaY=rng.uniform(0.6, 1.5))
    angle = rng.uniform(0, 2 * math.pi)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    gradient = (np.cos(angle) * (xx / w - 0.5) + np.sin(angle) * (yy / h - 0.5)) * rng.uniform(5, 30)
    surface = base + noise + gradient
    grain = rng.normal(0, rng.uniform(0, 6), (h, w)).astype(np.float32)
    tint = rng.uniform(-4, 6, 3)
    img = np.stack([surface + grain + tint[0], surface + grain + tint[1], surface + grain + tint[2]], axis=-1)
    return img


def _free_spot(rng, h, w, size, taken: List[Box]) -> Tuple[int, int]:
    for _ in range(50):
        cx, cy = int(rng.uniform(size, w - size)), int(rng.uniform(size, h - size))
        box = [cx - size, cy - size, cx + size, cy + size]
        if all(_iou(box, t) == 0 for t in taken):
            return cx, cy
    return int(rng.uniform(size, w - size)), int(rng.uniform(size, h - size))


def synth_labelled(rng: np.random.Generator, h: int = 720, w: int = 960) -> Tuple[np.ndarray, List[Tuple[str, Box]]]:
    img = _surface(rng, h, w)
    gts: List[Tuple[str, Box]] = []
    n_defects = int(rng.choice([0, 1, 1, 2, 2, 3]))
    kinds = list(rng.choice(CLASSES, size=n_defects, replace=True))

    # Shading defects modify the float surface before 8-bit conversion
    for kind in [k for k in kinds if k == "DENT"]:
        sigma = rng.uniform(0.03, 0.06) * w
        cx, cy = _free_spot(rng, h, w, int(2.5 * sigma), [b for _, b in gts])
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        g = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))
        a = rng.uniform(0, 2 * math.pi)
        directional = ((xx - cx) * math.cos(a) + (yy - cy) * math.sin(a)) / sigma
        img += (rng.uniform(30, 50) * directional * g - rng.uniform(10, 30) * g)[..., None]
        r = 2.2 * sigma
        gts.append(("DENT", [cx - r, cy - r, cx + r, cy + r]))

    img = np.clip(img, 0, 255).astype(np.uint8)

    for kind in kinds:
        taken = [b for _, b in gts]
        if kind == "SCRATCH":
            length = rng.uniform(0.15, 0.4) * math.hypot(w, h)
            cx, cy = _free_spot(rng, h, w, int(length / 2), taken)
            a = rng.uniform(0, math.pi)
            p1 = (int(cx - math.cos(a) * length / 2), int(cy - math.sin(a) * length / 2))
            p2 = (int(cx + math.cos(a) * length / 2), int(cy + math.sin(a) * length / 2))
            bright = rng.random() < 0.6
            colour = tuple(int(v) for v in (rng.uniform(215, 245),) * 3) if bright else tuple(int(v) for v in (rng.uniform(50, 90),) * 3)
            cv2.line(img, p1, p2, colour, int(rng.integers(1, 4)), cv2.LINE_AA)
            xs, ys = sorted([p1[0], p2[0]]), sorted([p1[1], p2[1]])
            gts.append(("SCRATCH", [xs[0] - 3, ys[0] - 3, xs[1] + 3, ys[1] + 3]))
        elif kind == "CRACK":
            cx, cy = _free_spot(rng, h, w, 120, taken)
            x, y = float(cx - 100), float(cy)
            heading = rng.uniform(-0.6, 0.6)
            pts = [(int(x), int(y))]
            for _ in range(int(rng.integers(18, 32))):
                heading += rng.uniform(-0.5, 0.5)
                step = rng.uniform(5, 12)
                x += math.cos(heading) * step
                y += math.sin(heading) * step + rng.uniform(-4, 4)
                pts.append((int(x), int(y)))
            arr = np.array(pts, dtype=np.int32)
            shade = int(rng.uniform(30, 70))
            cv2.polylines(img, [arr], False, (shade, shade, shade + 3), int(rng.integers(1, 3)), cv2.LINE_AA)
            x1, y1 = arr.min(axis=0)
            x2, y2 = arr.max(axis=0)
            gts.append(("CRACK", [x1 - 3, y1 - 3, x2 + 3, y2 + 3]))
        elif kind == "DISCOLOURATION":
            ax, ay = int(rng.uniform(0.04, 0.1) * w), int(rng.uniform(0.04, 0.1) * h)
            cx, cy = _free_spot(rng, h, w, max(ax, ay), taken)
            patch = np.zeros((h, w), np.float32)
            cv2.ellipse(patch, (cx, cy), (ax, ay), float(rng.uniform(0, 180)), 0, 360, 1.0, -1)
            patch = cv2.GaussianBlur(patch, (0, 0), 5)[..., None] * rng.uniform(0.4, 0.7)
            colour = np.array([[45, 95, 160], [40, 70, 110], [150, 120, 60], [60, 140, 150]][int(rng.integers(0, 4))], np.float32)
            img = (img.astype(np.float32) * (1 - patch) + colour * patch).astype(np.uint8)
            gts.append(("DISCOLOURATION", [cx - ax, cy - ay, cx + ax, cy + ay]))
    return img, gts


# ---------------------------------------------------------------- YOLO dataset loader
def load_yolo(folder: str, class_names: List[str]):
    images = sorted(glob.glob(os.path.join(folder, "images", "*")))
    for path in images:
        img = cv2.imread(path)
        if img is None:
            continue
        h, w = img.shape[:2]
        label = os.path.join(folder, "labels", os.path.splitext(os.path.basename(path))[0] + ".txt")
        gts = []
        if os.path.exists(label):
            for row in open(label, encoding="utf-8").read().split("\n"):
                parts = row.split()
                if len(parts) < 5:
                    continue
                c, cx, cy, bw, bh = int(parts[0]), *map(float, parts[1:5])
                name = DefectDetector.canonical_type(class_names[c]) if c < len(class_names) else f"CLASS_{c}"
                gts.append((name, [(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h]))
        yield os.path.basename(path), img, gts


# ---------------------------------------------------------------- metrics
def average_precision(scored: List[Tuple[float, bool]], n_gt: int) -> float:
    if n_gt == 0 or not scored:
        return 0.0
    scored = sorted(scored, key=lambda s: -s[0])
    tp = np.cumsum([1 if t else 0 for _, t in scored])
    fp = np.cumsum([0 if t else 1 for _, t in scored])
    recall = tp / n_gt
    precision = tp / np.maximum(tp + fp, 1)
    # All-point interpolation (VOC2010+/COCO-style envelope)
    mrec = np.concatenate([[0.0], recall, [1.0]])
    mpre = np.concatenate([[1.0], precision, [0.0]])
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    return float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))


def match(preds: List[dict], gts: List[Tuple[str, Box]], iou_thr: float) -> List[Tuple[str, float, bool]]:
    """Greedy, confidence-ordered, class-aware matching. Returns (class, confidence, is_tp)."""
    used = set()
    out = []
    for p in sorted(preds, key=lambda d: -d["confidence"]):
        best, best_iou = None, iou_thr
        for i, (cls, box) in enumerate(gts):
            if i in used or cls != p["defect_type"]:
                continue
            iou = _iou(p["bbox"], box)
            if iou >= best_iou:
                best, best_iou = i, iou
        if best is not None:
            used.add(best)
        out.append((p["defect_type"], p["confidence"], best is not None))
    return out


def evaluate(engine_name: str, detector: DefectDetector, samples, iou_thr: float, op_conf: float) -> dict:
    scored: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
    n_gt: Dict[str, int] = defaultdict(int)
    latencies = []
    img_tp = img_fp = img_tn = img_fn = 0
    for _, img, gts in samples:
        for cls, _ in gts:
            n_gt[cls] += 1
        t = time.perf_counter()
        res = detector.detect(img)
        latencies.append((time.perf_counter() - t) * 1000)
        preds = res["detections"]
        for cls, conf, tp in match(preds, gts, iou_thr):
            scored[cls].append((conf, tp))
        flagged = any(p["confidence"] >= op_conf for p in preds)
        if gts and flagged:
            img_tp += 1
        elif gts:
            img_fn += 1
        elif flagged:
            img_fp += 1
        else:
            img_tn += 1

    per_class = {}
    for cls in CLASSES:
        s = scored.get(cls, [])
        tp = sum(1 for c, t in s if t and c >= op_conf)
        fp = sum(1 for c, t in s if not t and c >= op_conf)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / n_gt[cls] if n_gt[cls] else 0.0
        per_class[cls] = {
            "gt": n_gt[cls], "tp": tp, "fp": fp, "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "ap50": round(average_precision(s, n_gt[cls]), 3),
        }
    present = [c for c in CLASSES if n_gt[c]]
    total_tp = sum(per_class[c]["tp"] for c in present)
    total_fp = sum(per_class[c]["fp"] for c in present)
    total_gt = sum(n_gt[c] for c in present)
    n_img = img_tp + img_fp + img_tn + img_fn
    return {
        "engine": engine_name,
        "map50": round(float(np.mean([per_class[c]["ap50"] for c in present])), 3) if present else 0.0,
        "precision": round(total_tp / (total_tp + total_fp), 3) if total_tp + total_fp else 0.0,
        "recall": round(total_tp / total_gt, 3) if total_gt else 0.0,
        "image_accuracy": round((img_tp + img_tn) / n_img, 3) if n_img else 0.0,
        "image_counts": {"tp": img_tp, "fp": img_fp, "tn": img_tn, "fn": img_fn},
        "avg_latency_ms": round(float(np.mean(latencies)), 1),
        "per_class": per_class,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", help="YOLO-format folder with images/ and labels/")
    ap.add_argument("--n", type=int, default=200, help="synthetic images (when no --dataset)")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--conf", type=float, default=settings.DEFECT_MODEL_CONF_THRESHOLD, help="operating threshold for P/R")
    ap.add_argument("--out", default=os.path.join(settings.REPORTS_DIR, "defect_model_evaluation.json"))
    args = ap.parse_args()

    model_path = settings.DEFECT_MODEL_PATH
    class_spec = settings.DEFECT_MODEL_CLASSES
    class_names = [c.strip() for c in class_spec.split(",") if c.strip()] or ["scratch", "crack", "dent", "discolouration"]

    if args.dataset:
        samples = list(load_yolo(args.dataset, class_names))
        source = f"YOLO dataset: {args.dataset}"
    else:
        rng = np.random.default_rng(args.seed)
        samples = [(f"synthetic_{i:04d}", *synth_labelled(rng)) for i in range(args.n)]
        source = f"synthetic benchmark: {args.n} images, seed {args.seed}"
    print(f"{source} | {sum(len(g) for _, _, g in samples)} ground-truth defects | IoU {args.iou} | operating conf {args.conf}")

    # Low model threshold so AP covers the whole precision-recall curve (standard mAP practice).
    settings.DEFECT_MODEL_CONF_THRESHOLD = 0.01
    engines = [
        ("onnx", DefectDetector(model_path=model_path, model_classes=class_spec, backend="onnx")),
        ("opencv", DefectDetector(model_path="", backend="opencv")),
        ("hybrid", DefectDetector(model_path=model_path, model_classes=class_spec, backend="hybrid")),
    ]
    results = []
    for name, det in engines:
        if name != "opencv" and not det.status()["model_loaded"]:
            print(f"skip {name}: model not loaded ({det.status()['model_error']})")
            continue
        det.detect(samples[0][1])  # warm-up
        results.append(evaluate(name, det, samples, args.iou, args.conf))

    print(f"\n{'engine':8} {'mAP50':>6} {'P':>6} {'R':>6} {'img-acc':>8} {'ms':>7}")
    for r in results:
        print(f"{r['engine']:8} {r['map50']:6.3f} {r['precision']:6.3f} {r['recall']:6.3f} {r['image_accuracy']:8.3f} {r['avg_latency_ms']:7.1f}")
    for r in results:
        print(f"\n[{r['engine']}] per class (P / R / F1 / AP50, gt):  image confusion {r['image_counts']}")
        for cls, m in r["per_class"].items():
            print(f"  {cls:15} {m['precision']:.3f} / {m['recall']:.3f} / {m['f1']:.3f} / {m['ap50']:.3f}   gt={m['gt']} tp={m['tp']} fp={m['fp']}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"source": source, "iou": args.iou, "operating_conf": args.conf, "results": results}, f, indent=2)
    print(f"\nSaved {args.out}")


if __name__ == "__main__":
    main()
