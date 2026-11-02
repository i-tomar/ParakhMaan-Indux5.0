# Final Implementation Report

ParakhMaan was upgraded from a Legal Metrology compliance platform into an industrial AI visual inspection platform for Hackathon PS-12, *AI & Computer-Vision Based Surface & Product Defect Inspection*.

Every figure here is measured and traceable to a file in `backend/storage/reports/`. Where something was not tested, this report says so.

## 1. Original project audit summary

Full audit: [02_PARAKHMAAN_EXISTING_PROJECT_AUDIT.md](02_PARAKHMAAN_EXISTING_PROJECT_AUDIT.md).

- **What it was:** a Legal Metrology compliance platform (SIH26034): OCR/LLM label extraction, a deterministic rule engine (`rules.json`), PDF reports and a Next.js UI. A classical OpenCV "defect mode" had been added later.
- **Reusable for PS-12:** about **27% of requirements**, or 35–40% counting platform plumbing. The assumed 60% did not hold.
- **The defect model shipped with it** (`best.onnx`) had no record of its training data. Its evaluation was synthetic only, and it scored zero recall on two named classes.
- **Missing entirely:**
  - production context (batch, machine, line, shift);
  - unit tracking and a continuous pipeline;
  - calibrated measurement and a reject interface;
  - anomaly detection and segmentation;
  - a model registry and retraining.
- **Security:**
  - fixed-salt SHA-256 password hashes, and a stored hash was accepted as a password;
  - any password created a demo account;
  - no token meant a default user;
  - hard-coded JWT secrets, open self-registration with a chosen role, and CORS `*`;
  - no upload checks, and a public `/storage` mount.
- **Baseline tests:** 40 passed, 3 failed. All 3 came from `cv2.setLogLevel`, which does not exist in pip OpenCV, so loading any trained model crashed.
- **Other bugs:** `npm ci` was broken (lockfile out of sync), and two Legal Metrology frontend routes returned 404 (review and report).

## 2. Work completed

| Phase (roadmap) | Delivered |
|---|---|
| P0 Planning | The three master documents, with a 35-row requirement matrix |
| P1 Security | bcrypt with legacy-hash upgrade; JWT with required secret in production; roles; no default accounts; upload limits; CORS allow-list; authenticated file route replacing public `/storage` |
| P2 Data | MVTec AD downloader and grouped, leak-free split (SHA-256 checked, 0 cross-split duplicates), YOLO-seg export, withheld-unknown set |
| P3 Anomaly | ONNX backbone export, PatchCore-style memory bank per product, evaluation on all 15 products with two backbones |
| P4 Segmentation | YOLO11n-seg trained 60 epochs on MPS, ONNX export, NumPy decoder in the backend, held-out evaluation |
| P5 Fusion and decision | Three-stream engine with anomaly corroboration of classical findings; per-product DecisionPolicy; decision-level evaluation |
| P6 Metrology | Checkerboard and reference calibration, mm measurements, tolerances, contour deviation, stated assumptions |
| P7 Real time | Unit tracker, bounded queue, browser/USB/RTSP/video/simulated-conveyor sources, WebSocket stream |
| P8 Line | Latency budget, MISSED_WINDOW handling, simulated/serial/webhook actuators, reject events, firmware sketch (untested) |
| P9 Logging | Products, golden references, lines, machines, batches, units, detections with model version and latency |
| P10 Analytics | KPIs, Pareto, p-chart with alerts, group-by, Fisher/BH root cause with filters, corrective actions, batch PDF |
| P11 Learning | Samples, fixed holdout, dataset versions, retraining, gate, promotion, rollback, onboarding |
| P12 Frontend | 16 sections in the existing design language; login; protected images and PDFs |
| P13 Deployment | Hash-locked backend image without PyTorch, non-root; compose with health check; `.env.example`; `.dockerignore` |
| P14 Verification | 101 tests, 18/18 workflows, headless-browser walkthrough, Docker checks, documents |

## 3. Architecture changes

- **Before:** an upload API calling one OpenCV detector, with an optional `cv2.dnn` ONNX model behind a lock, and the Legal Metrology flow alongside.
- **After:**

```
sources (upload / video / browser camera / USB / RTSP / simulated conveyor)
  → bounded queue → UnitTracker (one ID per part, best frame, trigger line)
  → InspectionEngine [YOLO11n-seg ‖ anomaly memory bank ‖ classical+golden (corroborated)] + metrology
  → DecisionPolicy → actuator → ProductionUnit / DefectDetection / RejectEvent
  → analytics (Pareto, p-chart, association) → alerts → corrective actions
  → review queue → DatasetSample (fixed holdout) → DatasetVersion → training → gate → ModelVersion (promote / rollback)
```

**Changes in more detail:**
- **Inference** moved from `cv2.dnn` to ONNX Runtime. The runtime image carries no PyTorch.
- **New tables:**
  - production context: `products`, `golden_references`, `calibration_profiles`, `production_lines`, `machines`, `batches`;
  - line results: `production_units`, `reject_events`;
  - analytics: `quality_alerts`, `corrective_actions`;
  - learning: `model_versions`, `dataset_versions`, `dataset_samples`, `training_jobs`.
