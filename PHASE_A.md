# ParakhMaan — Phase A: Scalable Foundation (and the road to Phases B–D)

**Team Tarang · Indux 5.0 · Problem Statement 12 — AI & Computer-Vision Based Surface and Product Defect Inspection**

This document records what Phase A delivered, how it was verified, and what Phases B, C, D and E will build on top of it.

| Phase | Theme | Status |
| :--- | :--- | :--- |
| **A** | Scalable foundation: multi-tenant data model, security & RBAC, PostgreSQL, object storage, job queue, edge node | ✅ **Done** |
| **B** | Governed automated learning loop (data flywheel) | ✅ **Done** — see [PHASE_B.md](PHASE_B.md) |
| **C** | Differentiators: anomaly → class onboarding, process-aware root cause, alerts | ⏳ Next |
| **D** | Packaging-line "dual inspection" (defects + Legal Metrology) and final hardening | Planned |
| **E** | Federated learning across factories (built during the hackathon) | Planned |

---

## 1. Why Phase A

The earlier prototype was a single process with SQLite, files in a public folder, synchronous video processing and development conveniences in authentication (anonymous requests were treated as a default inspector; plaintext password matches were accepted). That is fine for a demo but does not scale or survive scrutiny. Phase A turns it into a platform that can run on one laptop **and** as a distributed, multi-tenant deployment.

---

## 2. Architecture after Phase A

```
 Camera / phone ──► Edge node (app.edge.main) ── local inference + durable outbox ──┐  (keeps inspecting offline)
                                                                                    ▼  X-Device-Key
 Browser ──► Next.js ──► FastAPI API ──► PostgreSQL (Alembic migrations)
                            │   │
                            │   └──► S3-compatible object storage (images served via signed URLs)
                            └──► Redis queue ──► RQ workers (video analysis; scale horizontally)
```

| Concern | Local development | docker compose / production |
| :--- | :--- | :--- |
| Database | SQLite file | PostgreSQL 16 (`DATABASE_URL`) |
| Schema changes | Alembic, auto-run on API start | Same (`AUTO_MIGRATE`); pre-Alembic databases are stamped, then upgraded |
| Files | `backend/storage` | S3 / RustFS (`STORAGE_BACKEND=s3`); browser access only via HMAC-signed, expiring links |
| Background jobs | In-process thread pool | Redis + `python -m app.workers.worker` (any number of workers) |
| Edge inference | Optional | `docker compose --profile edge`; results queue locally and sync with retry/back-off |

---

## 3. What Phase A delivered

### 3.1 Multi-tenant organisation model
- New entities: **Organization → Plant → ProductionLine → Station**, plus **Product**, **EdgeDevice**, **Job**.
- Inspections now carry `organization_id`, `product_id`, `station_id`, `shift`, `batch_code`, `source` (WEB / EDGE / API) and `external_ref` (idempotency key for edge uploads).
- Detections record `model_version` (ONNX file name + SHA-256 fingerprint) whenever the model contributed.
- **Every API query is scoped to the caller's organisation**; another tenant's inspection, detection, report or job returns 404.

### 3.2 Security hardening & role-based access control
| Before | After |
| :--- | :--- |
| No token → silently acted as a default inspector | No token → **401** on every protected endpoint |
| Demo login auto-created accounts; public `/auth/register` accepted a role | Admin-only user management (`/admin/users`); registration endpoint removed |
| SHA-256 + static salt, and plaintext match accepted | **bcrypt**; legacy hashes verified once and upgraded on login; plaintext never accepted |
| No login throttling | Rate limit: 5 failed attempts per email+IP per 5 minutes → 429 |
| CORS `*`, fallback secret key | Explicit `CORS_ORIGINS`; `ENVIRONMENT=production` refuses default `SECRET_KEY`, wildcard CORS and demo seeding |
| `/storage` publicly mounted | Removed; files served only through signed, expiring links (`/api/v1/files/...`) |
| Any upload accepted | Validated by magic bytes, size limit and pixel count (decompression-bomb guard) |
| LLM config endpoint open | Admin only |

**Roles** (enforced in FastAPI, mirrored in the UI):

