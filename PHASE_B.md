# ParakhMaan — Phase B: Governed Automated Learning Loop

**Team Tarang · Indux 5.0 · Problem Statement 12**

Phase B makes the platform improve from production feedback **automatically, but never ungoverned**: the system selects what to label, builds versioned datasets, trains and evaluates candidates on its own — and a model only reaches production after passing an evaluation gate, an optional shadow test and a human approval, with one-click rollback.

> Principle: unreviewed AI predictions are never used as training labels, and no model is deployed without passing the gate (or an administrator override that is recorded with a reason).

Previous phase: [PHASE_A.md](PHASE_A.md) (scalable foundation; also holds the roadmap for Phases C–E).

---

## 1. The loop

```
 Live inspection (web / camera / video / edge)
        │  active model from the registry
        ▼
 Smart sampler ──► Review queue ──► Verified images ──► Dataset version (YOLO, immutable)
 (uncertain, disagreement,   (confirm / reject /          │   sticky splits, frozen golden test set
  unknown class, drift,       relabel / draw missed        ▼
  random PASS audit)          defects, verify)       Training worker (warm start + full-history replay)
                                                           │   ONNX export
                                                           ▼
 Rollback ◄── Registry: ACTIVE ◄── Approval ◄── Shadow mode ◄── Evaluation gate (golden set vs active model)
        │
        └──► Edge nodes pull the new active model automatically
```

---

## 2. What was built

### B1 — Smart sampler (active learning)
Every analysed image (web upload, camera, video keyframe, edge result) is scored; if any reason applies a prioritised **review task** is created (one per image).

| Reason | Trigger | Priority |
| :--- | :--- | :--- |
| `UNCERTAIN` | a detection's confidence is in the uncertain band (default 0.30–0.60) | +3 +1 per detection |
| `DISAGREEMENT` | in hybrid mode, a defect class the model knows was found by only one engine (model or OpenCV) | +2 |
| `UNKNOWN_CLASS` | a detection outside the model's taxonomy (dimensional anomalies excluded — they are geometry rules) | +2 |
| `QUALITY` | frame too dark / saturated | +1 |
| `DRIFT` | the station's input distribution shifted (B8) | +2 |
| `AUDIT` | a **random 2 % of clean (PASS) images** — 20 % at drifting stations — so missed defects (false negatives) are found too | +1 |

Sampling decisions are deterministic per image (hash-based), so they are reproducible and testable.

### B2 — Review queue
- `/review` page: prioritised queue with reason filters, image workspace with detection boxes.
- Reviewers **confirm / reject / relabel** model detections and **draw boxes for missed defects** (stored as `HUMAN` detections, which also update the inspection outcome).
- **"Verify for training"** marks the image `VERIFIED` (remaining pending detections are accepted, or the reviewer can require every detection to be resolved), assigns its sticky split and closes the task. Skipping is supported.
- From any inspection: **Verify for training** or **Send to review queue**.
- Every action is written to the audit trail and reviewer-action log.

### B3 — Versioned datasets
- Built only from `VERIFIED` images; labels = CONFIRMED / RELABELED detections + reviewer-drawn boxes. Rejected and unreviewed predictions are never labels.
- **Sticky splits** (train / val / test) assigned once per image and grouped by **batch** (or inspection when no batch is recorded), so near-identical images of one batch never leak across splits.
- The **test split is the frozen golden set** — never used for training; every candidate is scored on it.
- Each build is an immutable YOLO export (`images/`, `labels/`, `data.yaml`, `manifest.json` with SHA-256 per image) zipped into object storage at `datasets/<org>/v<N>/dataset.zip`, downloadable from the UI.

### B4 — Training worker
- `MODEL_TRAINING` background job (Redis worker in Docker, in-process locally):
  1. builds a fresh dataset from all verified images (unless one is chosen) — training on the full verified history is the **replay buffer** that prevents forgetting older defect types;
  2. fine-tunes YOLO with Ultralytics, **warm-starting from the active model's weights**;
  3. exports a static-size ONNX model (readable by OpenCV DNN, no PyTorch needed for inference);
  4. registers a `CANDIDATE` with metrics and a **model card** (classes, dataset version + manifest hash, warm-start source, training settings, limitations);
  5. runs the evaluation gate.
- **Auto-trigger policy** (`AUTO_TRAIN_MIN_NEW_VERIFIED`): when enough new images have been verified since the last dataset, training is queued automatically (one training job per organisation at a time). Default: off (manual).