- **New columns:** `defect_detections` gained `unit_id`, `model_version` and mm measurements, through lightweight migrations.
- **API:** routers are protected by default; only `/api/health` and `/api/v1/auth/login` are public.
- **Frontend:** the navigation was replaced with a 16-section shell. The Legal Metrology pages sit under *Rule-Based Engine*.

## 4. Existing functionality reused

| Kept | How |
|---|---|
| Legal Metrology rule engine, OCR/LLM services, routes, UI | Unchanged; `rules.json` MD5 `f30a15e4ae2d9d04c5d3735441d8be64` identical; all original rule tests pass; E2E #18 |
| OpenCV surface detector (`defect_detection_service.py`) | Kept as the classical stream and the fallback when no learned model exists; one bug fixed (`setLogLevel`) |
| Image quality analyser, heatmap service, PDF service | Reused; PDF service extended with batch reports |
| FastAPI app, SQLAlchemy models, storage service, audit events | Extended |
| Next.js app and design tokens | Reused for all new pages |
| Legacy `best.onnx` | Moved to `storage/models/legacy/` with a note; not loaded by default; its original tests still run |

## 5. New features implemented

These are listed in the README *Main features* table. The items that most change what the product can do:

1. **Unknown-defect detection.** On 342 test images of defect kinds no model was trained on, 91.8% were flagged.
2. **Segmentation masks** for the five named classes.
3. **Unit tracking** so each part is decided and logged exactly once: 43/43 and 23/23 parts.
4. **A real reject path** with timing budget and missed-window logging.
5. **Root cause with statistics** that found an injected machine fault and nothing else.
6. **A gated learning loop:** a worse model cannot reach production, and rollback restores the earlier one.

## 6. Model training and evaluation results

Details and per-product tables: [docs/MODELS.md](docs/MODELS.md). Data: MVTec AD, CC BY-NC-SA 4.0, real images only; the split is in [docs/DATASETS.md](docs/DATASETS.md).

**Anomaly model** (ResNet-18 memory bank, 15 products, val-chosen thresholds, test split):

| Metric | Result |
|---|---|
| Mean image AUROC | 0.979 (WRN-50: 0.984) |
| Mean pixel AUROC | 0.977 |
| Recall on mapped defects | 0.915 |
| Recall on withheld kinds | 0.918 (342 images) |
| False-reject rate | 0.094 |

- **Strongest products:** bottle, hazelnut, leather, tile and wood, with image AUROC 1.000.
- **Weakest:** screw (0.930 AUROC, 47.6% false-reject), zipper (37.5% false-reject), grid (27.3% false-reject) and transistor (40% miss).

**YOLO11n-seg** (398 test images, 228 instances):

| Metric | Result |
|---|---|
| Box mAP@50 | 0.606 |
| Mask mAP@50 | 0.585 |
| Image-level precision | 0.993 |
| Image-level recall | 0.848 |
| False-reject rate | 0.4% |

Per-class F1: SCRATCH 0.765, DISCOLOURATION 0.681, CRACK 0.621, DENT 0.532, DIMENSIONAL_ANOMALY 0.430. Recall by defect size: small 0.73, medium 0.88, large 1.00.

**Full system decision** (engine + default policy, 740 test images):

| Outcome | Result |
|---|---|
| Good parts auto-rejected | 0 / 234 |
| Good parts sent to review | 9.4% |
| Defective parts caught | 88.9% (24.3% auto-rejected, 64.6% sent to review) |
| Defective parts escaped | 11.1% (56 / 506) |

Escapes are concentrated in capsule (16), pill (11) and transistor (8).

**Targets from 01 §14:**

| Target | Result |
|---|---|
| Anomaly AUROC ≥ 0.90 | Met (0.979) |
| Per-class mAP reported for all 5 classes | Met |
| Unknown-defect recall reported | Met (0.918) |
| Dimensional error ≤ 1% on synthetic geometry | Met |
| Conveyor: seen = logged = decided, no duplicate IDs | Met, after a tracker fix |
| Worse candidate refused in an automated test | Met |
| Rollback in an automated test | Met |
| Rule engine tests pass and `rules.json` unchanged | Met |

## 7. Performance benchmarks

Full pipeline, 200 runs on real images, CPU (`benchmark_edge.py`):

| Device | p50 | p95 | p99 | Sequential FPS |
|---|---|---|---|---|
| Apple M1 Pro, macOS, native | 69.7 ms | 74.8 ms | 92.1 ms | 14.2 |
| Docker linux/arm64 on the same Mac | 365.1 ms | 494.3 ms | 639.9 ms | 2.6 |

**Stages and supporting runs:**
- **Stage p50 (native):** segmentation 47.6 ms, anomaly 20.4 ms. The anomaly model alone is 16.8 ms p50.
- **Simulated line run** (300 units): median 67 ms per unit without a golden reference, and 258 ms with the legacy golden comparison active.
- **Latency budget** at 200 mm/s, 600 mm camera-to-diverter and 300 mm pitch: 2,970 ms per decision and 40 units/min.
- **Offline:** inference also ran in the container with networking disabled.
- **Not measured:** any embedded edge board, GPU, industrial camera, or physical conveyor and diverter.

