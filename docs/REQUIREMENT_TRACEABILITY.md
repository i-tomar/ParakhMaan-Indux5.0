# Requirement Traceability Report

Each row of the matrix in `01_PROBLEM_STATEMENT_REQUIREMENTS.md` §18 is shown with the code that implements it, the test that was run, the actual result and the remaining limitation.

**Status key.**
- **VERIFIED:** the acceptance criterion was tested and met.
- **PARTIAL:** it works, but part of the criterion is untested or not met.
- **NOT VERIFIED:** it is implemented but has no test against its criterion.

**Evidence files** (`backend/storage/reports/`):
- `e2e_workflows.json`: 18/18 workflows passed against a running server on 2026-11-02;
- `eval_anomaly.json`, `eval_segmentation.json`, `eval_decision.json`: model and decision evaluations;
- `benchmark_edge.json`, `benchmark_docker.json`: speed;
- `e2e_onboarding.json`: new-product onboarding.

**Test suite:** `cd backend && .venv/bin/python -m pytest tests -q` gives **101 passed**.

## Summary

| Status | Count | Requirements |
|---|---|---|
| VERIFIED | 30 | R-01, R-02, R-03, R-04, R-05, R-06, R-07, R-09, R-10, R-11, R-13, R-14, R-16, R-17, R-18, R-20, R-21, R-22, R-23, R-24, R-25, R-26, R-27, R-28, R-29, R-30, R-31, R-33, R-34, R-35 |
| PARTIAL | 5 | R-08 (synthetic geometry only), R-12 (one device), R-15 (calculated, not physical), R-19 (simulated actuator), R-32 (anomaly onboarding only) |
| NOT VERIFIED | 0 | |

"VERIFIED" for R-04 to R-07 means the class is detected and measured on held-out real images. It does not mean the score is high: per-class F1 ranges from 0.43 to 0.77.

## Matrix