### B5 — Evaluation gate
Candidate and active model are both scored (model-only, mAP@0.5 with IoU 0.5) on the golden test split. All checks must pass:

| Check | Default |
| :--- | :--- |
| Golden set large enough | ≥ 10 test images |
| mAP@0.5 not worse than the active model | tolerance 0.00 |
| No class recall drop (classes with ≥ 3 test labels) | ≤ 2 points |
| Critical class recall (crack) | ≥ 0.50 |
| Latency | ≤ 1.5 × active model |

The full report (per-class metrics for both models, every check with value and threshold) is stored on the model version. **The gate never promotes** — it only decides whether promotion is allowed.

### B6 — Shadow mode
- A candidate in `SHADOW` runs on every live image next to the active model **without affecting any outcome**; its predictions and the active model's model-only predictions are stored with an agreement score.
- Once shadowed images are human-verified, both are scored against the verified labels (precision / recall / F1), so promotion decisions rest on real production traffic.

### B7 — Model registry & governance
```
TRAINING → CANDIDATE → GATE_PASSED → SHADOW → ACTIVE → RETIRED (→ ACTIVE again on rollback)
                     ↘ GATE_FAILED (promotion only by an administrator, with a recorded reason)
```
- Exactly one `ACTIVE` model per organisation serves all inference (API, worker, video, live frames); API replicas and workers pick up a promotion on the next request.
- On first start the configured model file is registered as **v1 (imported)** with a model card built from its original training metadata (Kaggle validation mAP@0.5 0.717).
- **Quality Managers** can shadow-test and promote gate-passed models; **Administrators** can override a failed gate only with a written reason; **one-click rollback** to any previously active model.
- Every transition (import, dataset built, training started/completed/failed, gate evaluated, shadow started/stopped, promoted, rolled back) is recorded in the model audit trail.
- **Edge nodes** poll `GET /edge/model` and hot-swap to the new active model (SHA-256 verified) — no redeploy.

### B8 — Drift monitoring
- Per station, the last 24 h are compared with the previous 14 days using the **Population Stability Index** on three label-free distributions: image brightness, strongest detection confidence, detections per image.
- PSI < 0.10 OK · 0.10–0.25 WATCH · > 0.25 ALERT (configurable). Drifting stations raise review sampling (B1). Shown on the Models page.

---

## 3. User interface

| Page | Who | What |
| :--- | :--- | :--- |
| `/review` | Operator, Quality Manager, Admin | Prioritised queue, reason filters, box drawing, confirm / reject / relabel, verify, skip |
| `/models` | Quality Manager, Admin (Auditor read-only) | Active / shadow / dataset / feedback overview, build dataset, train candidate with live job progress, registry with gate report + model card, shadow / promote / rollback / re-evaluate / download, dataset versions (YOLO zip), drift table, audit trail |
| `/defects/[id]` | All | Training-data status per image, *Verify for training*, *Send to review queue* |

---

## 4. API

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| GET | `/api/v1/review/queue`, `/review/stats`, `/review/tasks/{id}` | Queue, counters, task workspace |
| POST | `/api/v1/review/images/{id}/annotations` | Draw a missed defect |
| DELETE | `/api/v1/review/annotations/{id}` | Remove a reviewer-drawn box |
| POST | `/api/v1/review/images/{id}/complete` | Verify image for training |
| POST | `/api/v1/review/images/{id}/request`, `/review/tasks/{id}/skip` | Manual task, skip |
| GET | `/api/v1/learning/overview`, `/learning/models`, `/learning/models/{id}` | Registry & loop status |
| GET / POST | `/api/v1/learning/datasets`, `/learning/datasets/{id}/download` | Dataset versions |
| POST | `/api/v1/learning/models/train` | Train a candidate (job) |
| POST | `/api/v1/learning/models/{id}/evaluate` | Re-run the gate (job) |
| POST / DELETE | `/api/v1/learning/models/{id}/shadow` | Start / stop shadow mode |
| POST | `/api/v1/learning/models/{id}/promote`, `/rollback` | Governed promotion / rollback |
| GET | `/api/v1/learning/drift`, `/learning/events` | Drift and audit trail |
| GET | `/api/v1/edge/model` | Active model for edge nodes |
| POST | `/api/v1/learning/demo/seed-reviewed` | **Development only**: synthetic verified images to demonstrate the loop |

New permissions: `model:read` (Quality Manager, Admin, Auditor), `model:manage` (Quality Manager, Admin), `model:override` (Admin).

---

