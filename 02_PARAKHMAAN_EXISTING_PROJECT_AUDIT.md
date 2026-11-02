# 02 — ParakhMaan Existing Project Audit

Audit of the code as received (`ParakhMaan-Indux5.0-main`, 129 files, 16 MB), from reading the source and running it.
**Evidence labels:** VERIFIED = executed here · READ = confirmed in source, not executed · CLAIMED = stated in documents only.

## 1. Summary

- ParakhMaan was a Legal Metrology compliance platform (SIH26034) with a defect-inspection mode added later.
- **Reusable foundation for PS-12: about 35–40%, not the assumed 60%.** See §17 for the calculation.
- The Legal Metrology module is complete and well separated. It is preserved.
- The defect mode is a working classical-CV prototype. Its "AI" model is weak and its evaluation is synthetic only.
- Missing entirely: production context, unit tracking, real calibrated measurement, continuous pipeline, reject interface, anomaly detection, segmentation, model registry, retraining.
- Security was not fit for a shared deployment (see §15).

## 2. Existing architecture

```
Next.js 16 frontend ── REST ──▶ FastAPI (single process)
                                 ├ Legal: image quality ▸ OCR ▸ extraction ▸ LLM(optional) ▸ rule engine ▸ PDF
                                 ├ Defects: OpenCV heuristics + optional ONNX via cv2.dnn ▸ log ▸ PDF
                                 └ SQLite (SQLAlchemy), local file storage
```

## 3. Technologies and dependencies

Backend: FastAPI, Pydantic v2, SQLAlchemy 2, SQLite, OpenCV headless, ReportLab, PyJWT, pypdf, httpx. `passlib`, `bcrypt` listed but **unused**. Python 3.13 in Docker.
Frontend: Next.js 16.3.4, React 19, Tailwind 4, lucide-react. No chart library; charts are hand-built.
Documentation errors: README says Tailwind 3 (actual 4), scikit-learn for RAG (not a dependency; RAG is keyword-based over pypdf text), 17 and 19 tests (actual count in §14), `pdf_service.py` (actual `pdf_report_service.py`), `test_api.py` (actual `test_api_endpoints.py`), and an Ollama container in compose (not defined).

## 4. Backend modules

| File | Lines | Purpose | Status |
|---|---|---|---|
| `api/inspections.py` | 545 | Legal inspection flow | KEEP |
| `api/defects.py` | 803 | Defect flow | MODIFY (engine, units) |
| `api/auth.py` | 101 | JWT login | MODIFY (security) |
| `api/dashboard.py`, `reports.py`, `reviews.py`, `tools.py`, `demo.py`, `llm.py`, `rag.py` | various | Legal module | KEEP |
| `services/rule_engine.py` | 670 | Deterministic compliance | KEEP |
| `services/mpe_calculator.py`, `pdp_calculator.py`, `schedule_checker.py`, `declaration_service.py`, `classifier_service.py` | various | Legal logic | KEEP |
| `services/ocr_service.py` | 258 | Windows OCR → Tesseract → MSER fallback | KEEP; see §13 |
| `services/llm_service.py`, `rag_service.py` | | Optional Ollama; keyword retrieval | KEEP |
| `services/defect_detection_service.py` | 903 | OpenCV + cv2.dnn | IMPROVE: retain as fallback stream |
| `services/defect_analytics_service.py` | 259 | Per-inspection analytics | IMPROVE |
| `services/heatmap_service.py` | 161 | Overlays | KEEP |
| `services/image_quality.py` | 142 | Blur, glare, blank gates | KEEP (label-oriented; not valid as a surface quality gate, already noted in code) |
| `services/pdf_report_service.py` | 426 | Reports | IMPROVE |
| `services/storage_service.py` | 53 | Local files | MODIFY (validation) |

## 5. Frontend modules

| Route | Status | Note |
|---|---|---|
| `/dashboard`, `/inspections`, `/inspections/new`, `/inspections/[id]`, `/rules` | KEEP | Legal module |
| `/defects`, `/defects/[id]`, `/defects/analytics` | IMPROVE | Hand-built, usable |
| `Navbar.tsx` | REMOVE | Replaced with a sidebar for 16 sections; Ask Rule Book moved to the Rule Engine page |
| `CameraCaptureModal`, `DefectOverlay`, `DefectTable`, `DefectCharts`, `AuditTimeline`, `ImageQualityCard`, `EvidenceViewer`, `ComplianceMatrix`, `ReviewModal` | KEEP | |
| Login | ADD | None existed, though the backend had `/auth/login` |