| ID | Requirement | Implemented capability | Files / modules | Test performed | Actual result | Status | Remaining limitation |
|---|---|---|---|---|---|---|---|
| R-01 | Automatically examines products | Tracker triggers inspection per unit; no operator step | `services/realtime/pipeline.py`, `tracker.py` | E2E #17 conveyor; `test_tracker_counts_each_unit_once`, `test_split_silhouette_is_one_unit` | 12/12 units seen = inspected, 0 overflow; 43/43 and 23/23 parts tracked once over the full sample sets | VERIFIED | Simulated belt only |
| R-02 | Products and surfaces | Object and texture categories share one engine | `inference/engine.py` | Anomaly eval on 10 object + 5 texture categories | Mean image AUROC 0.979; textures (carpet, grid, leather, tile, wood) 0.962–1.000 | VERIFIED | |
| R-03 | Defects hard to see | Patch-level anomaly map; size-bucket recall | `anomaly_engine.py`, `ml/evaluate_supervised.py` | Size-bucket evaluation | Recall: small (<0.5% area) 0.73, medium 0.88, large 1.00; pixel AUROC 0.977 | VERIFIED | Small defects are the weakest |
| R-04 | Scratches | YOLO-seg class SCRATCH | `seg_detector.py` | Held-out per-class eval; E2E #4 | P 0.759, R 0.772, F1 0.765, AP50 0.796 (53 instances) | VERIFIED | |
| R-05 | Cracks | Class CRACK | same | same | P 0.663, R 0.585, F1 0.621, AP50 0.618 (37) | VERIFIED | |
| R-06 | Dents | Class DENT (poke/hole/dent-like labels, mapping documented) | same, `ml/datasets/label_map.py` | same | P 0.602, R 0.476, F1 0.532, AP50 0.551 (21) | VERIFIED | Few examples; mapping is a judgement call |
| R-07 | Discolouration | Class DISCOLOURATION + CIELAB ΔE in classical detector | same, `defect_detection_service.py` | same | P 0.751, R 0.623, F1 0.681, AP50 0.674 (69) | VERIFIED | |
| R-08 | Dimensional anomalies | Calibration, mm measurement, tolerances, contour deviation; plus YOLO class | `services/metrology/`, `api/metrology_api.py` | `test_measurement_error_under_one_percent`, `test_checkerboard_*`, E2E #7; YOLO class eval | Synthetic part 100×50 mm measured within 1%; out-of-tolerance flagged; checkerboard scale within 0.005 mm/px. YOLO class F1 0.430 | PARTIAL | No real part measured against a gauge; `physical_accuracy_validated=false` on every result |
| R-09 | Deep-learning models | YOLO11n-seg and ResNet-18 memory bank as ONNX, used by the API | `inference/`, `storage/models/` | E2E #1, #4, #5; `/api/health` lists models | Both models load and run in the API and the Docker image | VERIFIED | |
| R-10 | Computer-vision models | Original OpenCV detector kept, now corroborated; geometry; alignment | `defect_detection_service.py`, `engine.py` | Original 40 tests + `test_classical_findings_need_anomaly_support` | All pass; corroboration cutoff chosen on val | VERIFIED | Golden comparison adds no measurable recall on MVTec |
| R-11 | Camera images or video | Upload, video file, browser camera (WebSocket), USB/RTSP, simulated conveyor | `api/defects.py`, `api/live.py`, `realtime/sources.py` | E2E #1 (image), #2 (camera protocol), #3 (video) | Each source produced unit records with decisions | VERIFIED | Browser frames pushed by script. No physical webcam in the headless run |
| R-12 | In real time | Continuous tracker on every frame; bounded queue, drop-oldest; inference on best frame | `realtime/pipeline.py` | `benchmark_edge.py`; live session stats | Pipeline p50 69.7 ms / p95 74.8 ms on M1 Pro (14 FPS); 365 ms p50 in Docker VM | PARTIAL | One device only; no edge board |
| R-13 | Edge computing | ONNX Runtime CPU, no cloud call | `inference/`, backend `Dockerfile` | Inference in container with `--network none` | Worked; DNS lookup failed as expected | VERIFIED | |
| R-14 | Close to the line | Docker images + compose with health check | `docker-compose.yml`, `*/Dockerfile` | `docker compose up` | Healthy; login, upload, PDF, CORS checked | VERIFIED | No industrial PC tested |
| R-15 | Fast enough for a conveyor | Latency budget from belt speed, distance, pitch; MISSED_WINDOW events | `line/actuator.py`, `/edge/budget` | `test_latency_budget_and_missed_window`; E2E #17 | Budget 2,970 ms at 200 mm/s, 600 mm, 300 mm pitch vs measured 70–365 ms; no missed units in simulation | PARTIAL | Belt timing calculated, not measured on hardware |
| R-16 | Every defect logged | `defect_detections` linked to `production_units` | `inspection_service.record_unit` | E2E #1, #9 | Detections persisted and linked to the unit | VERIFIED | |
| R-17 | Categorised automatically | Class + severity from pipeline, UNKNOWN_ANOMALY when unnamed | `engine._finish`, `defect_detection_service` | E2E #10 | Every detection has a class from the six-label set and a severity | VERIFIED | |
| R-18 | Logged with context | Batch, machine, line, shift, model versions, latency on each unit | `models/industrial.py` | E2E #9; simulation | All fields populated in the simulated run | VERIFIED | |
| R-19 | Decision at the line | DecisionPolicy + simulated/serial/webhook actuators | `line/decision.py`, `line/actuator.py` | `test_decision_table` (9 cases), `test_serial_protocol_ack_and_timeout`, E2E #17 | Reject fired only for REJECT units; decisions deterministic | PARTIAL | No physical diverter; serial/webhook against fakes only |
| R-20 | Improve as samples collected | Feedback → samples → dataset → retrain → evaluate vs production | `services/learning/` | E2E #15 (bottle) | Candidate trained, scored on holdout with production rescored, gated, promoted, rolled back | VERIFIED | Improvement on real line data not demonstrated (no line data) |
| R-21 | Sample collection | Dataset samples, de-duplicated, versioned with content hash | `learning/service.py` | `test_dataset_version_hash_is_stable_and_changes_with_content` | Same content gives same version; added sample gives new hash | VERIFIED | |
| R-22 | Independent validation | Holdout fixed at insertion (1 in 5 per label); leakage assert | same | `test_holdout_split_is_fixed_at_insertion_and_never_moves` | Split unchanged after 10 more samples; duplicates ignored | VERIFIED | |
| R-23 | Safe improvement | Gate (holdout size, AUROC, recall, FRR) + rollback | `learning/gate.py`, `service.py` | `test_gate_refuses_regression_and_small_holdout`, `test_gate_failure_refuses_promotion_and_keeps_production`, `test_rollback_returns_production_pointer_to_previous_version` | Worse candidate refused; production pointer and engine return to v1 on rollback | VERIFIED | |
| R-24 | Most frequent types | Pareto with cumulative share | `analytics/quality.py` | `test_pareto_ranks_and_accumulates`; E2E #12 | Ranking and cumulative values exact on fixture | VERIFIED | |
| R-25 | Trace by machine, batch, shift | Group-by and filtered root cause | `analytics/quality.py`, `analytics_api.py` | Simulation with injected M-02 fault; E2E #13 | M-02 is the only significant factor (49.5% vs 10.6%, OR 8.07, q≈0) | VERIFIED | Fault is simulated |
| R-26 | Correct the root cause | Fisher exact + BH correction, correlation note, KB hypotheses, corrective actions | `analytics/spc.py`, `quality.py` | `test_association_finds_fault_and_ignores_noise`, `test_small_groups_are_not_tested`; E2E #13 | Fault found, noise not; every output carries the correlation note; action recorded | VERIFIED | |
| R-27 | Trend visibility | Daily flagged rate, FPY, p-chart | `quality.trend` | `test_p_chart_*`; Overview page | Trend rendered with control limit | VERIFIED | |
| R-28 | Early warning | p-chart spike alerts, association alerts, idempotent | `quality.refresh_alerts` | `test_p_chart_flags_spike_only`, `test_p_chart_needs_baseline` | Spike raises alert; stable data does not | VERIFIED | |
| R-29 | Consistency | Deterministic policy decision | `line/decision.py` | `test_decision_is_deterministic_and_policy_driven` | Same input gives same decision | VERIFIED | |
| R-30 | Less manual inspection | Auto accept/reject with review band; review share KPI | `decision.py`, `quality.summarise` | `eval_decision.json` | Good parts: 90.6% auto-accepted. Defective: 24.3% auto-rejected, 64.6% to review | VERIFIED (measured) | Review share is high by policy choice |
| R-31 | Lower error rate | Measured FNR/FPR on holdout | `ml/`, `scripts/evaluate_decision.py` | Decision-level eval on 740 test images | 0 good parts auto-rejected; 9.4% good to review; 11.1% defective escaped | VERIFIED (measured) | No human baseline exists, so no reduction is claimed |
| R-32 | Retrain for other products and defects | Create product → samples → train → gate → promote, all through the API | `api/production.py`, `api/learning.py` | Onboarding run (`e2e_onboarding.json`) | New product promoted; 9/9 good accepted, 3/3 defective flagged on its test images | PARTIAL | New defect **classes** need YOLO retraining with masks (`ml/train_yolo_seg.py`), not automated |
| R-33 | Preserve rule engine | Legal Metrology code, routes, UI kept | `app/api/inspections.py`, `rules.py`, `app/data/rules.json` | Original tests; E2E #18; MD5 of `rules.json` | Rule tests pass; E2E processed a label; `rules.json` MD5 `f30a15e4…` identical to original | VERIFIED | |
| R-34 | Reports | PDF per inspection and per batch | `pdf_report_service.py` | E2E #11 | Both are valid `%PDF` | VERIFIED | |
| R-35 | Security | bcrypt with legacy upgrade, JWT, RBAC, required secret in production, upload limits, CORS allow-list, live-source path confinement, stored files only through an authenticated route (no public `/storage`) | `core/security.py`, `api/auth.py`, `core/config.py`, `storage_service.py` | `tests/test_security.py` (19 cases); container start without secret | Anonymous → 401, wrong role → 403, `.exe` → 415, oversize → 413, `/etc/passwd` source → 403, evil origin not allowed, database/model files and `../` paths refused by `/files`; production start without `SECRET_KEY` refused | VERIFIED | No external penetration test |