| Role | Permissions |
| :--- | :--- |
| Operator | Run inspections (image / camera / video), give detection feedback |
| Quality Manager | Operator rights + finalise / override outcomes, view analytics |
| Administrator | Everything + plants/lines/stations, products, users, edge devices, demo data, system configuration |
| Auditor | Read-only access to inspections, evidence, reports and analytics |

Legacy roles migrate automatically: `INSPECTOR → OPERATOR`, `SUPERVISOR → QUALITY_MANAGER`.

### 3.3 PostgreSQL & migrations
- Alembic introduced: `0001` baseline schema, `0002` Phase A (organisation structure, jobs, edge devices, new inspection columns).
- `0002` moves existing single-tenant data into a **Default Organization**, maps legacy roles and copies defect batch numbers into `batch_code`.
- Databases created before Alembic are detected, stamped at the baseline and upgraded — tested on a copy of the real project database (16 defect + 18 legal inspections preserved).
- Downgrade/upgrade round-trip tested. PostgreSQL connection pooling with pre-ping.

### 3.4 Object storage abstraction
- One interface for **local disk** or **S3-compatible** storage (AWS S3, RustFS, SeaweedFS, MinIO).
- Code stores *keys* (`uploads/<inspection>/<uuid>.jpg`); OpenCV/OCR read via a local cache.
- API responses include a computed `file_url` (signed, expiring, cache-friendly). Tampered or expired links → 403; path traversal blocked.
- Legacy rows with absolute local paths keep working.

### 3.5 Background job queue
- `Job` table is the source of truth (status, progress 0–1, message, result, error).
- Transport: Redis + RQ when `REDIS_URL` is set; otherwise an in-process thread pool; `JOB_MODE=eager` for tests.
- **Video analysis is now asynchronous**: `POST /defects/inspections/{id}/video` returns a job (202); clients poll `GET /jobs/{id}`. The uploaded video is deleted from storage after processing.
- Worker entry point `python -m app.workers.worker` (Windows-compatible worker class included).

### 3.6 Edge inference node
- Separate service `app.edge.main` (same image, different command): local inference → **durable SQLite outbox** → background sync to `POST /api/v1/edge/ingest` with an `X-Device-Key`.
- Offline-tolerant: network errors retry with exponential back-off; permanent 4xx failures are parked; results keep their capture time.
- Server ingestion is **idempotent** on the device's `local_id`, so retries never duplicate inspections.
- Devices are registered per station in the Admin console; the plaintext key is shown once, only an HMAC hash is stored; keys can be rotated or devices disabled.
- Edge API: `POST /infer`, `POST /infer/frame`, `GET /queue`, `POST /sync`, `GET /health`.

### 3.7 Organisation & administration APIs
- `/org/tree`, `/org/plants`, `/org/lines`, `/org/stations`, `/org/products` (read for all roles, write for admins).
- `/admin/users` (create, change role, disable, reset password; admins cannot remove their own admin access).
- `/admin/devices` (register, rotate key, enable/disable).
- `/jobs`, `/jobs/{id}`; `/edge/ping`, `/edge/ingest`; `/files/{signed-key}`.

### 3.8 Shared defect pipeline
Defect logic moved from the API router into `app/services/defect_pipeline.py`, so the **API, the worker and edge ingestion share one implementation** (analysis, video processing, outcome rules, reports, training-sample capture, demo seeding).

### 3.9 Frontend
- **Login page** (development demo accounts listed only when the API runs in development mode) and a session guard that redirects signed-out users.
- All API calls send the bearer token; a 401 clears the session and returns to login.
- **Role-aware navigation** (analytics for managers/auditors, Admin for administrators; read-only users don't see actions they can't perform).
- Images use signed `file_url`s; PDF reports download through an authenticated request.
- Defect inspection form: **product, plant/line/station and shift selectors**; video uploads show **live job progress**.
- **Admin console** (`/admin`): plants & stations, products, users & roles, edge devices (one-time key display, rotation).
- Home now opens Defect Inspection; the Legal Metrology module remains one click away.

### 3.10 Deployment
- `docker-compose.yml`: `postgres`, `redis`, `objectstore` (RustFS), `api`, `worker`, `frontend`, and `edge` (profile).
- `.env.example` with every setting; non-root containers; API health check; the ONNX model is bind-mounted read-only.
- `requirements.txt` (runtime) and `requirements-dev.txt` (pytest, moto).