Design language: Notion-derived tokens in `DESIGN.md` and `globals.css`. Kept.

## 6. Existing AI models

`backend/storage/models/best.onnx` (22 MB, 4 classes: scratch, crack, dent, discolouration).
- No training script, dataset, or provenance in the repository. Its origin cannot be established.
- Stored evaluation on the repo's synthetic benchmark (IoU 0.5): **mAP@50 0.254; recall 0.282; crack recall 0.000; dent recall 0.000**.
- Assessment: **REPLACE.**

## 7. Existing CV pipelines (READ, then VERIFIED by tests in §14)

- Scratch/crack: morphological line extraction, separated by tortuosity.
- Dent: shading deviation from a blurred background.
- Discolouration: CIELAB chroma/ΔE deviation.
- Dimensional: ratio comparison to a golden contour, or convexity notches. **No millimetres, no calibration.**
- Golden: ORB + homography alignment and a min/max envelope difference.
- Live: repeated stateless single-frame requests, nothing persisted. Video: fixed-rate sampling.

## 8. Existing model evaluation results

From `backend/storage/reports/defect_model_evaluation.json` (synthetic, 200 images, seed 2026, IoU 0.5):

| Engine | mAP@50 | Precision | Recall | Image acc. | Latency |
|---|---|---|---|---|---|
| ONNX | 0.254 | 0.672 | 0.282 | 0.705 | 18.8 ms |
| OpenCV | 0.605 | 0.688 | 0.679 | 1.000 | 164.9 ms |
| Hybrid | 0.604 | 0.634 | 0.682 | 1.000 | 184.6 ms |

The benchmark is generated by the same author-written primitives as the detector's assumptions, so image accuracy 1.000 is not evidence of real-world performance. **No real-image evaluation existed.** OpenCV dent F1 is 0.109 even here.

## 9. Existing datasets

None in the repository. Four demo package JPEGs and generated synthetic metal surfaces. Rule data: `SIH26034_RULES.json` is byte-identical to `backend/app/data/rules.json` (SHA-256 `04e520c6…`), 50 rules.

## 10. Database architecture

SQLite with 10 tables: `users`, `inspections`, `images`, `declarations`, `rules`, `compliance_results`, `reviewer_actions`, `audit_events`, `defect_detections`. The shipped `legal_metrology.db` holds 18 legal and 16 defect inspections, 65 detections, 1 user.
Gaps: `brand_name` was repurposed as "batch"; no machine, line, shift, product, batch, unit, model version, or reject tables. Migrations: small column back-fill helper only.

## 11. APIs

About 45 routes. Legal: `/inspections*`, `/tools/*`, `/rag/ask`, `/llm/status`, `/dashboard/summary`, `/demo/seed`. Defects: `/defects/*` (status, inspections, reference, analyze, capture, video, feedback, overlay, report, finalize, analytics, log, seed).

## 12. Analytics and reporting

Exists: type frequency, severity, trend, 3×3 hotspot, per-product rate, keyword root-cause hints, reviewer precision estimate, PDFs.
Missing: machine/batch/shift, FPY, control limits, statistical association, corrective-action tracking. Root-cause text was a fixed knowledge base, presented as "likely causes" with no statistical test.

## 13. Rule-based engine — PRESERVE

- 670-line deterministic engine, 50 rules, MPE, Fifth Schedule, Second Schedule, PDP. Independent of the defect flow. Tests VERIFIED in §14.
- Caveat that predates this work: `ocr_service.py` loads ground-truth sidecar metadata for demo images, so demo extraction does not prove OCR. On macOS/Linux without Tesseract the OCR engine falls back to `OPENCV_MSER_VISION`, which localises text but cannot read it. **The legal module therefore needs Windows OCR or Tesseract for real images.** Documented, not changed.

## 14. Deployment and testing

Docker: compose defines backend and frontend, **hardcodes `SECRET_KEY`**, and README refers to a nonexistent `lm-ollama` service.
**VERIFIED defect:** `frontend/package-lock.json` was out of sync, so `npm ci` fails (`Missing: @emnapi/runtime@1.11.3 from lock file`). The frontend Dockerfile uses `npm ci`, so **the shipped Docker build could not succeed.** Repaired with `npm install`.

Baseline results (from the untouched backup):