## The 18 end-to-end workflows of the brief

Run with `backend/scripts/e2e_workflows.py` against a live backend (DEMO_MODE, supervisor account) using held-out MVTec test images. Each workflow is PASS only if every assertion held. Full evidence is in `e2e_workflows.json`.

| # | Workflow | Result | Key evidence | Disclosed limitation |
|---|---|---|---|---|
| 1 | Upload an image and detect defects | PASS | Scratched metal_nut → detections + non-ACCEPT; good metal_nut → ACCEPT; rows persisted | |
| 2 | Inspect with a live camera | PASS | JPEG frames over the browser WebSocket protocol; 2 units seen, 2 inspected | No physical webcam in headless run |
| 3 | Process a video | PASS | MP4 frames sampled, defects found, labelled SAMPLED review | Video mode samples frames; the line uses the tracker |
| 4 | All defect categories | PASS | All 5 classes have test recall > 0; each produced through the live API on a real test image | |
| 5 | Unseen abnormalities | PASS | Withheld kind metal_nut/flip flagged; heatmap stored; unknown recall 0.918 reported | |
| 6 | Segment defective regions | PASS | Detections carry masks; mask mAP50 0.585 | |
| 7 | Calibrated dimensional inspection | PASS | 100 and 50 mm within 1%; 45 mm spec fails as expected; assumptions printed | Synthetic image |
| 8 | Golden references | PASS | Stored, activated, used; with it active, 6/6 good test parts accepted | Adds no recall on MVTec |
| 9 | Log results | PASS | Unit has decision, model versions, time, latency, machine/batch/shift | |
| 10 | Categorise automatically | PASS | Class and severity on every detection | |
| 11 | Reports | PASS | Inspection PDF and batch PDF | |
| 12 | Manufacturing analytics | PASS | KPIs, Pareto, trend | |
| 13 | Investigate by batch and machine | PASS | M-02 first; on the simulated line alone, the only significant factor; corrective action saved | Simulated fault |
| 14 | Reviewer feedback | PASS | Detection feedback, review queue, unit label → training sample, final decision | |
| 15 | Retraining and evaluation | PASS | Samples → dataset v → training → holdout metrics → gate → promote → rollback | |
| 16 | Edge deployment configuration | PASS | ONNX Runtime CPU; benchmarks on named devices; offline container run | No edge board |
| 17 | Accept/reject and rejection interface | PASS | 12/12 units; 2 ACCEPT, 8 REVIEW, 2 REJECT; reject fired only for REJECT | Simulated actuator |
| 18 | Original Rule-Based Engine | PASS | Legal inspection processed with rule results; rule tests pass; `rules.json` unchanged | |

