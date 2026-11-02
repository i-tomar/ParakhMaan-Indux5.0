# 01 — Problem Statement Requirements (PS-12)

> Source of truth for what ParakhMaan must do. Status of each item lives in
> `02_PARAKHMAAN_EXISTING_PROJECT_AUDIT.md` (start state), `03_COMPLETE_IMPLEMENTATION_ROADMAP.md`
> (plan) and `FINAL_IMPLEMENTATION_REPORT.md` (tested end state).

## 1. Official problem statement (verbatim)

**Problem Statement 12: AI & Computer-Vision Based Surface & Product Defect Inspection**
Domain tags on the hackathon listing: *Software + AI/ML + Deep Learning + Computer Vision + Edge Computing + Data Analytics*. Theme: *AI Computer Vision & Image Processing Systems*.

> "The AI-Based Visual Inspection system automatically examines products and surfaces to find defects that are difficult to catch with the human eye. Deep-learning and computer-vision models identify scratches, cracks, dents, discolouration, and dimensional anomalies from camera images or video in real time, and improve further as more defect samples are collected. Edge computing runs the AI models close to the production line so inspection is fast enough for a moving conveyor, and every detected defect is logged and categorised automatically. Analytics on this data reveal which defect types occur most frequently, helping teams trace and correct the root cause in the process. Overall, the system improves product quality and consistency, reduces manual inspection effort and error rate, and can be retrained for different products and defect types."

The text was checked against the hackathon screenshot supplied with the brief (`WhatsApp Image 2026-10-31 at 03.09.24.jpeg`); they match.

### Sentence map

| # | Sentence (abridged) | Requirement IDs |
|---|---|---|
| S1 | Automatically examines products and surfaces; finds defects hard to catch by eye | R-01, R-02, R-03 |
| S2 | DL + CV identify scratches, cracks, dents, discolouration, dimensional anomalies, from images or video, in real time; improve as samples are collected | R-04…R-12, R-20…R-23 |
| S3 | Edge computing, close to the line, fast enough for a moving conveyor; every defect logged and categorised automatically | R-13…R-19 |
| S4 | Analytics show most frequent defect types; helps trace and correct root cause | R-24…R-28 |
| S5 | Improves quality/consistency, reduces manual effort and error rate; retrainable for different products and defect types | R-29…R-32 |

## 2. Problem understanding and industry context

Manual end-of-line inspection is slow, inconsistent between inspectors and shifts, and tires quickly. Three operational problems sit behind the statement:

1. **Escapes and over-rejection.** Missed defects reach customers; cautious inspectors scrap good parts. Both have a cost, so the system must report *both* miss rate and false-reject rate, not "accuracy".
2. **Defect data is scarce and unbalanced.** A healthy line produces few defects, and new defect kinds appear without warning. A purely supervised detector cannot be the only model: it needs an unsupervised partner trained on good parts only.
3. **Inspection results rarely reach process engineers.** A rejected part fixes nothing. The value comes from tying each defect to machine, batch, shift and time, so the process can be corrected.

### What separates an advanced build from an ordinary YOLO demo

| Ordinary | Required here |
|---|---|
| One detector, one dataset, one uploaded image | Supervised model **and** anomaly model **and** deterministic geometry, each measured separately |
| "Accuracy 98%" on a random split | Grouped splits, per-class P/R/F1, miss rate and false-reject rate on held-out real images |
| Sampling every Nth frame | Every frame tracked; each physical unit gets exactly one decision |
| Boxes on a screenshot | Logged unit record → decision → reject signal → analytics |
| "Retrainable" as a sentence | Working register → train → validate → promote → roll back loop with a gate |
| Root-cause list of generic tips | Statistical association per machine/batch/shift, labelled as correlation |

## 3. Functional requirements

- **FR-1 Inspect** images, uploaded video, and a live camera stream through one pipeline.
- **FR-2 Detect, classify, localise and segment** the five named defect classes, several per unit.
- **FR-3 Flag unknown anomalies** the classifier was never trained on.
- **FR-4 Measure** length, width, diameter, shape deviation against per-product tolerance.
- **FR-5 Compare** against golden references.
- **FR-6 Decide** ACCEPT / REJECT / MANUAL_REVIEW, and emit a rejection signal.
- **FR-7 Track** each unit across frames so it is decided once.
- **FR-8 Log** every inspection and defect persistently with batch, machine, line, shift, model version.
- **FR-9 Analyse** frequency, trends, machine/batch/shift splits, rejection rate, spikes, root-cause evidence.
- **FR-10 Learn**: inspector feedback → dataset version → retrain → gate → controlled deploy → rollback.
- **FR-11 Onboard** a new product or defect type without code changes.
- **FR-12 Report** inspection and batch results as PDF.
- **FR-13 Preserve** the Legal Metrology rule engine as a separate optional module.