| Check | Result |
|---|---|
| `pytest tests` | 40 passed, 3 failed (original code, Python 3.12, opencv-python-headless 4.14). All 3 failures are the same bug: `cv2.setLogLevel` does not exist in the pip OpenCV wheels, so loading any trained ONNX model raised `AttributeError`, meaning the supervised model path never worked. Fixed by using `cv2.utils.logging`. After the upgrade: 101 passed, 0 failed (2026-11-02). |
| `next build` (after lock repair) | PASS, 10 routes |
| `eslint src` | 59 errors, 46 warnings (mostly `no-explicit-any`) |

## 15. Requirement comparison

| Requirement | Existing Implementation | Actual Status | Gap | Required Change | Priority |
|---|---|---|---|---|---|
| R-01 Automatic inspection | Manual upload per image | Partial | No unattended flow | Tracked pipeline | ADD P0 |
| R-02 Products and surfaces | Heuristics tuned on synthetic metal | Weak | Unproven on real objects | Multi-product models | ADD P0 |
| R-03 Hard-to-see defects | Heuristics only | Weak | No fine-scale AI | Patch-level anomaly map | ADD P0 |
| R-04 Scratch | OpenCV, weak ONNX | Works on synthetic | No real validation | Train + evaluate | IMPROVE P0 |
| R-05 Crack | OpenCV; ONNX recall 0 | Works on synthetic | Same | Train + evaluate | IMPROVE P0 |
| R-06 Dent | OpenCV F1 0.109; ONNX recall 0 | Not working | Effectively absent | Train + evaluate | MODIFY P0 |
| R-07 Discolouration | CIELAB | Partial | Real validation | Train + evaluate | IMPROVE P0 |
| R-08 Dimensional | Ratios to golden, notches | Partial | No mm, calibration, tolerance | Metrology service | ADD P0 |
| R-09 Deep learning | Unknown ONNX | Poor | No provenance | Replace | MODIFY P0 |
| R-10 Computer vision | OpenCV | Working | Fallback role | Keep | KEEP |
| R-11 Images/video | Upload, snapshot, sampled video | Working | Sampling only | Shared unit path | IMPROVE P0 |
| R-12 Real time | Stateless loop | Partial | No tracking, no queue | Pipeline | MODIFY P0 |
| R-13 Edge inference | cv2.dnn local | Partial | No telemetry | ONNX Runtime + status | MODIFY P0 |
| R-14 Near the line | Docker broken | Broken | Build failed | Fix | MODIFY P1 |
| R-15 Conveyor speed | None | Missing | No budget | Budget + simulation | ADD P0 |
| R-16 Defects logged | `defect_detections` | Working | Unit identity missing | Unit table | IMPROVE P0 |
| R-17 Categorised | Types assigned | Working | Fine | Add unknown class | IMPROVE |
| R-18 Context | `brand_name` as batch | Missing | No machine/shift | Schema | ADD P0 |
| R-19 Decision + signal | Outcome label only | Partial | No actuator | Decision + actuator | ADD P0 |
| R-20…23 Learning | Crops + manifest | Partial | No dataset, retrain, gate | Learning service | ADD P0 |
| R-24 Pareto | Type counts | Working | Fine | Reuse | KEEP |
| R-25 Tracing | Product only | Missing | Machine/batch/shift | Analytics | ADD P0 |
| R-26 Root cause | Static KB | Partial | No statistics | Association tests | MODIFY P0 |
| R-27 Trend | Daily counts | Partial | No rate/yield | Add | IMPROVE |
| R-28 Alerts | None | Missing | | p-chart | ADD P1 |
| R-29 Consistency | Deterministic rule | Working | Fine | Policy | IMPROVE |
| R-30/31 Effort, error | None | Missing | No measures | Measure | ADD |
| R-32 New products | Golden per inspection | Partial | No model per product | Onboarding | ADD P0 |
| R-33 Rule engine | Complete | Working | None | Preserve | KEEP |
| R-34 Reports | PDF per inspection | Working | No batch report | Add | IMPROVE |
| R-35 Security | See below | Unsafe | | Harden | MODIFY P0 |

### Classification

- **KEEP:** rule engine and legal services/routes/pages, OCR, audit trail, heatmap overlay, frontend tokens and components.
- **IMPROVE:** OpenCV detector (fallback), defect API, analytics service, PDF service.
- **MODIFY:** auth, config, storage, main app, API client, Docker.
- **ADD:** anomaly engine, seg detector, fusion engine, metrology, realtime, line automation, analytics, learning, 13 frontend sections.
- **REMOVE:** `Navbar.tsx` from primary experience; `best.onnx` as default model; stale generated PDFs from version tracking.

### Files

