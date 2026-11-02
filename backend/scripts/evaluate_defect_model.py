"""
Accuracy benchmark for the Defect Inspection detectors (ONNX model, OpenCV, hybrid).

Usage (from the backend folder):
    python -m scripts.evaluate_defect_model                       # labelled synthetic benchmark
    python -m scripts.evaluate_defect_model --dataset path/to/val # YOLO-format images/ + labels/

A YOLO dataset folder must contain `images/` and `labels/` (one `<image>.txt` per image with
`class cx cy w h` normalised rows). Class indices follow DEFECT_MODEL_CLASSES / the .names file.
"""
import argparse
import json
import os

import numpy as np

from app.core.config import settings
from app.services.defect_detection_service import DefectDetector
from app.services.learning.evaluation import evaluate, load_yolo, synth_labelled


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
    engines = [
        ("onnx", DefectDetector(model_path=model_path, model_classes=class_spec, backend="onnx", conf_threshold=0.01)),
        ("opencv", DefectDetector(model_path="", backend="opencv")),
        ("hybrid", DefectDetector(model_path=model_path, model_classes=class_spec, backend="hybrid", conf_threshold=0.01)),
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