---

## 4. Verification

| Check | Result |
| :--- | :--- |
| Backend test suite | **59 passed** (43 existing + 16 new in `tests/test_phase_a.py`) |
| New tests cover | 401 without token, rate limiting, legacy-hash upgrade, no plaintext login, removed registration, role permissions, admin self-lockout guard, cross-organisation isolation, upload validation, signed-link tampering/expiry, path traversal, S3 backend (moto), failed jobs reported, edge ingest auth + idempotency, edge offline queue → later sync, migration data move + downgrade, production config refusal |
| Frontend | `tsc` clean; `next build` succeeds (incl. `/login`, `/admin`) |
| Docker end-to-end | PostgreSQL + S3 storage + Redis worker: login, demo data, signed image from S3, image analysis with ONNX + OpenCV, **video job processed by the separate worker container**, edge container inferred (~210 ms), queued and **synced to the API** where it appears with source `EDGE` and its station |
| Real-database migration | Copy of `legal_metrology.db` upgraded; all inspections moved into Default Organization |

---

## 5. Running it

### Local development (no extra services)
```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests
python -m uvicorn app.main:app --port 8080 --reload
```
```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```
Development demo accounts (password `ParakhMaan@2026`): `admin@parakhmaan.local`, `manager@parakhmaan.local`, `operator@parakhmaan.local`, `auditor@parakhmaan.local`.

### Full stack
```bash
cp .env.example .env              # set SECRET_KEY and passwords beyond a local demo
docker compose up -d --build
docker compose up -d --scale worker=3              # more workers
EDGE_DEVICE_KEY=pmk_... docker compose --profile edge up -d edge
docker compose down                # stop
```
App http://localhost:3000 · API docs http://localhost:8080/docs · Storage console http://localhost:9001 · Edge http://localhost:8090

### Production checklist
`ENVIRONMENT=production`, random `SECRET_KEY` (≥ 32 chars), `SEED_DEMO_DATA=false`, `BOOTSTRAP_ADMIN_EMAIL/PASSWORD`, `CORS_ORIGINS` and `PUBLIC_API_URL` set to your domain, TLS in front of the API, real storage and database credentials.

---

## 6. Decisions & notes

- **Breaking API changes:** all endpoints except `/api/health` require authentication; the video endpoint returns a job instead of a summary; reports require an authenticated download.
- **MinIO → RustFS:** MinIO no longer publishes community Docker images. RustFS (Apache-2.0, S3-compatible) was verified with boto3. Any S3 service works by changing `S3_ENDPOINT_URL`.
- **OpenCV pinned to 4.x:** the unpinned image pulled OpenCV 5.0, which broke the detector; 4.x is the validated range.
- **Frontend image on Node 24 / npm 11** with a regenerated lock file (the old one was out of sync and `npm ci` failed).
- The legacy `inspector@gov.in` account stored a plaintext password and can no longer log in (by design).
- **Recommended:** `backend/legal_metrology.db` is tracked in Git and contains password hashes — untrack it with `git rm --cached backend/legal_metrology.db` and add `*.db` to `.gitignore`.

### Known limitations (carried into later phases)
- Login rate limiting is per API instance (move to Redis when running multiple API replicas).
- Training samples are still written to local disk (`DEFECT_SAMPLES_DIR`) — moved to object storage in Phase B.
- The edge outbox is not encrypted at rest.
- The model's real-world accuracy is unproven: mAP@0.5 = 0.717 on its own Kaggle validation set, but it missed cracks and dents on our synthetic benchmark.

---

## 7. Phase B — Governed automated learning loop (next, ~3–4 days)

**Goal:** the system improves from production feedback automatically, but **never deploys a model without passing an evaluation gate and human approval**. Unreviewed predictions are never used as labels.

```
 Inference ─► Smart sampler ─► Review queue ─► Approved labels ─► Versioned dataset
                                                                       │
 Rollback ◄─ Model registry ◄─ Approval ◄─ Shadow mode ◄─ Eval gate ◄─ Training worker
```