## Defects found and fixed during verification

Each was found by running the system, not by reading code. Each has a regression test or an E2E assertion.

1. **Tracker double-counted parts.** A dark part on a dark belt split into two blobs: 49 units for 43 parts. Fragments are now merged before tracking, giving 43/43 (`test_split_silhouette_is_one_unit`).
2. **Golden reference rejected good parts.** The legacy detector with a golden image flagged 60% of good val parts. Classical findings now need anomaly-map support; the cutoff was chosen on val.
3. **Simulated conveyor ran empty.** Sample folders with `good/` and `defect/` subfolders yielded no images (`test_conveyor_samples_include_subfolders`).
4. **Analytics ignored parts awaiting review.** Root cause found 0 of 57 defective parts when anomaly-only findings went to review (`test_review_units_count_as_flagged_until_a_reviewer_accepts`).
5. **Deployed anomaly thresholds differed from the reported ones.** The evaluation now writes the val-chosen threshold into each saved model; engine decisions match the report image for image.
6. **Model Performance page crashed.** A device object was rendered as text. Fixed and checked in headless Chrome.
7. **Measurement read every side about 1.5 px too long.** A fixed low threshold on a blurred edge. Otsu now puts the edge at the midpoint.
8. **Pre-existing bug in the original code:** `cv2.setLogLevel` does not exist in pip OpenCV, so loading any trained ONNX model crashed. Three original tests failed because of it.
9. **Login import error, demo-seed syntax error, video `outcome` key:** found by the first test run.
10. **Root-cause API lacked the line, machine, batch and shift filters** that drill-down needs.
11. **Every stored file was public.** `/storage` served part images, reports and, in the Docker layout, the SQLite database with password hashes, without login. This was found while writing the final report. The mount was removed and replaced by an authenticated `/api/v1/files` route. The frontend loads images with the auth header (`ProtectedImg`) and keeps tokens out of URLs.

## Frontend verification

A headless Chrome walkthrough (DevTools protocol, real login form) loaded all 16 sections:
- Signed-out access redirects to `/login`.
- Login stores a token and lands on `/overview`.
- **16/16 sections** load with no uncaught exception, no console error and no failed API call.
- Screenshots were reviewed for Overview, Root-Cause and Model Performance.

`next build` succeeds with 27 routes.