## 4. Non-functional requirements

| ID | Attribute | Target | How measured |
|---|---|---|---|
| NFR-1 | Latency | Full-frame AI inference ≤ 150 ms on the reference CPU, reported p50/p95 | `ml/benchmark_inference.py` |
| NFR-2 | Line rate | Tracker keeps up with a 30 fps stream; zero units missed in the simulated conveyor at the stated belt rate | Conveyor E2E test |
| NFR-3 | Honesty of telemetry | Latency, FPS, memory and device values come from live measurement | Code review + `/edge/status` |
| NFR-4 | Reliability | Model load failure degrades to classical CV and is shown as such, never silently | Test with a missing model |
| NFR-5 | Security | No default secrets, hashed passwords, RBAC on mutating routes, upload limits | Tests + audit |
| NFR-6 | Reproducibility | Clean-environment commands + Docker Compose | Docker build run |
| NFR-7 | Traceability | Every detection records its model version | Schema + test |
| NFR-8 | Isolation | Legal Metrology tests pass unchanged in behaviour | `pytest tests/test_rule_engine.py` etc. |

## 5. AI and ML requirements

- **AI-1** Supervised multi-class detector/segmenter trained on real defect images.
- **AI-2** Unsupervised anomaly model trained on good parts only, per product, with pixel heatmaps.
- **AI-3** Calibrated decision thresholds chosen on a validation split, never on the test split.
- **AI-4** Severity derived from measured size/location, documented and deterministic.
- **AI-5** ONNX export and runtime without PyTorch.
- **AI-6** Metrics: P, R, F1, mAP@50, mAP@50-95, per-class, FPR, FNR, latency, FPS, mask IoU/F1, AUROC, AUPRO or pixel AUROC.
- **AI-7** Model versioning and an auditable registry.

## 6. Computer-vision requirements

- **CV-1** Preprocessing: resizing, optional perspective rectification, exposure and blur gate.
- **CV-2** Product segmentation from background.
- **CV-3** Golden alignment and difference.
- **CV-4** Calibration: checkerboard (intrinsics/planar homography) or known-reference-length px/mm.
- **CV-5** Measurement: min-area rectangle, circle fit, contour deviation (Hausdorff-style), notch detection.
- **CV-6** Visual output: original, processed, boxes, masks, anomaly heatmap.

## 7. Real-time inspection requirements

- **RT-1** Live camera frames streamed continuously (not single snapshots).
- **RT-2** Bounded queue with drop-oldest policy; dropped frames counted and displayed.
- **RT-3** Every received frame passes the lightweight unit tracker; heavy inference runs once per unit at the best frame.
- **RT-4** Stable unit IDs; a unit crossing the frame produces one record.
- **RT-5** Clear distinction in the UI between *continuous tracked mode* and *sampled video review*.

## 8. Edge-computing requirements

- **EDGE-1** All inference runs locally, with no cloud dependency.
- **EDGE-2** Runtime reports device, execution provider, loaded models, process memory, p50/p95 latency, FPS, throughput.
- **EDGE-3** A container or install path for edge hardware. Only hardware actually tested is claimed; Jetson/Raspberry Pi are listed **unverified** unless run.

## 9. Production-line automation requirements

- **LINE-1** Decision rule engine with configurable thresholds per product.
- **LINE-2** Reject actuator interface with simulated, serial (Arduino/ESP32) and webhook back ends.
- **LINE-3** Reject delay computed from belt speed and sensor-to-diverter distance.
- **LINE-4** Simulation labelled as simulation everywhere it appears.

## 10. Manufacturing analytics requirements

- **AN-1** Pareto by defect type.
- **AN-2** Split by machine, line, batch, shift, product.
- **AN-3** Defect-rate and first-pass-yield trend.
- **AN-4** Rejection rate.
- **AN-5** Spike alerts (p-chart 3σ control limits).
- **AN-6** Association tests (e.g. Fisher exact or chi-square with effect size), labelled *correlation, not proven cause*.
- **AN-7** Spatial hotspot on the part.

## 11. Continuous-learning requirements

- **CL-1** Inspector confirm / reject / relabel on each detection.
- **CL-2** Good-sample and defective-sample collection with annotation records.
- **CL-3** Immutable, hashed dataset versions.
- **CL-4** Training jobs launched from the UI/API, status visible.
- **CL-5** Independent validation on a fixed holdout that training never sees.
- **CL-6** Side-by-side candidate vs production comparison.
- **CL-7** Promotion gate: a candidate that does not meet the criteria cannot be promoted.
- **CL-8** One-click rollback.

## 12. Inputs and outputs