Retain unchanged: `backend/app/services/{rule_engine,mpe_calculator,pdp_calculator,schedule_checker,declaration_service,classifier_service,ocr_service,llm_service,rag_service}.py`, `backend/app/data/rules.json`, `SIH26034_RULES.{json,csv}`, `SOURCE_REGISTER.csv`, both reference PDFs.
Modify: `backend/app/{main.py,core/*,api/auth.py,api/defects.py,api/demo.py,models/all_models.py}`, `backend/app/services/{storage_service,heatmap_service,pdf_report_service,defect_detection_service}.py`, `frontend/src/lib/{api,defects}.ts`, `frontend/src/app/layout.tsx`, `docker-compose.yml`, Dockerfiles, `.gitignore`.
New: see `03_COMPLETE_IMPLEMENTATION_ROADMAP.md`.

### Bugs and technical debt

| # | Issue | Evidence | Severity |
|---|---|---|---|
| 1 | Frontend review action calls `/reviews/{id}/review`; backend serves `/inspections/{id}/review` | `lib/api.ts:195`, `api/reviews.py` | High: legal review always 404 |
| 2 | Frontend report link `/reports/{id}/report`; backend `/inspections/{id}/report` | `lib/api.ts:204`, `api/reports.py` | High: legal PDF link 404 |
| 3 | `npm ci` broken | §14 | High |
| 4 | `DEFECT_MODEL_CLASSES` silently masked mismatch cases by env | compose | Low |
| 5 | Startup always seeds demo rows into any database | `main.py` | Medium |
| 6 | Generated PDFs and a populated DB shipped in the repo; its 35 image rows point to `C:\Users\Abhis\...` files that do not exist here | `backend/storage/reports`, `*.db` | Low |
| 7 | README claims disagree with the code | §3 | Low |

### Model performance problems

Stated in §6 and §8: no provenance, zero recall on two named classes, synthetic-only evaluation, and hybrid no better than OpenCV alone.

### Missing datasets and training requirements

Real multi-product defect images with masks, good-only images per product, a held-out test split, a training environment.

### Security issues (VERIFIED by reading; each has a test after the fix)

| Issue | Location |
|---|---|
| Passwords hashed with one fixed salt SHA-256 | `core/security.py` |
| `plain_password == hashed_password` accepted, so a stored hash works as a password | `core/security.py` |
| Any password creates a demo account for three known emails | `api/auth.py` |
| No token means default inspector, so auth is effectively off | `api/auth.py` |
| Hardcoded JWT secrets in config and compose | `core/config.py`, `docker-compose.yml` |
| `/auth/register` open, with caller-chosen role | `api/auth.py` |
| CORS `*` with credentials | `main.py` |
| Upload: no type or size check | `storage_service.py` |
| `/storage` served without auth; contains reports, part images and (in Docker) the SQLite database itself | `main.py`. **Fixed:** public mount removed; images and PDFs only via the authenticated `/api/v1/files/...` route, which refuses databases, models and paths outside storage (`test_stored_files_need_login_and_only_images_or_pdfs_are_served`) |

### Performance issues

cv2.dnn serialised behind a lock; OpenCV pipeline 165 ms; video runs the full pipeline per sampled frame; `list_defect_inspections` loads every image and detection per row (N+1).

### Integration issues

No login page despite backend auth. Analytics keyed on free-text product names. Live camera results were never logged.

## 16. Verified vs unverified

| Capability | State |
|---|---|
| Rule engine, calculators | VERIFIED by tests |
| Next build | VERIFIED |
| Defect API | VERIFIED by tests on synthetic images |
| Real-world detection | Never measured before this work |
| Ollama extraction | CLAIMED: not run, no local model |
| Windows OCR | CLAIMED: not run on macOS |
| Docker | Frontend build broken as shipped |

## 17. Reusable foundation, quantified

Weighted against the 35 requirements in the RTM, using requirement status: KEEP = 1.0, IMPROVE = 0.5, MODIFY = 0.25, ADD = 0.

- KEEP: 3 (R-10, R-24, R-33)
- IMPROVE: 9 (R-04, R-05, R-07, R-11, R-16, R-17, R-27, R-29, R-34)
- MODIFY: 8 (R-06, R-09, R-12, R-13, R-14, R-26, R-35, and one share of R-20…23)
- ADD: the rest

Score ≈ (3 + 4.5 + 2) ÷ 35 ≈ **27% of requirements**. Weighted by platform plumbing that does not appear as a requirement (auth skeleton, API, storage, PDF, audit, UI system) the estimate rises to **35–40%**. The 60% assumption does not hold for PS-12. It holds only for the Legal Metrology product.