## 5. Configuration (environment variables)

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `LEARNING_CLASSES` | `scratch,crack,dent,discolouration` | YOLO class order |
| `REVIEW_UNCERTAIN_LOW` / `HIGH` | 0.30 / 0.60 | Uncertain band |
| `REVIEW_AUDIT_RATE` / `REVIEW_DRIFT_AUDIT_RATE` | 0.02 / 0.20 | Random audit of clean results |
| `SPLIT_VAL_FRACTION` / `SPLIT_TEST_FRACTION` | 0.15 / 0.15 | Batch-grouped split sizes |
| `TRAIN_EPOCHS`, `TRAIN_IMGSZ`, `TRAIN_BATCH`, `TRAIN_DEVICE` | 15, 320, 8, cpu | Training settings |
| `TRAIN_BASE_WEIGHTS` | `yolov8n.pt` | Used only when the active model has no `.pt` weights |
| `AUTO_TRAIN_MIN_NEW_VERIFIED` | 0 (off) | Auto-training threshold |
| `GATE_*` | see B5 | Gate thresholds |
| `DRIFT_PSI_WATCH` / `DRIFT_PSI_ALERT` | 0.10 / 0.25 | Drift levels |
| `EDGE_MODEL_CHECK_SECONDS` | 300 | Edge model polling interval |

---

## 6. Verification

| Check | Result |
| :--- | :--- |
| Backend test suite | **74 passed** (59 from earlier phases + 15 in `tests/test_phase_b.py`) |
| Phase B tests cover | sampler reasons & deterministic audit rate, PSI / drift levels, every gate rule, shadow matching, review flow (task, box drawing validation, verify, pending-resolution option, delete only human boxes), organisation isolation of the queue, sticky batch-grouped splits, dataset export (verified-only labels, YOLO format, rejected excluded), registry governance (gate / override / reason / shadow / promote / rollback / audit events / role checks), shadow predictions on live traffic, edge model pull + hot-swap, **a real training job** (1 epoch) producing a gated candidate |
| Real training run (local CPU) | 80 synthetic verified images → dataset v1 (16 golden test images) → warm start from v1 → 3 epochs in 73 s → ONNX export → OpenCV DNN loaded the new model → gate compared it with the active model and **correctly failed it** (mAP@0.5 0.265 vs 0.292, crack recall 0) — the active model stayed in place |
| Migration `0003` | upgrade / downgrade / upgrade round-trip |
| Frontend | `tsc` clean |

---

## 7. Demonstrating the loop

1. Sign in as `admin@parakhmaan.local` (development).
2. **Models → Seed demo data** (synthetic verified images; development only), or inspect real parts and verify them in **Review**.
3. **Train candidate** — watch the job progress (dataset build → training → ONNX export → gate).
4. Expand the new version to read the gate report and model card.
5. If it passed: **Shadow** → inspect a few parts → compare on the Models page → **Promote**. If it failed: only an admin can override, with a reason.
6. **Roll back** from the retired version at any time; edge nodes follow automatically.

> Synthetic data proves the pipeline works; it is **not** evidence of real-world accuracy. Real accuracy claims require verified images of the pilot product.

---

## 8. Decisions & limitations

- **Ultralytics without `opencv-python`:** installed with `--no-deps` (locally and in the worker image) so it does not conflict with `opencv-python-headless`. Only the worker image carries PyTorch (`TRAINING=true` build argument); the API image stays small.
- **Inference stays on OpenCV DNN** (no PyTorch / onnxruntime at inference time); exports use opset 12 with a static input size for compatibility.
- **Gate compares model-only output** (the OpenCV engine is identical for both models).
- **Validation split fallback:** with very few batches the val split can be empty; training then validates on the train split and records this in the metrics. The golden test set is never touched.
- **Training runs on CPU** by default; set `TRAIN_DEVICE=0` on a GPU worker.
- Training samples captured as crops in Phase A (`DEFECT_SAMPLES_DIR`) remain; Phase B datasets use full images from object storage instead.
- Drift needs at least 20 baseline and 10 recent images per station before it reports a status.

---

## 9. What's next

- **Phase C — Differentiators:** anomaly → class onboarding from only good images, process-aware root cause, configurable alerts, Pareto / defect-rate analytics, capture-quality coach.
- **Phase D — Dual inspection & hardening.**
- **Phase E — Federated learning** across factories, reusing this phase's training worker, evaluation gate, shadow mode and registry.

See [PHASE_A.md](PHASE_A.md) for the full roadmap.
