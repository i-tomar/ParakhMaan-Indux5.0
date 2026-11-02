# Models

Every number on this page comes from a JSON report in `backend/storage/reports/`. Each report was produced by a script in this repo, on real MVTec AD images that training never saw. Rerun the script and you get the same report. Nothing here is estimated or copied from a paper.

| Report | Produced by |
|---|---|
| `eval_anomaly.json` (= `eval_anomaly_resnet18.json`), `eval_anomaly_wrn50.json` | `ml/anomaly/evaluate.py` |
| `eval_segmentation.json` | `ml/evaluate_supervised.py` |
| `eval_decision.json` | `backend/scripts/evaluate_decision.py` |
| `benchmark_edge.json`, `benchmark_docker.json` | `backend/scripts/benchmark_edge.py` |
| `e2e_workflows.json`, `e2e_onboarding.json` | `backend/scripts/e2e_workflows.py`, onboarding run |

Dataset, split and label mapping: [DATASETS.md](DATASETS.md).

## Pipeline at a glance

```
image ─┬─▶ YOLO11n-seg (ONNX) ───────────▶ class + mask + confidence ─┐
       ├─▶ ResNet-18 features ─▶ memory bank ─▶ anomaly map ─▶ regions ┼─▶ fusion ─▶ severity ─▶ DecisionPolicy ─▶ ACCEPT / REJECT / MANUAL_REVIEW
       └─▶ classical OpenCV (+ golden reference), corroborated ──────────┘                     ▲
           metrology (calibrated mm, tolerances) ──────────────────────────────────────────────┘
```

The runtime uses **ONNX Runtime only**. The edge image has no PyTorch. Training is in `ml/` and needs PyTorch.

## 1. Anomaly model (any defect, including unseen kinds)

**Method.** PatchCore-style memory bank (Roth et al., 2022), implemented in `backend/app/services/inference/anomaly_engine.py`:

- ImageNet ResNet-18 (torchvision weights), exported to ONNX at 256×256. Layers 2 and 3 are pooled 3×3 and concatenated: 384 channels on a 32×32 grid.
- A fixed random projection reduces this to 192 dimensions. A greedy coreset keeps 3,000 patches per product.
- The score map is the nearest-neighbour distance per patch. The image score is the mean of the top 0.1% of the map.
- **One model per product**, fitted on good images only, in 4–30 s on a laptop CPU (`fit_seconds` in each report).

**Threshold.** It is chosen F1-optimal on the labelled `val` + `unknown_val` split and stored in each product's `anomaly_model.json`. The pixel threshold is scaled by the same factor. The good-only threshold (taken from the 99th–100th percentile of held-back good images, ×1.15) is kept in the same file. It is what a newly onboarded product gets until labelled defects exist. **Test images never touch either threshold.**

**Backbone choice.** Both were evaluated on the same split:

| Backbone | Mean image AUROC | Mean pixel AUROC | Recall, mapped defects | Recall, withheld kinds | False-reject rate | Latency p50 / p95 (CPU, this Mac) |
|---|---|---|---|---|---|---|
| **ResNet-18 (deployed)** | **0.979** | **0.977** | **0.915** | **0.918** (342 images) | **0.094** | **16.8 / 23.1 ms** |
| Wide-ResNet-50-2 | 0.984 | 0.981 | 0.890 | 0.883 | 0.051 | 84.5 / 103.0 ms |

ResNet-18 is deployed because it is five times faster at a 0.005 AUROC cost. Its false-reject rate is higher (9.4% vs 5.1%); a product that needs fewer false rejects can switch to `wrn50_256.onnx`.

**Per product (ResNet-18, test split, val-chosen threshold).**