| # | Deliverable | Details |
| :--- | :--- | :--- |
| B1 | **Smart sampler** | Routes images to review when: confidence in the uncertain band (≈0.3–0.6); ONNX and OpenCV disagree; anomaly score high but no known class; drift detected; plus a **random ~2% of PASS results** (catches missed defects) |
| B2 | **Review queue UI** | Prioritised queue; confirm / reject / relabel; **draw boxes for missed defects** (false negatives); keyboard shortcuts |
| B3 | **Versioned dataset** | Full-image YOLO export (not just crops) in object storage; manifest with hashes; train/val/test **split by batch / capture session**; a **frozen golden test set** never used for training |
| B4 | **Training worker** | Job type `MODEL_TRAINING`: fine-tunes the current champion (warm start) with a **replay buffer** of historical data to avoid forgetting; exports ONNX. Triggers: N new approved labels, drift alarm, or schedule |
| B5 | **Evaluation gate** | Candidate vs champion on the golden set: mAP not lower, no class recall drop > 2 points, critical-class (crack) recall ≥ minimum, latency within budget. Uses `scripts/evaluate_defect_model.py` |
| B6 | **Shadow mode** | Candidate runs alongside the champion on live traffic without affecting decisions; agreement and reviewed outcomes compared |
| B7 | **Model registry & promotion** | `ModelVersion` table (metrics, dataset version, model card); Quality Manager approves; edge nodes pull the new model; **one-click rollback** |
| B8 | **Drift monitoring** | Per-station distributions of confidence, brightness and (optionally) embeddings; PSI / KS alerts that increase review sampling |

**Acceptance criteria:** a full cycle runs end to end on demo data (feedback → dataset version → training job → gate report → shadow → approval → active model changes → rollback works); every model change is audited.

**Prerequisite:** install Ultralytics in the worker image (torch ≥ 2.10 if Anomalib is added later).

---

## 8. Phase C — Differentiators (~3–4 days)

| # | Deliverable | Why it matters |
| :--- | :--- | :--- |
| C1 | **Anomaly → class onboarding** | Onboard a new product with only **20–50 good images** using training-free / few-shot anomaly detection (Anomalib: PatchCore, SuperADD, FoundAD). Flagged anomalies are **clustered automatically**; an operator names each cluster ("these are dents"); named clusters become labelled data that train the YOLO model through Phase B. Starts like Siemens Inspekto (no defect data needed), ends like LandingLens (per-class labels, root cause). Also adds the **UNKNOWN_ANOMALY** category |
| C2 | **Process-aware root cause** | Ingest process data (CSV upload or MQTT: press force, temperature, line speed, die/tool changes, material batch, shift). Change-point detection and correlation produce evidence-linked hypotheses such as *"dents tripled on Station 2 after the 14:20 die change"* — always labelled as hypotheses with counts and time windows |
| C3 | **Configurable alert engine** | Baseline-relative rules per product/station (e.g. scratch rate above baseline, any confirmed critical crack, repeated dents at one station); notifications; alert precision tracked |
| C4 | **Production analytics** | Defect rate per 100 / 1,000 units by product, station and shift; **Pareto chart**; corrective-action tracking ("did the fix reduce the rate?") |
| C5 | **Capture-quality coach** | Surface-appropriate quality gate (never auto-PASS a blurry or badly framed image) with live guidance to fix blur, glare, framing or lighting before inspection |

**Acceptance criteria:** a new product onboarded from good images only reaches a working anomaly detector in minutes; at least one cluster graduates into a named class; an injected process change produces a correct, evidence-backed alert.

---

## 9. Phase D — Dual inspection & final hardening (~2–3 days)

| # | Deliverable | Details |
| :--- | :--- | :--- |
| D1 | **Packaging-line dual inspection** | One capture checks physical package defects **and** Legal Metrology declarations (OCR + the existing deterministic rule engine with 40+ rules) in a single unified report — positioned as an optional compliance module |
| D2 | **Security & reliability pass** | Redis-backed rate limiting, encrypted edge outbox, dependency/vulnerability scan, backup & restore test, OWASP API Top-10 review, request timeouts and resource limits on inference |
| D3 | **Benchmark report** | Held-out **real** pilot-product test set: per-class precision/recall/F1, confusion matrix, mAP; measured p50/p95 latency and FPS on the demo laptop / edge device — only measured numbers are quoted |
| D4 | **Demo & documentation** | Demo script (inspect → review → analytics → alert → retrain → PDF), model card, deployment guide, architecture diagrams |