| Inputs | Outputs |
|---|---|
| Image (JPG/PNG), video (MP4/AVI/MOV), browser camera, RTSP/USB camera, video file as a stream | Unit record with decision and reasons |
| Product profile: dimensions, tolerance, thresholds, golden images | Defect rows: class, severity, confidence, box, mask, area, length, model version |
| Calibration images or reference length | px/mm with stated assumptions and residual error |
| Context: batch, machine, line, shift | Overlay, heatmap, PDF report |
| Inspector feedback | Dataset version, model candidate, comparison report |

## 13. Functional workflows

```
A. Inline     Camera ▸ bounded queue ▸ tracker ▸ best frame ▸ AI + geometry ▸ decision ▸ log ▸ reject signal ▸ analytics
B. Offline    Upload image/video ▸ same inference ▸ inspection record ▸ review ▸ report
C. New part   Create product ▸ upload good images ▸ fit anomaly model ▸ validate ▸ activate
D. Learning   Review queue ▸ labels ▸ dataset version ▸ train ▸ holdout eval ▸ gate ▸ promote or reject ▸ rollback if needed
E. Root cause Spike alert ▸ drill into machine/batch/shift ▸ association evidence ▸ corrective note
F. Legal      Legal Metrology module, separate navigation, unchanged rule engine
```

## 14. Technical acceptance criteria (summary)

A requirement is done only if its test ran and its result is recorded. Numeric model targets are **goals, not claims**; `FINAL_IMPLEMENTATION_REPORT.md` reports the measured values, whichever way they land.

| Area | Goal |
|---|---|
| Anomaly model on MVTec AD held-out | Mean image AUROC ≥ 0.90 |
| Supervised model on held-out real images | mAP@50 reported per class; each of the 5 classes present in test evaluated |
| Unknown defects | Defect types withheld from supervised training are still flagged above threshold; recall reported |
| Dimensional | Mean error on synthetic known-geometry set ≤ 1% ; every result prints its calibration assumptions |
| Conveyor simulation | Units seen = units logged = units decided, no duplicate IDs |
| Promotion gate | A deliberately worse candidate is refused in an automated test |
| Rollback | Production pointer returns to the earlier version in an automated test |
| Rule engine | Original tests pass; `rules.json` unchanged |

## 15. Expected final product capabilities

Sixteen sections: Overview, Live Inspection, Defect Detection, Dimensional Inspection, Golden References, Line Monitoring, Product & Batch Tracking, History, Defect Analytics, Root-Cause, Model Performance, Dataset & Feedback, Model Versions, Reports, Settings, Rule Engine.

## 16. Innovation opportunities pursued

1. **Three independent evidences on one unit**: learned class, unsupervised anomaly, physical geometry. Disagreement routes to a human instead of a guess.
2. **New product in minutes** using good images only.
3. **Withheld-class test** showing what the system does on defects it never saw.
4. **Statistical root-cause drill-down** that keeps correlation and cause apart.
5. **Traceable promotion gate**, so model upgrades can be audited.

## 17. Likely judging criteria and how to demonstrate them

| Criterion | Demonstration |
|---|---|
| Technical depth | Show the live pipeline and the per-model evaluation report |
| Works end to end | Conveyor simulation producing unit logs and analytics in front of judges |
| Real-world readiness | Edge telemetry, reject interface, calibration assumptions |
| Honesty | Show the limitations list and worst-performing classes |
| Extensibility | Onboard a new product live |

---

## 18. Requirement Traceability Matrix

> **Final status (2026-11-02):** 30 VERIFIED, 5 PARTIAL (R-08, R-12, R-15, R-19, R-32), 0 NOT VERIFIED. Implementation, tests, results and limitations for every row: [docs/REQUIREMENT_TRACEABILITY.md](docs/REQUIREMENT_TRACEABILITY.md).

Priority: P0 must have, P1 should have, P2 nice to have.