| product | test imgs | image AUROC | pixel AUROC | F1 | miss rate | false-reject rate | WRN-50 image AUROC |
|---|---|---|---|---|---|---|---|
| bottle | 23 | 1.000 | 0.984 | 0.960 | 0.077 | 0.000 | 1.000 |
| cable | 75 | 0.980 | 0.983 | 0.945 | 0.065 | 0.069 | 0.996 |
| capsule | 45 | 0.992 | 0.994 | 0.867 | 0.235 | 0.000 | 0.995 |
| carpet | 65 | 0.973 | 0.985 | 0.949 | 0.098 | 0.000 | 0.976 |
| grid | 37 | 0.962 | 0.954 | 0.926 | 0.039 | 0.273 | 0.972 |
| hazelnut | 44 | 1.000 | 0.987 | 0.979 | 0.042 | 0.000 | 1.000 |
| leather | 45 | 1.000 | 0.992 | 0.946 | 0.103 | 0.000 | 1.000 |
| metal_nut | 43 | 0.997 | 0.980 | 0.968 | 0.063 | 0.000 | 1.000 |
| pill | 68 | 0.954 | 0.978 | 0.932 | 0.127 | 0.000 | 0.961 |
| screw | 44 | 0.930 | 0.991 | 0.821 | 0.000 | 0.476 | 0.942 |
| tile | 42 | 1.000 | 0.940 | 0.980 | 0.040 | 0.000 | 1.000 |
| toothbrush | 30 | 0.958 | 0.989 | 0.936 | 0.083 | 0.167 | 0.944 |
| transistor | 50 | 0.987 | 0.950 | 0.750 | 0.400 | 0.000 | 1.000 |
| wood | 27 | 1.000 | 0.961 | 1.000 | 0.000 | 0.000 | 1.000 |
| zipper | 102 | 0.947 | 0.986 | 0.966 | 0.000 | 0.375 | 0.976 |

Test sets per product are small (23–102 images; 6–30 good images). A single image moves a rate by several points. **Screw, zipper and grid reject too many good parts. Transistor and capsule miss too many defects.** Treat these as products that need line data before deployment.

## 2. Supervised segmentation (the five named classes)

**Model.** Ultralytics YOLO11n-seg, starting from COCO weights (`yolo11n-seg.pt`), with 2.85 M parameters. It is exported to ONNX (opset 17, `nms=False`, 11.7 MB) and decoded in `backend/app/services/inference/seg_detector.py`.

**Training** (`ml/train_yolo_seg.py`, Apple M1 Pro, MPS):

| setting | value |
|---|---|
| images | 682 train (502 defect images + background goods) / 402 val |
| epochs | 60 (patience 15; ran all 60, best epoch 55) |
| image size, batch | 640, 8 |
| optimiser | Ultralytics `auto`, lr0 0.01, AMP |
| augmentation | Ultralytics defaults, mosaic 0.6, close_mosaic 10 |
| seed | 2026 |
| wall time | about 65 min |

**Results on the held-out test split** (398 images, 228 instances; `ml/evaluate_supervised.py`):

| | box | mask |
|---|---|---|
| mAP@50 | 0.606 | 0.585 |
| mAP@50-95 | 0.373 | 0.314 |
| precision / recall | 0.664 / 0.562 | |

| class | instances | precision | recall | F1 | AP@50 | mask AP@50 |
|---|---|---|---|---|---|---|
| SCRATCH | 53 | 0.759 | 0.772 | 0.765 | 0.796 | 0.743 |
| CRACK | 37 | 0.663 | 0.585 | 0.621 | 0.618 | 0.650 |
| DENT | 21 | 0.602 | 0.476 | 0.532 | 0.551 | 0.586 |
| DISCOLOURATION | 69 | 0.751 | 0.623 | 0.681 | 0.674 | 0.623 |
| DIMENSIONAL_ANOMALY | 48 | 0.547 | 0.354 | 0.430 | 0.392 | 0.321 |

**Image level** (any detection at confidence 0.25 means defective): 139 TP, 1 FP, 25 FN, 233 TN.
- Precision 0.993, recall 0.848, F1 0.915.
- False-reject rate 0.4%, miss rate 15.2%.

**Recall by defect size:**
- small (<0.5% of the image): 0.73;
- medium: 0.88;
- large (>5%): 1.00.

**Agreement check:** the backend's own NumPy decoder reproduces the Ultralytics image-level counts exactly (139 / 1 / 25 / 233).