---

## 10. Parallel track — data (team, starts now)

The learning loop is only as good as its data. Alongside Phases B–C:
1. Choose one **pilot product family** (e.g. sheet-metal parts).
2. Capture **300–500 images** including clean parts, across lighting conditions, shifts and batches.
3. Label in CVAT or Label Studio; split by batch to avoid leakage.
4. Retrain (compare YOLOv8n @ 320 with YOLOv8s @ 640) and evaluate:
   `python -m scripts.evaluate_defect_model --dataset path/to/test`
5. Drop the new `best.onnx` into `backend/storage/models/` — the integration already works.

---

## 11. Phase E — Federated learning across factories (during the hackathon, ~2–3 days)

**Goal:** several factories (or plants of one company) improve one shared defect model **without sending their raw images to a central server**. Each site trains on its own data; only model updates travel. This builds directly on Phase B (training worker, evaluation gate, model registry) and Phase A (edge nodes with device keys, organisation model).

```
                 ┌──────────── Coordinator (central API + Flower server) ────────────┐
                 │  round config ─► aggregate (FedAvg / FedProx) ─► eval gate ─► registry │
                 └───────▲───────────────────────▲───────────────────────▲──────────┘
            model update │          model update │          model update │   (weights only, no images)
                 ┌───────┴──────┐        ┌───────┴──────┐        ┌───────┴──────┐
                 │ Factory A    │        │ Factory B    │        │ Factory C    │
                 │ local data   │        │ local data   │        │ local data   │
                 │ local train  │        │ local train  │        │ local train  │
                 └──────────────┘        └──────────────┘        └──────────────┘
```

| # | Deliverable | Details |
| :--- | :--- | :--- |
| E1 | **Federated client** | Runs on an edge node / site server (reuses `app.edge` and its device key): receives the global model, fine-tunes YOLO for a few local epochs on its **own reviewed labels** (from the Phase B review queue), returns weight updates plus sample counts and local metrics |
| E2 | **Coordinator** | Flower (`flwr`) server inside the platform, launched as a `FEDERATED_ROUND` job; round configuration (participating sites, local epochs, learning rate) from the Admin console |
| E3 | **Aggregation** | FedAvg as the baseline, FedProx for non-identical data across factories (different products, lighting, cameras); weighted by sample count |
| E4 | **Security & privacy** | Clients authenticate with device keys over TLS; updates are validated (shape/norm checks, outlier rejection to resist poisoned updates); optional secure aggregation and differential-privacy noise; audit log of every round and participant |
| E5 | **Governance** | The aggregated model goes through the **same Phase B evaluation gate, shadow mode and Quality Manager approval** before any site uses it; per-site metrics show who benefits; rollback via the model registry |
| E6 | **Simulation & dashboard** | Demo with **3 simulated factories** using deliberately different data splits (product mix, lighting); UI shows per-round global and per-site metrics, participation and data never leaving sites |

**Acceptance criteria:**
- Three simulated sites with non-identical data complete at least 5 rounds end to end.
- The federated model beats **each site's local-only model** on a combined held-out test set and approaches a centrally trained model.
- It is demonstrable (logs / network capture) that **no images leave a site** — only weight updates.
- Every round is audited and the promoted model passes the evaluation gate.

**Dependencies:** Phase B (training worker, golden test set, evaluation gate, model registry); Ultralytics and `flwr` in the worker / client images.

**Why it matters for the pitch:** quality data is commercially sensitive, so factories will not pool images. Federated learning lets an industry cluster (e.g. an auto-component supplier network) share defect knowledge while each plant keeps its data — something none of the incumbent inspection products we reviewed offer.

---

## 12. Out of scope for the hackathon (production roadmap)

Kubernetes, Kafka and LLM-generated defect explanations. They are compatible with this architecture but add complexity without improving the core inspection workflow at this stage.