| ID | Official requirement | Interpretation | Required implementation | Expected output | Acceptance criteria | Pri | Test method |
|---|---|---|---|---|---|---|---|
| R-01 | Automatically examines products | No operator action per unit | Inline pipeline triggered by unit presence | Unit record without manual step | Conveyor test logs all units with no input | P0 | E2E conveyor |
| R-02 | …and surfaces | Close-up textures and whole objects | Object and texture profiles | Works on both | Eval covers object and texture categories | P0 | Per-category eval |
| R-03 | Defects hard to catch by eye | Small/subtle defects | High-res tiling or patch-level anomaly map | Pixel heatmap | Small-defect recall reported by size bucket | P1 | Size-bucket eval |
| R-04 | Identify scratches | Class SCRATCH | Supervised + CV | Class label | Per-class P/R on real test | P0 | Model eval |
| R-05 | Identify cracks | Class CRACK | Supervised + CV | Class label | Per-class P/R on real test | P0 | Model eval |
| R-06 | Identify dents | Class DENT | Supervised (bent/poke/dent-like real labels) + CV | Class label | Per-class P/R; label mapping documented | P0 | Model eval |
| R-07 | Identify discolouration | Class DISCOLOURATION | Supervised + CIELAB ΔE | Class label, ΔE | Per-class P/R on real test | P0 | Model eval |
| R-08 | Identify dimensional anomalies | Real measurement | Calibration + metrology + tolerance | mm values, pass/fail | Synthetic known-geometry error ≤ 1%; assumptions printed | P0 | Geometry test |
| R-09 | Deep-learning models | Trained neural models in use | YOLO-seg + feature-based anomaly model | ONNX artefacts | Models load and infer in API | P0 | Integration |
| R-10 | Computer-vision models | Classical CV retained where better | OpenCV pipeline, geometry, alignment | Fallback + measurement | Tests pass | P0 | Unit |
| R-11 | From camera images or video | Three sources | Upload, video, live stream | Same record schema | Each source produces a record | P0 | E2E ×3 |
| R-12 | In real time | Continuous, not sampled | Frame loop with bounded queue and tracker | Live FPS/latency | Measured FPS ≥ source rate for tracker; inference p95 reported | P0 | Benchmark |
| R-13 | Edge computing runs AI models | Local inference | ONNX Runtime on the device | `/edge/status` | Works with network disabled | P0 | Offline run |
| R-14 | Close to the production line | Deployable at the line | Docker image, camera input | Container | Compose up + health OK | P1 | Docker |
| R-15 | Fast enough for a moving conveyor | Latency budget vs belt speed | Budget calculator from belt speed, pitch | Budget pass/fail | Simulated conveyor: no missed units at stated rate | P0 | E2E conveyor |
| R-16 | Every detected defect logged | Persistent rows | `defect_detections` + `production_units` | DB rows | Detected count = stored count | P0 | Integration |
| R-17 | Categorised automatically | Class set with no human step | Class + severity from pipeline | Class/severity on each row | No row lacks a class | P0 | Integration |
| R-18 | Logged with context | Traceability | Batch/machine/line/shift/model version fields | Filterable log | All fields populated in conveyor run | P0 | Integration |
| R-19 | Decision at the line | Accept/reject/manual review + signal | Decision engine + actuator | Reject event | Reject fires only for REJECT units, with correct timing | P0 | Unit + E2E |
| R-20 | Improve further as samples collected | Loop exists and helps | Feedback → dataset → retrain | Candidate metrics | Candidate from added samples evaluated against production | P0 | Learning E2E |
| R-21 | Sample collection | Good and bad samples stored | Dataset service | Dataset version | Hash stable; rows counted | P0 | Unit |
| R-22 | Independent validation | Fixed holdout | Holdout manifest | Compare report | Holdout never in training set (asserted) | P0 | Unit |
| R-23 | Safe improvement | Gate and rollback | Registry + gate | Promote/refuse | Worse model refused; rollback works | P0 | Unit + API |
| R-24 | Reveal most frequent types | Pareto | Analytics API + UI | Ranked list, cumulative % | Matches hand count on fixture | P0 | Unit |
| R-25 | Helping teams trace | Machine/batch/shift split | Group-by APIs + drill-down | Tables/charts | Injected machine fault found | P0 | E2E analytics |
| R-26 | Correct the root cause | Evidence + action tracking | Association tests, KB, corrective notes | Evidence list | Output labelled as correlation | P0 | Unit |
| R-27 | Trend visibility | Time series | Defect rate, FPY | Trend chart | Tests on fixture | P1 | Unit |
| R-28 | Early warning | Spike alerts | p-chart | Alert rows | Injected spike raises alert; stable data does not | P1 | Unit |
| R-29 | Improves quality and consistency | Same rule every unit | Deterministic decision from model output | Repeatable decision | Same input ⇒ same decision | P0 | Unit |
| R-30 | Reduces manual inspection effort | Fewer units for humans | Auto-accept/reject with review band | Review share KPI | Review share measured from data | P1 | Analytics |
| R-31 | Reduces error rate | Measured FNR/FPR | Evaluation + feedback precision | Rates reported | Measured on holdout, not assumed. No human baseline exists, so no reduction % is claimed | P0 | Model eval |
| R-32 | Retrained for different products and defect types | No-code onboarding | Product profile, anomaly fit, class extension | Active product model | New product onboarded via API and inferring | P0 | Onboarding E2E |
| R-33 | (Brief) Preserve rule engine | Separate module | Keep services, routes, UI | Legal flow works | Original tests pass; rules file identical | P0 | Regression |
| R-34 | (Brief) Reports | PDF | Report service | PDF per inspection and batch | Valid PDF generated | P1 | Integration |
| R-35 | (Brief) Security | Hardening | bcrypt, env secrets, RBAC | Protected routes | Unauthenticated writes return 401 | P0 | Tests |