DIMENSIONAL_ANOMALY is weak because "bent lead", "squeezed teeth" and "manipulated front" are shape changes a small detector cannot see from texture. The calibrated metrology module (§4) is the intended path for real dimensional checks.

## 3. Fusion and decision: what the line actually sees

`engine.inspect()` merges the evidence streams:

- **YOLO_SEG** detections are taken as they are.
- **ANOMALY** regions that overlap no YOLO box (IoU ≤ 0.3) become `UNKNOWN_ANOMALY`.
- **OPENCV** (the original rule-based surface detector, plus the golden reference when one is active) is used only where the anomaly map agrees, if the product has an anomaly model: the box peak must be at least `CLASSICAL_CORROBORATION = 1.2` × the pixel threshold.
  - **Why:** on validation images, the uncorroborated legacy detector with a golden reference falsely flagged 60% of good parts, against 21.4% without it. At 1.2 the golden stream adds no false flags, and also no recall, on MVTec.
  - The cutoff was chosen on `val` only (5 products, 171 images).

`DecisionPolicy` (per product, editable) then sets the outcome:
- HIGH/CRITICAL findings at ≥0.5 confidence → REJECT;
- MEDIUM findings and UNKNOWN_ANOMALY → MANUAL_REVIEW;
- dimensional out-of-tolerance → REJECT;
- poor exposure → MANUAL_REVIEW.

**Decision-level results**: full engine + default policy, test + unknown_test, all 15 products, 740 real images (`eval_decision.json`):

| | count | rate |
|---|---|---|
| Good parts accepted | 212 / 234 | 90.6% |
| Good parts sent to manual review | 22 / 234 | 9.4% |
| **Good parts automatically rejected** | **0 / 234** | **0.0%** |
| Defective parts automatically rejected | 123 / 506 | 24.3% |
| Defective parts sent to manual review | 327 / 506 | 64.6% |
| **Defective parts accepted (escapes)** | **56 / 506** | **11.1%** |
| of which withheld (never-trained) kinds | 36 / 342 | 10.5% |

**How to read this:** the system never automatically rejected a good part. It catches 89% of defective parts, but most of those go to a human rather than being rejected outright. The large review share is deliberate: anomaly-only findings go to review because the model cannot name them. A product owner can change `unknown_anomaly_action` to REJECT once its false-reject rate on line data is acceptable.

The escapes are concentrated in a few products: capsule 16/34, pill 11/55, transistor 8/20. These are not ready for unattended use.

## 4. Dimensional inspection (metrology)

`backend/app/services/metrology/`. This is classical geometry, not a learned model:
- **Calibration:** checkerboard homography, which corrects perspective, or a reference length.
- **Part outline:** found by Otsu thresholding against the background.
- **Measurements:** length and width from the minimum-area rectangle, plus area, perimeter and equivalent diameter.
- **Shape check:** Hausdorff contour deviation from a golden part.

**Verified accuracy:** under 1% error on synthetic images of known size (`test_measurement_error_under_one_percent`; for example 100.0 mm measured for 100 mm). The checkerboard recovers 0.25 mm/px within 0.005 and corrects a perspective warp to within 0.5 mm over 80 mm.

**Not verified:** no real part has been measured against a physical gauge, so every result carries `physical_accuracy_validated: false` and lists its assumptions:
- a flat part, parallel to the calibration plane;
- a fixed camera;
- a contrasting background;
- lens distortion corrected or negligible.

## 5. Speed (measured only where stated)

Full pipeline (YOLO-seg + anomaly + fusion), 200 runs on 43 real metal_nut images, CPU execution provider (`benchmark_edge.py`):

| measured on | p50 | p95 | p99 | sequential FPS | seg p50 | anomaly p50 |
|---|---|---|---|---|---|---|
| macOS, Apple M1 Pro (native) | 69.7 ms | 74.8 ms | 92.1 ms | 14.2 | 47.6 ms | 20.4 ms |
| Docker linux/arm64 on the same Mac (Docker Desktop VM, 10 vCPU) | 365.1 ms | 494.3 ms | 639.9 ms | 2.6 | 210.0 ms | 152.5 ms |

