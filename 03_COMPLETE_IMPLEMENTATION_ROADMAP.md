# 03 — Complete Implementation Roadmap

Execution plan derived from `01_PROBLEM_STATEMENT_REQUIREMENTS.md` (R-xx IDs) and `02_PARAKHMAAN_EXISTING_PROJECT_AUDIT.md`.
Status keys: ☐ not started · ◐ in progress · ☑ acceptance criteria tested · ⚠ done with a recorded limitation.
Every phase runs the loop: **ANALYZE → PLAN → IMPLEMENT → INTEGRATE → TEST → EVALUATE → FIX → OPTIMIZE → VERIFY → DOCUMENT**.

## Target architecture

```
                            ┌────────────────────── Edge node (single process, no cloud) ───────────────────────┐
Browser camera ─ WebSocket ─▶                                                                                   │
USB/RTSP/video ─ capture ───▶ bounded queue ▶ UnitTracker ▶ best frame ▶ InferenceEngine ▶ DecisionEngine ▶ log ├▶ SQL
                            │ (drop oldest)   (every frame)              ├ YOLO-seg ONNX   (per-product rules)  │
                            │                                            ├ Anomaly (per-product memory bank)    ├▶ RejectActuator
                            │                                            ├ OpenCV classical                     │  sim / serial / webhook
                            │                                            └ Metrology (calibrated mm)            │
                            └───────────────────────────────────────────────────────────────────────────────────┘
Feedback ▶ dataset version ▶ training job (ml/) ▶ holdout evaluation ▶ promotion gate ▶ production pointer ▶ rollback
Analytics: Pareto · machine/batch/shift · FPY · p-chart alerts · association tests (correlation, not cause)
Legal Metrology module: unchanged rule engine behind its own navigation
```

### Key engineering decisions

| # | Decision | Reason | Alternative rejected |
|---|---|---|---|
| D1 | Three evidence streams: YOLO segmentation (classify), memory-bank anomaly (unknowns), geometry (measurement) | No single model covers all of R-04…R-08 | YOLO only: blind to new defects, cannot measure |
| D2 | MVTec AD as the main supervised dataset, with labels mapped onto the 5 classes | Real images with pixel masks across many products; includes crack, scratch, colour, bent/poke, squeeze | NEU-DET only: steel texture, no dent or dimensional class |
| D3 | Group-aware split by category + defect type, no image in two splits | Prevents leakage | Random image split |
| D4 | ONNX Runtime replaces cv2.dnn | Supports seg and arbitrary models, reports providers | cv2.dnn: limited operator support |
| D5 | Anomaly model fits per product from good images, no labels | Gives no-code onboarding (R-32) | Single global anomaly model |
| D6 | Heavy inference runs once per tracked unit; tracker runs on every frame | Lets a CPU keep up with a conveyor and gives one decision per unit | Inference on every Nth frame (is sampling, not inspection) |
| D7 | Additive schema: new tables, existing tables keep working, `run_lightweight_migrations` extended | Rule engine untouched, SQLite demo stays simple | Alembic rewrite: no benefit for this schema size yet |
| D8 | Separate `ml/` environment for PyTorch; backend runtime has no torch | Keeps the edge image small | Single environment |
| D9 | Legal Metrology kept at existing routes, moved to a side section in navigation | R-33 | Merge into the defect flow |

## Dependency graph and critical path

```
P0 Baseline ─▶ P1 Security/Arch ─▶ P2 Data ─▶ P3 Train+Eval ─▶ P4 Inference engine ─▶ P5 Metrology ─┐
                     │                                                                              ▼
                     └────────────▶ P6 Domain schema ─▶ P7 Decision+Line ─▶ P8 Real-time ─▶ P9 Analytics ─▶ P11 Frontend ─▶ P13 Verify ─▶ P14 Docs
                                                                 P3 ─▶ P10 Continuous learning ─────────────┘
                                                                         P12 Docker/Edge ───────────────────┘
```
**Critical path:** P0 → P1 → P2 → P3 → P4 → P6 → P7 → P8 → P9 → P11 → P13.
Parallelisable: P5, P10, P12 once P4/P6 exist.

---

## P0 Repository analysis and baseline (items 1)

- **Objective:** know the true starting point.
- **Tasks:** back up original; run tests; build frontend; boot API; write audit.
- **Files:** `02_PARAKHMAAN_EXISTING_PROJECT_AUDIT.md`.
- **Dependencies:** Python 3.12 venv, Node 22.
- **Deliverable:** audit with verified/unverified columns.
- **Testing:** `pytest`, `next build`, health check.
- **Acceptance:** baseline numbers recorded.
- **Done when:** all three commands have recorded output.

