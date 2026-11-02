#!/usr/bin/env python3
"""One-time scoring of a trained model on the held-out `test` split.

Reports Ultralytics box and mask metrics, per-class P/R/F1/AP, then image-level miss and
false-reject rates using the exported ONNX path the backend actually runs. All data is real.

    ml/.venv/bin/python ml/evaluate_supervised.py --weights ml/runs/NAME/weights/best.pt \
        --onnx ml/runs/NAME/NAME.onnx --out backend/storage/reports/eval_segmentation.json
"""
import argparse
import json
import os
import sys
import time
from collections import Counter

import cv2
import numpy as np
import torch
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend", "app", "services", "inference"))
from seg_detector import SegDetector  # noqa: E402


def image_level(detector: SegDetector, folder: str, label_folder: str, conf: float):
    tp = fp = fn = tn = 0
    latency = []
    errors = Counter()
    per_size = {"small (<0.5% area)": [0, 0], "medium": [0, 0], "large (>5% area)": [0, 0]}
    for name in sorted(os.listdir(folder)):
        image = cv2.imread(os.path.join(folder, name))
        if image is None:
            continue
        label = os.path.join(label_folder, os.path.splitext(name)[0] + ".txt")
        rows = [r.split() for r in open(label).read().splitlines() if r.strip()] if os.path.exists(label) else []
        t = time.perf_counter()
        preds = detector.detect(image, conf=conf)
        latency.append((time.perf_counter() - t) * 1000)
        defective, flagged = bool(rows), bool(preds)
        tp += defective and flagged
        fn += defective and not flagged
        fp += (not defective) and flagged
        tn += (not defective) and not flagged
        if defective and not flagged:
            errors[name.split("__")[0] + "/" + name.split("__")[1]] += 1
        if defective:
            area = 0.0
            for r in rows:
                pts = np.array(r[1:], dtype=np.float32).reshape(-1, 2)
                area += 0.5 * abs(np.dot(pts[:, 0], np.roll(pts[:, 1], 1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], 1)))
            key = "small (<0.5% area)" if area < 0.005 else ("large (>5% area)" if area > 0.05 else "medium")
            per_size[key][0] += 1
            per_size[key][1] += flagged
    return {
        "confidence": conf, "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
        "precision": round(tp / max(1, tp + fp), 4), "recall": round(tp / max(1, tp + fn), 4),
        "f1": round(2 * tp / max(1, 2 * tp + fp + fn), 4), "miss_rate": round(fn / max(1, tp + fn), 4),
        "false_reject_rate": round(fp / max(1, fp + tn), 4),
        "recall_by_defect_size": {k: {"images": v[0], "recall": round(v[1] / max(1, v[0]), 4)} for k, v in per_size.items()},
        "most_missed": errors.most_common(10),
    }, latency


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--data", default="datasets/prepared/yolo/data.yaml")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default=None)
    args = ap.parse_args()

    model = YOLO(args.weights)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    m = model.val(data=os.path.abspath(args.data), split="test", imgsz=model.ckpt.get("train_args", {}).get("imgsz", 640),
                  conf=0.001, device=device, plots=False, verbose=False)
    names = model.names
    per_class = []
    for row, idx in enumerate(m.seg.ap_class_index):
        p, r = float(m.box.p[row]), float(m.box.r[row])
        per_class.append({"name": names[int(idx)], "instances": int(m.nt_per_class[int(idx)]) if hasattr(m, "nt_per_class") else None,
                          "precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / max(1e-9, p + r), 4),
                          "ap50": round(float(m.box.ap50[row]), 4), "ap50_95": round(float(m.box.ap[row]), 4),
                          "mask_ap50": round(float(m.seg.ap50[row]), 4), "mask_ap50_95": round(float(m.seg.ap[row]), 4)})
    root = os.path.dirname(os.path.abspath(args.data))
    detector = SegDetector(args.onnx, classes=[names[i] for i in sorted(names)])
    level, latency = image_level(detector, os.path.join(root, "images/test"), os.path.join(root, "labels/test"), args.conf)
    report = {
        "data": "real images, MVTec AD held-out test split, labels mapped per ml/datasets/label_map.py",
        "name": args.name or os.path.basename(args.onnx), "split": "test",
        "box": {"map50": round(float(m.box.map50), 4), "map50_95": round(float(m.box.map), 4), "precision": round(float(m.box.mp), 4), "recall": round(float(m.box.mr), 4)},
        "mask": {"map50": round(float(m.seg.map50), 4), "map50_95": round(float(m.seg.map), 4)},
        "per_class": per_class, "image_level": level,
        "onnx_cpu_latency_ms": {"p50": round(float(np.percentile(latency, 50)), 1), "p95": round(float(np.percentile(latency, 95)), 1)},
        "onnx_size_mb": round(os.path.getsize(args.onnx) / 1e6, 2),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
