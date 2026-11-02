#!/usr/bin/env python3
"""Trains a YOLO segmentation candidate and exports it to ONNX. Model selection uses `val` only.

    ml/.venv/bin/python ml/train_yolo_seg.py --model yolo11n-seg.pt --epochs 80 --imgsz 640 --name yolo11n_seg

Uses Apple MPS when available. Ultralytics is AGPL-3.0: see docs/MODELS.md.
"""
import argparse
import os
import shutil

import torch
from ultralytics import YOLO


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="datasets/prepared/yolo/data.yaml")
    ap.add_argument("--model", default="yolo11n-seg.pt")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--patience", type=int, default=20)
    ap.add_argument("--name", default="yolo_seg")
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    model = YOLO(args.model)
    model.train(
        data=os.path.abspath(args.data), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch, device=args.device,
        patience=args.patience, project=os.path.abspath("ml/runs"), name=args.name, exist_ok=True, seed=2026,
        deterministic=False, workers=args.workers, cos_lr=True, close_mosaic=10,
        # Defects are orientation-agnostic. Colour stays nearly fixed because colour IS a defect class here.
        fliplr=0.5, flipud=0.5, degrees=10, translate=0.08, scale=0.3, hsv_h=0.0, hsv_s=0.1, hsv_v=0.2, mosaic=0.6,
        plots=True, verbose=True,
    )
    best = os.path.abspath(f"ml/runs/{args.name}/weights/best.pt")
    exported = YOLO(best).export(format="onnx", imgsz=args.imgsz, nms=False, simplify=True, opset=17)
    target = os.path.abspath(f"ml/runs/{args.name}/{args.name}.onnx")
    shutil.copyfile(exported, target)
    print("EXPORTED", target, os.path.getsize(target) // 1024, "KiB")


if __name__ == "__main__":
    main()
