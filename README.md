# ParakhMaan: Industrial AI Visual Inspection

AI and computer-vision inspection of products and surfaces on a production line. It detects scratches, cracks, dents, discolouration and dimensional anomalies, plus defects it was never trained on. It measures parts in millimetres and decides accept, reject or manual review per unit. Every result is logged with batch, machine, line, shift and model version, and analytics trace defects back to where they come from.

It is built on the ParakhMaan Legal Metrology platform (SIH26034). That rule-based engine is preserved unchanged as an optional module; see [docs/LEGAL_METROLOGY_MODULE.md](docs/LEGAL_METROLOGY_MODULE.md).

> **Status.** 101 backend tests pass. All 18 end-to-end workflows of the brief pass against a running server with real images (`backend/storage/reports/e2e_workflows.json`). The model numbers below are measured on held-out MVTec AD images. Physical hardware (diverter, PLC, edge board, industrial camera) has **not** been tested; see [Known limitations](#known-limitations).

## Problem statement

Hackathon PS-12, *AI & Computer-Vision Based Surface & Product Defect Inspection*. The full official text, interpretation and a 35-row requirement matrix are in [01_PROBLEM_STATEMENT_REQUIREMENTS.md](01_PROBLEM_STATEMENT_REQUIREMENTS.md). How each requirement was met and tested is in [docs/REQUIREMENT_TRACEABILITY.md](docs/REQUIREMENT_TRACEABILITY.md).

## Main features

| Area | What it does |
|---|---|
| Defect detection | YOLO11n-seg for the 5 named classes, with pixel masks |
| Unseen defects | Per-product PatchCore-style anomaly model with a heatmap. Defects it cannot name become UNKNOWN_ANOMALY |
| Classical CV | The original OpenCV surface detector and golden-reference comparison. They count only when the anomaly model agrees |
| Dimensional | Checkerboard or reference-length calibration, mm measurements, tolerance check, contour deviation |
| Live line | Browser camera, USB/RTSP camera, video file or simulated conveyor; one ID per part, inspected once at a trigger line |
| Line decision | ACCEPT / REJECT / MANUAL_REVIEW from a per-product policy. Latency budget from belt speed. Reject signal through simulated, serial or webhook actuators |
| Logging | Every unit and detection, with batch, machine, line, shift, model version and latency |
| Analytics | KPIs, Pareto, p-chart trend with spike alerts, breakdowns by machine/shift/batch/line. Root-cause association (Fisher exact test, BH-corrected), labelled as correlation |
| Continuous learning | Reviewer labels and samples, fixed holdout, dataset versions, retraining, gate, promotion, rollback |
| Reports | PDF per inspection and per batch |
| Security | bcrypt, JWT, roles (INSPECTOR / SUPERVISOR / ADMIN), no default secrets, upload type and size limits, stored images and PDFs only through an authenticated route |
| Rule-Based Engine | Legal Metrology module, unchanged (`rules.json` byte-identical to the original) |

The frontend has 16 sections: Overview, Live Inspection, Defect Detection, Dimensional Inspection, Golden References, Line Monitoring, Products & Batches, Inspection History, Defect Analytics, Root-Cause Investigation, Reports, Model Performance, Dataset & Feedback, Model Versions, Settings and Rule-Based Engine.

## Architecture

```
 camera / video / upload / simulated conveyor
            │
            ▼
   bounded frame queue ─▶ unit tracker (one ID per part, best frame, trigger line)
            │
            ▼
   InspectionEngine (ONNX Runtime, CPU)
     ├─ YOLO11n-seg ─────────────▶ class + mask
     ├─ ResNet-18 memory bank ───▶ anomaly map ─▶ UNKNOWN_ANOMALY regions
     ├─ OpenCV + golden (corroborated by the anomaly map)
     └─ metrology (calibrated mm, tolerances)
            │
            ▼
   DecisionPolicy ─▶ ACCEPT / REJECT / MANUAL_REVIEW ─▶ actuator (simulated / serial / webhook)
            │
            ▼
   SQLite: production_units, defect_detections, reject_events, batches, machines, ...
            │
            ├─▶ analytics (Pareto, p-chart, association) ─▶ alerts, corrective actions
            └─▶ review queue ─▶ dataset versions ─▶ retrain ─▶ gate ─▶ promote / rollback
```

| Layer | Path |
|---|---|
| API (FastAPI) | `backend/app/api/` (`defects`, `production`, `metrology_api`, `analytics_api`, `live`, `learning`, `edge`, plus legacy `inspections`, `rules`, ...) |
| Inference | `backend/app/services/inference/` (`engine.py`, `anomaly_engine.py`, `seg_detector.py`) |
| Metrology | `backend/app/services/metrology/` |
| Line and real time | `backend/app/services/line/`, `backend/app/services/realtime/` |
| Analytics | `backend/app/services/analytics/` |
| Learning | `backend/app/services/learning/` |
| Training and evaluation | `ml/` (needs PyTorch; not part of the runtime image) |
| Frontend (Next.js 16, React 19, Tailwind 4) | `frontend/src/app/` |
| Reject controller sketch (untested) | `firmware/reject_controller/` |

## Technology stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, SQLite, ONNX Runtime 1.31, OpenCV 4.14, NumPy, SciPy, ReportLab, bcrypt, PyJWT.
- **ML (training only):** PyTorch 2.15 (MPS), Ultralytics 8.4, scikit-learn.
- **Frontend:** Next.js 16.3, React 19, Tailwind CSS 4, TypeScript.
- **Deployment:** Docker, Docker Compose.

## Models

Full details, per-product tables and how to reproduce them: [docs/MODELS.md](docs/MODELS.md).

### Anomaly detector, ResNet-18 (all 15 MVTec products)

| Metric | Result |
|---|---|
| Mean image AUROC | 0.979 |
| Mean pixel AUROC | 0.977 |
| Recall on defect kinds no model was trained on | 0.918 (342 images) |
| False-reject rate | 0.094 |
| Latency p50 | 17 ms |

### Defect-shape model, YOLO11n-seg (398 test images)

| Metric | Result |
|---|---|
| Box mAP@50 | 0.606 |
| Mask mAP@50 | 0.585 |
| Defective images caught (image-level recall) | 0.848 |
| Image-level precision | 0.993 |
| Good images wrongly flagged | 0.4% |

Per-class F1: scratch 0.77, discolouration 0.68, crack 0.62, dent 0.53, dimensional anomaly 0.43.

### Decisions on 740 held-out images (234 good, 506 defective)

| Outcome | Result |
|---|---|
| Good parts automatically rejected | 0 |
| Good parts sent to manual review | 9.4% |
| Defective parts caught (rejected or sent to review) | 88.9% |
| Defective parts accepted (escapes) | 11.1% |

### Speed

| Measured on | Full pipeline p50 | Throughput |
|---|---|---|
| Apple M1 Pro, CPU | 70 ms | 14 FPS |
| Linux Docker container on the same Mac | 365 ms | — |

## Dataset

MVTec AD: 15 categories and 5,354 images, licensed CC BY-NC-SA 4.0, so it is non-commercial. It is downloaded by script and **not committed**. The split has no overlap between sets, is grouped by defect kind, and keeps a withheld set of defect kinds the supervised model never sees. See [docs/DATASETS.md](docs/DATASETS.md).

## Installation

Requirements:
- Python 3.12;
- Node 22;
- about 6 GB of free disk space for the dataset, needed only if you retrain.

### Backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt          # or: --require-hashes -r requirements.lock
cp .env.example .env                                # then set SECRET_KEY (see below)
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env` settings:

| Variable | Meaning |
|---|---|
| `SECRET_KEY` | **Required** when `ENVIRONMENT=production`; the server refuses to start without it |
| `DEMO_MODE` / `DEMO_PASSWORD` | `true` plus a password creates `inspector@gov.in`, `supervisor@gov.in` and `admin@gov.in` with that password. Off by default |
| `AUTH_REQUIRED` | `true` by default |
| `BACKEND_CORS_ORIGINS` | Comma-separated list. Default `http://localhost:3000` |
| `SEG_MODEL_PATH` | YOLO-seg ONNX model. Default `storage/models/segmentation/production.onnx` |
| `ANOMALY_BACKBONE_PATH` | Anomaly backbone ONNX model. Default `storage/models/anomaly/backbone.onnx` |
| `ANOMALY_PRODUCTS_DIR` | Per-product anomaly models. Default `storage/models/anomaly/products` |
| `MAX_UPLOAD_MB` / `MAX_VIDEO_MB` | Upload limits. Default 25 / 300 |

**Model files.** The trained ONNX models are under `backend/storage/models/`:
- `segmentation/production.onnx`, 11.7 MB;
- `anomaly/backbone.onnx`, 10.6 MB;
- `anomaly/products/*`, 35 MB.

Because they are trained on MVTec AD they carry its non-commercial licence. If they are absent, regenerate them with the commands in [docs/MODELS.md](docs/MODELS.md#7-reproduce). The server also runs without them, falling back to the classical detector, and `/api/health` reports which models are loaded.

### Running the backend

```bash
cd backend
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080
# health:  http://localhost:8080/api/health
# API docs (OpenAPI / Swagger): http://localhost:8080/docs
```

### Running the frontend

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8080/api/v1 npm run build
npm run start            # http://localhost:3000, or `npm run dev` while developing
```

## Docker deployment

```bash
cp .env.example .env      # set SECRET_KEY; optionally DEMO_MODE=true and DEMO_PASSWORD
docker compose up --build
# frontend http://localhost:3000   backend http://localhost:8080/api/health
```

**Container setup:**
- The backend image is Python 3.12-slim with ONNX Runtime and no PyTorch. It runs as a non-root user and installs from `requirements.lock` with `--require-hashes`.
- Models and reports are mounted from `backend/storage/`; the database lives in a named volume.
- On a slow network, add `--build-arg PIP_INDEX_URL=<mirror>`. The hashes still pin the exact official files.

**Verified:** the compose stack builds and passes its health check. It also handles login, a real image upload, a PDF report and the CORS restriction. Inference was also run in the container with networking disabled (`--network none`).

## API documentation

Interactive OpenAPI docs are at `/docs`. The main groups:

| Prefix | Purpose |
|---|---|
| `/api/v1/auth` | Login, current user, register (ADMIN only) |
| `/api/v1/defects` | Inspections, image/frame/video analysis, golden reference per inspection, feedback, PDF report |
| `/api/v1/production` | Products, golden references, lines, machines, batches (+ PDF), units, final decisions |
| `/api/v1/metrology` | Calibrations (checkerboard / reference length), dimensional inspection |
| `/api/v1/live` | Live sessions (BROWSER / CAMERA / RTSP / VIDEO_FILE / CONVEYOR_SIM) and the WebSocket frame stream |
| `/api/v1/analytics` | Overview, root cause, alerts, corrective actions |
| `/api/v1/learning` | Review queue, samples, dataset versions, training jobs, models, promote, rollback |
| `/api/v1/edge` | Runtime status, benchmark, stored evaluation reports, latency budget |
| `/api/v1/inspections`, `/api/v1/rules`, ... | Legal Metrology module (unchanged) |

All routes except `/api/health` and `/api/v1/auth/login` need a bearer token. Promotion, rollback, product and line setup need SUPERVISOR or ADMIN.

## Testing

```bash
cd backend && .venv/bin/python -m pytest tests -q                     # 101 passed
cd frontend && npm run build                                           # 27 routes
# against a running backend started with DEMO_MODE=true:
cd backend && DEMO_PASSWORD=... .venv/bin/python -m scripts.e2e_workflows --manifest ../datasets/prepared/manifest.json
```

The original project scored 40 passed, 3 failed. The 3 failures came from a `cv2.setLogLevel` bug, which is now fixed.

## Demonstration workflow

1. Start the backend with `DEMO_MODE=true DEMO_PASSWORD=<pw>` and start the frontend. Log in as `supervisor@gov.in`.
2. **Fill the dashboards (simulated):**
   ```bash
   cd backend && .venv/bin/python -m scripts.simulate_production --reset --product metal_nut --samples storage/demo_samples/metal_nut --units 300
   ```
   This runs real held-out images through real inference. Machine M-02 receives extra defective parts, and every row is marked SIMULATED.
3. **Overview / Defect Analytics:** KPIs, Pareto, control chart, open alert for M-02.
4. **Root-Cause Investigation:** M-02 is the only significant factor (odds ratio ≈ 8). Record a corrective action.
5. **Defect Detection:** upload `storage/demo_samples/metal_nut/defect/*.png` to see masks, the anomaly heatmap, the decision and a PDF report.
6. **Live Inspection:** choose *Simulated conveyor* (`demo_samples/metal_nut`) or *Browser camera*. Parts get IDs, decisions and simulated reject events.
7. **Dimensional Inspection:** create a calibration and inspect an image of a part on a plain background.
8. **Dataset & Feedback → Model Versions:** label units, train a candidate, see the gate checks, then promote or roll back.
9. **Model Performance:** every evaluation number above, read from the stored reports.
10. **Rule-Based Engine:** the original Legal Metrology flow.

`storage/demo_samples/` is built from the MVTec test split (git-ignored); recreate it with `python3 ml/datasets/make_demo_samples.py` from the project root.

## Known limitations

- **No physical line was tested.**
  - The actuator is simulated.
  - The serial and webhook actuators are tested only against fakes.
  - `firmware/` has not been compiled or flashed.
  - Belt-speed timing is calculated, not measured.
- **Benchmarks cover only this Mac and its Docker VM.** No edge board was tested, and the 5× Docker slowdown was not investigated.
- **MVTec AD is a studio dataset:** one centred part, controlled lighting. Expect lower accuracy on a real line until the models are retrained on line images through the learning loop.
- **Weak products:** screw, zipper and grid reject too many good parts. Capsule, pill and transistor miss too many defects. DIMENSIONAL_ANOMALY and DENT are the weakest classes, and test sets are small (6–30 good images per product).
- **Manual review share:** 64.6% of defective parts go to review rather than automatic rejection, because the default policy does not auto-reject defects the model cannot name.
- **Dimensional accuracy** is verified only on synthetic images of known geometry. Real parts have not been measured against a gauge.
- **Golden-reference comparison** adds no measurable benefit on MVTec when learned models exist, and costs about 190 ms per image.
- **Licences are non-commercial:** the models are MVTec-trained (CC BY-NC-SA) and Ultralytics is AGPL-3.0.
- **Lint:** 60 errors remain, all in original Legal Metrology frontend files (mostly `no-explicit-any`). The new pages are lint-clean apart from unused-import warnings.
- **Database:** SQLite with a single backend process. Multi-line deployment would need PostgreSQL and a shared session manager.

## Project documents

| File | Content |
|---|---|
| [01_PROBLEM_STATEMENT_REQUIREMENTS.md](01_PROBLEM_STATEMENT_REQUIREMENTS.md) | Official text, requirements, acceptance criteria, matrix |
| [02_PARAKHMAAN_EXISTING_PROJECT_AUDIT.md](02_PARAKHMAAN_EXISTING_PROJECT_AUDIT.md) | Audit of the original code |
| [03_COMPLETE_IMPLEMENTATION_ROADMAP.md](03_COMPLETE_IMPLEMENTATION_ROADMAP.md) | Phases and status |
| [FINAL_IMPLEMENTATION_REPORT.md](FINAL_IMPLEMENTATION_REPORT.md) | What was built, results, limitations |
| [docs/REQUIREMENT_TRACEABILITY.md](docs/REQUIREMENT_TRACEABILITY.md) | Requirement → code → test → result |
| [docs/MODELS.md](docs/MODELS.md), [docs/DATASETS.md](docs/DATASETS.md) | Models, data, licences |
| [docs/HARDWARE_INTERFACE.md](docs/HARDWARE_INTERFACE.md) | Reject signal, serial protocol, wiring notes |
| [docs/LEGAL_METROLOGY_MODULE.md](docs/LEGAL_METROLOGY_MODULE.md) | Original README of the preserved module |