## 8. Test results

| Suite | Result |
|---|---|
| Backend unit and integration (`pytest tests`) | **101 passed**, 0 failed (original: 40 passed, 3 failed) |
| End-to-end workflows (`scripts/e2e_workflows.py`, live server, real images) | **18 / 18 PASS** (`e2e_workflows.json`) |
| New-product onboarding through the API | Passed (`e2e_onboarding.json`) |
| Frontend `next build` | Succeeds, 27 routes |
| Headless Chrome walkthrough (real login, all 16 sections + unit and defect detail) | 0 exceptions, 0 console errors, 0 failed API calls; protected images load |
| Docker | Both images build; compose healthy; login, upload, PDF and CORS checked; secret enforced; non-root; offline inference |
| Frontend lint | 59 errors, all in original Legal Metrology files; new pages have no errors |

**Defects found by running the system and fixed** (details in [docs/REQUIREMENT_TRACEABILITY.md](docs/REQUIREMENT_TRACEABILITY.md#defects-found-and-fixed-during-verification)):

| Defect | Severity / effect |
|---|---|
| Public `/storage` exposed the database and images | Critical |
| Golden reference rejected good parts | 60% of good val parts flagged |
| Tracker double-counted parts | 49 units logged for 43 parts |
| Simulated conveyor ran empty | No parts seen |
| Analytics ignored review units | 0 of 57 defective parts counted |
| Deployed thresholds differed from reported ones | Decisions did not match the published numbers |
| Model Performance page crashed | Page failed to render |
| Measurement bias | Every side read about 1.5 px too long |
| Login import error, demo-seed syntax error | Login and demo seeding broken |
| Pre-existing `setLogLevel` crash | Any trained model failed to load |
| Missing root-cause filters | No drill-down by line, machine, batch or shift |

## 9. Requirement coverage

[docs/REQUIREMENT_TRACEABILITY.md](docs/REQUIREMENT_TRACEABILITY.md) covers all 35 requirements:

- **30 VERIFIED.**
- **5 PARTIAL:**
  - R-08: dimensional accuracy is verified on synthetic geometry only.
  - R-12: real-time speed is measured on one device only.
  - R-15: conveyor timing is calculated, not measured physically.
  - R-19: the actuator is simulated.
  - R-32: new defect classes need manual YOLO retraining.
- **0 NOT VERIFIED.**

## 10. Known limitations

1. **No physical hardware tested.**
   - The actuator is simulated.
   - Serial and webhook back ends are tested against fakes only.
   - The firmware has not been compiled.
   - Belt timing is calculated, not measured.
   - No industrial camera, edge board or GPU was used.
2. **Studio data only.** MVTec AD shows one centred part under controlled light. Line accuracy will be lower until the models are retrained on line images.
3. **Weak products and classes.**
   - Screw, zipper and grid reject too many good parts.
   - Capsule, pill and transistor miss too many defects.
   - DIMENSIONAL_ANOMALY (F1 0.43) and DENT (0.53) are weak.
   - Test sets are small (6–30 good images per product).
4. **High review share.** 64.6% of caught defects go to a person, because the default policy does not auto-reject unnamed anomalies.
5. **Metrology** is verified only on synthetic images. Real parts have not been checked against a gauge.
6. **The golden-reference stream** adds no measured value on MVTec once learned models exist, and costs about 190 ms per image.
7. **Docker is 5× slower** than native on this Mac. The cause was not investigated.
8. **Licences are non-commercial.** The models are MVTec-trained (CC BY-NC-SA), Ultralytics is AGPL-3.0, and commercial use needs retraining and licensing.
9. **Single-process SQLite deployment.** Live sessions are held in memory.
10. **Original demo database:** its 35 image rows point to Windows paths from the original author's machine, so those images do not display.
11. **59 lint errors remain** in original Legal Metrology frontend files.

## 11. Future improvements

1. **Collect line images** through the review queue and retrain both models per product. This is the single biggest accuracy gain available.
2. **Measure on target hardware.** Benchmark on the intended edge device (Jetson Orin or an x86 IPC with OpenVINO), and try INT8 quantisation of both ONNX models.
3. **Commission a physical diverter** with the serial controller, a safety interlock and measured belt timing.
4. **Fix the weak products:** a higher-resolution or tiled anomaly model for screw and zipper, and dedicated metrology profiles for transistor leads and screw threads instead of the DIMENSIONAL_ANOMALY class.
5. **Automate YOLO retraining** with mask annotation in the review UI, so new defect classes need no ML engineer.
6. **Investigate the Docker slowdown** (thread settings, x86 build) and move to PostgreSQL for multi-line deployments.
7. **Validate metrology** against gauge measurements of real parts, with lens-distortion calibration.
8. **Replace MVTec-trained models** with ones trained on licensed or customer data for commercial use.