## P1 Architecture restructuring and security (item 2, 21-partial)

- **Objective:** close critical holes without breaking legal flow.
- **Tasks:** bcrypt with transparent legacy upgrade; drop plaintext comparison; drop implicit default user; drop any-password auto-create outside `DEMO_MODE`; required `SECRET_KEY` outside demo mode; explicit CORS list; upload type/size validation; RBAC helper; fix `/reviews` and `/reports` frontend path mismatches; rename app metadata.
- **Files modified:** `backend/app/core/{config,security,database}.py`, `backend/app/api/auth.py`, `backend/app/main.py`, `backend/app/services/storage_service.py`, `frontend/src/lib/api.ts`, `.gitignore`, `docker-compose.yml`.
- **New:** `backend/.env.example`, `backend/app/core/permissions.py`, `backend/tests/test_security.py`.
- **Testing:** new security tests + all existing tests.
- **Acceptance:** anonymous write returns 401; wrong password returns 400/401; legacy hash upgrades at login; rule tests unchanged.
- **Done when:** R-35 tests pass.

## P2 Dataset research, acquisition and preparation (items 4, 5)

- **Objective:** real, documented training data with no leakage.
- **Tasks:** download; verify licences; map labels to taxonomy; convert masks to YOLO-seg polygons; grouped split; write manifests with SHA-256; class-balance report.
- **New:** `ml/datasets/download_hf.py`, `ml/datasets/prepare_mvtec_yolo.py`, `ml/datasets/label_map.py`, `ml/tests/test_split_integrity.py`, `docs/DATASETS.md`.
- **Dependencies:** network speed; a partial dataset is acceptable and must be disclosed.
- **Testing:** assert no file hash across two splits; class counts non-zero.
- **Acceptance:** train/val/test exist, and every class appears in val and test.
- **Done when:** leakage test passes and licences are documented.

## P3 Model selection, training, evaluation, optimisation (items 6, 7, 8, 9, 10)

- **Objective:** measured models, chosen by results.
- **Tasks:**
  1. Anomaly: fit memory-bank model on good images per category; test backbone candidates; choose by AUROC vs latency.
  2. Supervised: train nano and small YOLO-seg candidates; compare on val, report once on test.
  3. Threshold selection on validation.
  4. Withheld-class experiment for unknown defects.
  5. Error analysis by class and size.
  6. ONNX export; latency benchmark on reference CPU.
- **New:** `ml/train_yolo_seg.py`, `ml/anomaly/{patchcore.py,fit.py,evaluate.py}`, `ml/evaluate_supervised.py`, `ml/benchmark_inference.py`, `docs/MODELS.md`.
- **Outputs:** `backend/storage/models/**`, `backend/storage/reports/eval_*.json`.
- **Testing:** smoke tests on small fixtures; ONNX vs PyTorch numerical match.
- **Acceptance:** all metrics of AI-6 reported on held-out real images; synthetic results labelled separately.
- **Done when:** report JSONs exist and `docs/MODELS.md` cites them.

## P4 Inference engine (items 3, 10 integration)

- **Objective:** replace the model plug-in with a versioned engine.
- **Tasks:** `SegDetector` (ONNX Runtime, mask decode); `AnomalyEngine` (backbone ONNX + NumPy kNN, per product); `HybridFusion` (merge streams, disagreement → review); keep OpenCV path as fallback; golden compare service with alignment; severity from mask; attach `model_version` to each result.
- **Files modified:** `backend/app/services/defect_detection_service.py`, `heatmap_service.py`, `backend/requirements.txt`.
- **New:** `backend/app/services/inference/{engine.py,seg_detector.py,anomaly_engine.py,fusion.py,golden.py,severity.py}`.
- **Testing:** existing `test_defects.py` keep passing; missing model degrades visibly; multi-defect test on real images.
- **Acceptance:** real defect image yields box + mask + class + severity + heatmap.
- **Done when:** R-04…R-07, R-09, R-10 pass integration tests.

## P5 Dimensional inspection (item 11)

- **Objective:** real geometry.
- **Tasks:** checkerboard calibration (intrinsics + planar homography); reference-length px/mm; perspective rectify; measure length/width/diameter/roundness; contour deviation vs golden; notch detection; tolerance check; print assumptions; synthetic known-geometry validation.
- **New:** `backend/app/services/metrology/{calibration.py,measure.py,tolerance.py}`, `backend/app/api/metrology.py`, `backend/tests/test_metrology.py`, `ml/validate_metrology.py`.
- **Acceptance:** synthetic known-geometry mean error ≤ 1%; results carry `calibration` block with assumptions. Physical accuracy marked **not validated**.
- **Done when:** R-08 passes.

