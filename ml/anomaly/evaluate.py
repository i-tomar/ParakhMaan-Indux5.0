#!/usr/bin/env python3
"""Fits one anomaly model per MVTec category on train/good and scores the shared held-out split.

Thresholds: image F1-optimal threshold is chosen on `val` + `unknown_val` and applied unchanged to
`test` + `unknown_test`. The good-only threshold from fitting is reported too, because that is the
one a newly onboarded product gets. `unknown_*` holds real defect kinds withheld from the
supervised model. Results are real-image metrics.

    ml/.venv/bin/python ml/anomaly/evaluate.py --backbone backend/storage/models/anomaly/resnet18_256.onnx \
        --out backend/storage/reports/eval_anomaly_resnet18.json --save-models backend/storage/models/anomaly/products
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

import cv2
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend", "app", "services", "inference"))
from anomaly_engine import FeatureExtractor, ProductModel, fit_product, image_score, score_map  # noqa: E402


def best_f1_threshold(scores, labels):
    best_t, best_f = float(np.max(scores)) + 1, -1.0
    for t in np.unique(scores):
        pred = scores >= t
        tp = int((pred & labels).sum())
        fp = int((pred & ~labels).sum())
        fn = int((~pred & labels).sum())
        f = 2 * tp / max(1, 2 * tp + fp + fn)
        if f > best_f:
            best_t, best_f = float(t), f
    return best_t


def rates(scores, labels, threshold):
    pred = scores >= threshold
    tp, fp = int((pred & labels).sum()), int((pred & ~labels).sum())
    fn, tn = int((~pred & labels).sum()), int((~pred & ~labels).sum())
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(tp / max(1, tp + fp), 4), "recall": round(tp / max(1, tp + fn), 4),
            "f1": round(2 * tp / max(1, 2 * tp + fp + fn), 4),
            "false_reject_rate": round(fp / max(1, fp + tn), 4), "miss_rate": round(fn / max(1, fn + tp), 4)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default="datasets/prepared/manifest.json")
    ap.add_argument("--backbone", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--coreset", type=int, default=3000)
    ap.add_argument("--projection", type=int, default=192)
    ap.add_argument("--categories", nargs="*")
    ap.add_argument("--max-fit", type=int, default=0, help="limit good images per category (0 = all)")
    ap.add_argument("--save-models")
    args = ap.parse_args()

    with open(args.manifest) as f:
        records = json.load(f)["records"]
    extractor = FeatureExtractor(args.backbone)
    groups = defaultdict(list)
    for r in records:
        groups[r["category"]].append(r)

    results, all_rows = {}, []
    latency_ms = []
    for category in sorted(args.categories or groups):
        rows = groups[category]
        goods = [r["path"] for r in rows if r["split"] == "fit"]
        if args.max_fit:
            goods = goods[:args.max_fit]
        model = fit_product(extractor, [cv2.imread(p) for p in goods], args.coreset, args.projection)
        pixel_true, pixel_score = [], []
        scored = []
        for r in rows:
            if r["split"] == "fit":
                continue
            img = cv2.imread(r["path"])
            t = time.perf_counter()
            amap = score_map(extractor, model, img)
            latency_ms.append((time.perf_counter() - t) * 1000)
            scored.append({**r, "score": image_score(amap)})
            if r["split"] in ("test", "unknown_test"):
                s = amap.shape[0]
                gt = np.zeros((s, s), np.uint8)
                if r.get("mask") and os.path.exists(r["mask"]):
                    gt = cv2.resize(cv2.imread(r["mask"], 0), (s, s), interpolation=cv2.INTER_NEAREST) > 127
                pixel_true.append(np.asarray(gt, bool).ravel()[::3])
                pixel_score.append(amap.ravel()[::3])
        val = [r for r in scored if r["split"] in ("val", "unknown_val")]
        test = [r for r in scored if r["split"] in ("test", "unknown_test")]
        vs = np.array([r["score"] for r in val]); vl = np.array([r["kind"] != "good" for r in val])
        ts = np.array([r["score"] for r in test]); tl = np.array([r["kind"] != "good" for r in test])
        threshold = best_f1_threshold(vs, vl) if vl.any() and (~vl).any() else model.image_threshold
        pt, ps = np.concatenate(pixel_true), np.concatenate(pixel_score)
        results[category] = {
            "fit_images": len(goods), "test_images": len(test), "defective_test": int(tl.sum()),
            "fit_seconds": model.meta["fit_seconds"],
            "image_auroc": round(float(roc_auc_score(tl, ts)), 4) if tl.any() and (~tl).any() else None,
            "image_ap": round(float(average_precision_score(tl, ts)), 4) if tl.any() else None,
            "pixel_auroc": round(float(roc_auc_score(pt, ps)), 4) if pt.any() else None,
            "at_val_threshold": rates(ts, tl, threshold),
            "at_good_only_threshold": rates(ts, tl, model.image_threshold),
        }
        results[category]["val_threshold"] = round(float(threshold), 5)
        results[category]["good_only_threshold"] = round(float(model.image_threshold), 5)
        for r in test:
            r["pred_val"] = r["score"] >= threshold
            r["pred_good_only"] = r["score"] >= model.image_threshold
            all_rows.append(r)
        if args.save_models:
            # Deploy the threshold the reported test metrics were measured at. The pixel threshold is
            # scaled by the same factor so flagged images still produce regions. Test images never
            # influence either value.
            good_only = model.image_threshold
            scale = threshold / max(good_only, 1e-9)
            model.meta.update({"good_only_image_threshold": good_only, "good_only_pixel_threshold": model.pixel_threshold,
                               "threshold_source": "F1-optimal on labelled val split (test untouched)"
                               if threshold != good_only else model.meta.get("threshold_source")})
            model.image_threshold, model.pixel_threshold = float(threshold), float(model.pixel_threshold * scale)
            model.save(os.path.join(args.save_models, category))
        print(category, results[category]["image_auroc"], results[category]["pixel_auroc"], results[category]["at_val_threshold"]["f1"], flush=True)

    unknown = [r for r in all_rows if r["split"] == "unknown_test"]
    known = [r for r in all_rows if r["split"] == "test" and r["kind"] != "good"]
    good = [r for r in all_rows if r["split"] == "test" and r["kind"] == "good"]
    aurocs = [v["image_auroc"] for v in results.values() if v["image_auroc"] is not None]
    pixels = [v["pixel_auroc"] for v in results.values() if v["pixel_auroc"] is not None]
    summary = {
        "data": "real images, MVTec AD held-out split", "backbone": os.path.basename(args.backbone),
        "coreset": args.coreset, "projection_dim": args.projection,
        "categories": len(results), "mean_image_auroc": round(float(np.mean(aurocs)), 4),
        "mean_pixel_auroc": round(float(np.mean(pixels)), 4) if pixels else None,
        "latency_ms_p50": round(float(np.percentile(latency_ms, 50)), 1),
        "latency_ms_p95": round(float(np.percentile(latency_ms, 95)), 1),
        "withheld_unknown_defects": {"images": len(unknown),
                                     "recall_at_val_threshold": round(sum(r["pred_val"] for r in unknown) / max(1, len(unknown)), 4),
                                     "recall_at_good_only_threshold": round(sum(r["pred_good_only"] for r in unknown) / max(1, len(unknown)), 4)},
        "mapped_defects_recall_at_val_threshold": round(sum(r["pred_val"] for r in known) / max(1, len(known)), 4),
        "good_false_reject_rate_at_val_threshold": round(sum(r["pred_val"] for r in good) / max(1, len(good)), 4),
        "per_category": results,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "per_category"}, indent=1))


if __name__ == "__main__":
    main()