- **What these numbers cover:** inference latency for one image. Reading a camera at 30 fps is a separate step: the tracker handles every frame, and only one best frame per part is sent for inspection.
- **What 14 inspections per second supports:** at the default belt settings (200 mm/s, 600 mm from camera to diverter, 300 mm between parts), there is about 2,970 ms to decide each part (`/edge/budget`). That is far more than the 70–365 ms measured.
- **Golden reference cost:** an active golden reference adds the legacy classical stream, which raised the simulated run's median from 67 ms to 258 ms.
- **Not tested:** no Jetson, Raspberry Pi, industrial PC or GPU deployment. The Docker slowdown was measured but its cause was not investigated (likely ONNX Runtime threading inside the VM).

## 6. Continuous learning

`backend/app/services/learning/`:
1. Reviewer labels and uploads become `DatasetSample`s.
2. Every fifth sample of each label goes to the HOLDOUT split, permanently.
3. A dataset version is frozen with a content hash.
4. A candidate anomaly model is fitted, then the candidate and the current production model are both scored on the same holdout.
5. The gate checks:
   - minimum holdout sizes;
   - AUROC must not fall;
   - recall and false-reject rate within limits.
6. Promotion goes through if the gate passes; any earlier version can be rolled back.

Automated tests cover:
- the holdout never changing;
- the dataset hash staying stable;
- a worse candidate being refused;
- the rollback pointer returning to the earlier version.

The live workflow run (`e2e_workflows.json` #15) trained, gated, promoted and rolled back a real bottle model through the API.

**Retraining YOLO-seg with new classes is not automated**: it needs mask labels and `ml/train_yolo_seg.py`.

## 7. Reproduce

```bash
# environments
python3 -m venv ml/.venv && ml/.venv/bin/pip install -r ml/requirements.txt
# data (see DATASETS.md)
python3 ml/datasets/download_hf.py --dataset mvtec --out datasets/mvtec_ad
ml/.venv/bin/python ml/datasets/prepare_mvtec.py --root datasets/mvtec_ad --out datasets/prepared
# anomaly
ml/.venv/bin/python ml/anomaly/export_backbone.py --arch resnet18 --size 256 --out backend/storage/models/anomaly/resnet18_256.onnx
ml/.venv/bin/python ml/anomaly/evaluate.py --manifest datasets/prepared/manifest.json \
  --backbone backend/storage/models/anomaly/resnet18_256.onnx \
  --out backend/storage/reports/eval_anomaly.json --save-models backend/storage/models/anomaly/products
cp backend/storage/models/anomaly/resnet18_256.onnx backend/storage/models/anomaly/backbone.onnx
# segmentation
ml/.venv/bin/python ml/train_yolo_seg.py --data datasets/prepared/yolo/data.yaml --model yolo11n-seg.pt --epochs 60 --name yolo11n_seg
ml/.venv/bin/python ml/evaluate_supervised.py --weights ml/runs/yolo11n_seg/weights/best.pt \
  --onnx ml/runs/yolo11n_seg/yolo11n_seg.onnx --out backend/storage/reports/eval_segmentation.json
cp ml/runs/yolo11n_seg/yolo11n_seg.onnx backend/storage/models/segmentation/production.onnx
# decision level and speed (from backend/)
.venv/bin/python scripts/evaluate_decision.py
.venv/bin/python -m scripts.benchmark_edge --samples storage/demo_samples/metal_nut --product metal_nut
```

## Licences

| Item | Licence | Consequence |
|---|---|---|
| MVTec AD | CC BY-NC-SA 4.0 | Models trained on it are **non-commercial**; retrain on own data for commercial use |
| Ultralytics YOLO11 | AGPL-3.0 | Network use of a modified version requires releasing source, or buy an Ultralytics licence |
| torchvision ResNet weights | BSD-3-Clause (ImageNet terms apply to the data) | |
| ONNX Runtime, OpenCV | MIT / Apache-2.0 | |

## Legacy model

`backend/storage/models/legacy/best.onnx` shipped with the original repository. Its training data and metrics are undocumented, so it is not loaded by default. The original tests still exercise it. To use it, set `DEFECT_MODEL_PATH`.