## P6 Database and API (item 15)

- **Objective:** traceable manufacturing schema.
- **New tables:** `products`, `golden_references`, `calibrations`, `machines`, `production_lines`, `batches`, `production_units`, `reject_events`, `quality_alerts`, `corrective_actions`, `model_versions`, `dataset_versions`, `dataset_samples`, `training_jobs`.
- **Modified:** `backend/app/models/all_models.py`, `core/database.py`, `defect_detections` gains `mask_rle`, `length_mm`, `width_mm`, `area_mm2`, `model_version`, `unit_id`.
- **New routers:** `products`, `production`, `edge`, `models`, `datasets`, `analytics`.
- **Testing:** migration on the shipped DB copy; API CRUD tests.
- **Acceptance:** upgrade existing DB without data loss; legal rows intact.

## P7 Production-line automation (item 14)

- **Objective:** deterministic decision and reject interface.
- **New:** `backend/app/services/line/{decision.py,actuator.py,conveyor_sim.py}`, `firmware/reject_controller/reject_controller.ino`, `docs/HARDWARE_INTERFACE.md`.
- **Tasks:** per-product decision policy; `ACCEPT/REJECT/MANUAL_REVIEW`; actuator back ends; delay from belt speed; latency budget calculator.
- **Testing:** policy table tests; timing test with fake clock; firmware compile if toolchain is available, else disclosed unverified.
- **Acceptance:** rejects fire only for REJECT, with computed delay.

## P8 Real-time inspection and edge (items 12, 13)

- **Objective:** continuous pipeline with honest telemetry.
- **New:** `backend/app/services/realtime/{pipeline.py,tracker.py,sources.py,telemetry.py}`, `backend/app/api/live.py` (WebSocket + REST).
- **Tasks:** bounded queue; background-subtraction segmenter; centroid/IoU tracker; line-crossing trigger; best-frame by sharpness; dedupe; live stats; simulated conveyor video source built from held-out real images.
- **Testing:** conveyor E2E: N injected units → N records, no duplicates; overload test counts dropped frames.
- **Acceptance:** R-12, R-15; UI differentiates tracked stream and sampled review.

## P9 Manufacturing analytics (item 16)

- **New:** `backend/app/services/analytics/{quality.py,spc.py,association.py}`.
- **Tasks:** Pareto; group-bys; FPY; p-chart with Wilson-safe limits; Fisher/chi-square + odds ratio with Benjamini-Hochberg correction; drill-down; corrective-action notes; correlation disclaimer.
- **Testing:** hand-computed fixtures; injected fault found; stable data raises nothing.
- **Acceptance:** R-24…R-28.

## P10 Human-in-the-loop, retraining, versioning (items 17, 18)

- **New:** `backend/app/services/learning/{dataset_service.py,registry.py,gate.py,job_runner.py}`, `ml/retrain_anomaly.py`, `ml/retrain_yolo.py`.
- **Tasks:** extend feedback to full-image samples; review queue; annotation records; hashed dataset versions; subprocess jobs with logs; holdout evaluation; promotion gate; rollback.
- **Testing:** worse candidate refused; rollback; holdout leakage assert; real E2E on a product.
- **Acceptance:** R-20…R-23, R-32.

## P11 Frontend (items 19, 20)

- **Objective:** sixteen-section product using existing tokens (`DESIGN.md`) and components.
- **Tasks:** left navigation shell; login; Overview; Live; Detection (reuse `/defects`); Dimensional; Golden; Line; Batches; History; Analytics; Root Cause; Model Performance; Dataset & Feedback; Model Versions; Reports; Settings; Rule Engine (existing pages unchanged).
- **Reuse:** `DefectOverlay`, `DefectTable`, `DefectCharts`, `CameraCaptureModal`, `AuditTimeline`, `ImageQualityCard`.
- **Testing:** `next build`, lint, browser walkthrough with real backend data.
- **Acceptance:** no placeholder buttons; every number from the API.

## P12 Docker and deployment (item 21)

- **Files:** `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `.env.example`, `docker-compose.edge.yml`.
- **Testing:** `docker compose up --build`; health check; inference inside the container.
- **Acceptance:** clean-machine commands work.

## P13 Testing, optimisation, debugging (item 22)

- Run the 18 end-to-end workflows of the brief, record pass/fail with evidence.
- Regression: all tests, build, Docker.
- Fix all critical issues, repeat.

## P14 Final demonstration and documentation (item 23)

- `README.md`, `docs/DATASETS.md`, `docs/MODELS.md`, `docs/API.md`, `docs/DEMO_SCRIPT.md`, `FINAL_IMPLEMENTATION_REPORT.md`, traceability report.
- **Acceptance:** every row in the RTM has a test and a result.

## Phase status (2026-11-02)

| Phase | Status | Evidence | Deviation from plan / limitation |
|---|---|---|---|
| P0 Baseline | ☑ | 02 audit: 40 passed / 3 failed, build, health | |
| P1 Security | ☑ | `test_security.py` 19 cases; container refuses start without `SECRET_KEY` | Public `/storage` mount also removed (authenticated `/api/v1/files`) |
| P2 Data | ☑ | `manifest.json`: SHA-256 per file, `cross_split_duplicates: 0`; `docs/DATASETS.md` | Leakage is checked by the prepare script and recorded in the manifest, not by a separate `ml/tests/test_split_integrity.py` |
| P3 Models | ☑ | `eval_anomaly*.json`, `eval_segmentation.json`; `docs/MODELS.md` | Only YOLO11n trained (no small variant: time). Benchmark is `backend/scripts/benchmark_edge.py`, not `ml/benchmark_inference.py` |
| P4 Inference engine | ☑ | E2E #1, #4, #5, #6; `test_classical_findings_need_anomaly_support` | Fusion lives in `engine.py`, no separate `fusion.py` |
| P5 Metrology | ⚠ | `test_measurement_error_under_one_percent`, E2E #7 | Synthetic geometry only; physical accuracy not validated. Validation is a backend test, not `ml/validate_metrology.py` |
| P6 Database and API | ☑ | Lightweight migrations on the shipped DB; legal rows intact; E2E #9 | |
| P7 Line automation | ⚠ | `test_decision_table`, `test_latency_budget_and_missed_window`, E2E #17 | Simulated actuator; serial/webhook against fakes; firmware not compiled (no `arduino-cli`) |
| P8 Real time and edge | ⚠ | Conveyor E2E, tracker tests, `benchmark_edge.json`, `benchmark_docker.json` | One device; no edge board; no `docker-compose.edge.yml` (the main compose runs offline) |
| P9 Analytics | ☑ | SPC/association tests; simulated M-02 fault found; E2E #12, #13 | Fault is simulated |
| P10 Learning | ⚠ | `test_learning.py`, E2E #15, `e2e_onboarding.json` | Anomaly retraining automated; YOLO class retraining manual (`ml/train_yolo_seg.py`) |
| P11 Frontend | ☑ | `next build` 27 routes; headless walkthrough of 16 sections, 0 errors | 59 lint errors remain in original Legal Metrology files |
| P12 Docker | ☑ | Compose healthy; login, upload, PDF, CORS, offline inference | Docker 5× slower than native, not investigated |
| P13 Testing | ☑ | 101 tests pass; 18/18 workflows (`e2e_workflows.json`) | |
| P14 Docs | ☑ | `README.md`, `FINAL_IMPLEMENTATION_REPORT.md`, `docs/REQUIREMENT_TRACEABILITY.md`, `docs/MODELS.md`, `docs/DATASETS.md` | API docs are the live OpenAPI page (`/docs`) plus the README table, and the demo script is a README section; no separate `docs/API.md` or `docs/DEMO_SCRIPT.md` |

## Item coverage

| Brief item | Phase | | Brief item | Phase |
|---|---|---|---|---|
| 1 Analysis/cleanup | P0 | | 13 Edge deployment | P8, P12 |
| 2 Restructuring | P1 | | 14 Line automation | P7 |
| 3 CV improvements | P4 | | 15 DB and API | P6 |
| 4 Dataset research | P2 | | 16 Analytics | P9 |
| 5 Preparation | P2 | | 17 Human-in-the-loop | P10 |
| 6 Model selection | P3 | | 18 Retraining/versioning | P10 |
| 7 Training | P3 | | 19 Frontend | P11 |
| 8 Evaluation | P3 | | 20 Rule engine | P1, P11, P13 |
| 9 Unknown defects | P3, P4 | | 21 Docker | P12 |
| 10 Segmentation | P3, P4 | | 22 Testing | P13 |
| 11 Dimensional | P5 | | 23 Demo and docs | P14 |
| 12 Real-time | P8 | | | |

## Change log

| Date | Change | Reason |
|---|---|---|
| 2026-11-01 | Initial roadmap | From audit |
| 2026-11-02 | Phase status table added | Final verification: 101 tests, 18/18 workflows |
