# AI-Powered Legal Metrology Compliance & Inspection Platform (SIH26034)

[![Legal Metrology Rules 2011](https://img.shields.io/badge/Statutory_Standard-LMR_2011_Amendments_2026-blue.svg)](https://consumeraffairs.nic.in)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js 16](https://img.shields.io/badge/Frontend-Next.js_16_(App_Router)-black.svg)](https://nextjs.org)
[![PyTest](https://img.shields.io/badge/Tests-17_Passing-success.svg)](backend/tests)
[![License](https://img.shields.io/badge/License-Government_Open_Standard-orange.svg)](#)

An enterprise-grade, dual-engine inspection system engineered for the **Smart India Hackathon 2026** problem statement **SIH26034**: *"AI-Powered Legal Metrology Compliance & Inspection Platform"*.

Designed for Legal Metrology Officers, State Enforcement Squads, and E-Commerce Compliance Auditors to inspect packaged commodities across 1–4 surfaces, evaluate image clarity, extract declarations via vision & local LLMs, and validate them against the **Legal Metrology (Packaged Commodities) Rules, 2011** (incorporating all Gazette notifications up to 2026).

---

## 🏛️ Core Principles & Dual-Engine Architecture

> **⚖️ The Legal Non-Delegation Principle:** AI/LLM is strictly an assistive perception and extraction tool. AI **NEVER** decides statutory compliance. The deterministic, versioned Rule Engine is the sole and immutable source of truth for legal outcomes.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                      Package Ingestion (1–4 Surfaces or Live Camera)                    │
└────────────────────────────────────────┬────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                 OpenCV Image Quality Gate & Blank Image Detector                        │
│   • Laplacian Sharpness Variance (Blur threshold > 40.0)                                │
│   • Specular Glare & Overexposure Ratio (< 15%)                                         │
│   • Resolution & Pixel Density Check                                                    │
│   • Unprinted / Plain Foil Detection (std_dev < 6.0 → Confidence 0.0, REVIEW state)    │
└────────────────────────────────────────┬────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│              Dual-Path Vision & Semantic Extraction Service                             │
│   • Path A: High-Precision OCR & Deterministic Regex Parser                             │
│   • Path B: Local LLM Engine (Ollama / Qwen2.5:7b) + Legal Metrology RAG Search         │
│   • Structured Declarations: MRP, Net Qty, Dates, Mfg/Packer, Country of Origin, USP   │
└────────────────────────────────────────┬────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│          DETERMINISTIC STATUTORY RULE ENGINE (40+ Statutory Rules)                      │
│   • General Declarations: PC-DEC-001 through PC-DEC-010                                 │
│   • Unit Standardization: PC-UNIT-001 (g, kg, ml, l, m, cm, No.)                       │
│   • Cross-Surface Contradiction: PC-CON-001 (e.g. Front 500g vs Back 450g)              │
│   • Schedule Compliance: PC-SCHED-001 (Second Schedule Standard Pack Sizes)             │
│   • Principal Display Panel: PC-FONT-001 (Rule 7 Area & Min Font Height)                │
│   • Special Commodities: PC-EX-001 (Pan Masala RSP), PC-EX-002, PC-ECOM-001             │
└────────────────────────────────────────┬────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                             Statutory Compliance Matrix                                 │
│   🟢 COMPLIANT (Pass)   │   🟡 NEEDS MANUAL REVIEW   │   🔴 POSSIBLE NON-COMPLIANCE     │
└────────────────────────────────────────┬────────────────────────────────────────────────┘
                                         │
             ┌───────────────────────────┴───────────────────────────┐
             ▼                                                       ▼
┌─────────────────────────────────────────┐ ┌─────────────────────────────────────────────┐
│  Inspector Interactive Evidence Viewer  │ │ Inspector Statutory Tools Hub (/rules)      │
│  • High-resolution Canvas Box Overlay   │ │ • 1st Schedule MPE Tolerances               │
│  • Field-by-Field Visual Linkage        │ │ • 5th Schedule Lot Sampling (t-corrected)   │
│  • Manual Correction / Override Trail   │ │ • 2nd Schedule Commodity Standard Sizes     │
│  • Official Legal Metrology PDF Export  │ │ • Rule 7 PDP Area & Font Height Calculator  │
└─────────────────────────────────────────┘ └─────────────────────────────────────────────┘
```

---

## ✨ Key Features & Capabilities

### 1. Multi-Surface & Live Camera Acquisition
- Ingest up to 4 surface photos (`FRONT`, `BACK`, `SIDE`, `TOP`, `BOTTOM`).
- **Live Camera Integration**: Direct WebRTC stream for mobile phones (rear-camera auto-facing) and PC webcams with real-time frame capture.

### 2. OpenCV Image Quality & Blank Detector
- Analyzes Laplacian variance, specular glare percentage, and minimum readable resolution.
- **True Zero-Confidence on Unprinted / Empty Surfaces**: Plain silver foil pouches or blank unprinted photos yield **`0.0%` confidence** and route to `NEEDS MANUAL REVIEW` with `UNVERIFIED_PACKAGE` / `NO_TEXT_DETECTED`, preventing false positive compliance claims.

### 3. Dual-Engine Extraction (OCR + Local LLM RAG)
- **Deterministic Regex Parser**: Instant, air-gapped parsing of standard statutory formats (`₹`, `Rs.`, `Mfd on:`, `Net Wt:`, `PKD:`, `Consumer Care:`, `Country of Origin`).
- **Local Ollama Integration**: Powered by `qwen2.5:7b` for complex multiline packaging text, bilingual labels, and non-standard layout disambiguation.
- **Statutory RAG Engine**: Semantic search across the Gazette Notifications, Rules PDF, and official Legal Metrology FAQs.

### 4. 40+ Statutory Rules Implementation
- Enforces all key provisions of the **Legal Metrology (Packaged Commodities) Rules, 2011**:
  - **Rule 6(1)(a)**: Common generic product name.
  - **Rule 6(1)(b)**: Complete manufacturer / packer name and physical address with pin code.
  - **Rule 6(1)(c)**: Country of origin for imported goods (Rule 6(10) / G.S.R. 881(E)).
  - **Rule 6(1)(d)**: Net quantity in standard SI units (Rule 11/12).
  - **Rule 6(1)(e)**: Month and year of manufacture/pre-packing/import.
  - **Rule 6(1)(f)**: MRP in Indian Rupees inclusive of all taxes (`₹` or `Rs.`, Rule 6(1)(da)).
  - **Rule 6(1)(g)**: Consumer care details (name/designation, address, telephone, and email).
  - **Rule 6(1)(ea)**: Unit Sale Price (USP) mandatory declaration (e.g. `₹ 0.50 / g`).
  - **Rule 7**: Principal Display Panel (PDP) minimum letter/numeral height check against 5 area bands.
  - **Rule 5 & Second Schedule**: Verification against prescribed pack sizes (Biscuits, Tea, Coffee, Edible Oils, Sugar, Cement, etc.).
  - **Fifth Schedule**: Batch/lot sampling verification with allowable $T_1$ limits, zero $T_2$ tolerances, and Student's t-corrected sample mean.

### 5. Multi-Surface Contradiction Detection
- Flags discrepancies across surfaces (e.g., front declares `500 g` while back declares `450 g`) with rule `PC-CON-001`.

### 6. Interactive Inspector Tools Suite (`/rules`)
- **Statutory Rules Catalog**: Searchable and filterable database of 40+ rules with legal text, penalties, and amendment references.
- **First Schedule MPE Calculator**: Instant Maximum Permissible Error tolerance calculation for mass/volume.
- **Fifth Schedule Lot Sampling Evaluator**: Statistical acceptance testing for lot sizes ($n=32, 80, 125$) with Student's t-correction ($\bar{x}_{\text{corr}} = \bar{x} + \frac{2s}{\sqrt{n}}$).
- **Second Schedule Standard Pack Sizes**: Permitted weight/volume validator for 12+ notified commodity classes.
- **Rule 7 PDP Calculator**: Principal Display Panel surface calculation and statutory minimum font height determination.

### 7. Official Legal Metrology Inspection Certificate
- Export complete inspection reports to digitally-styled, printable PDF format containing Government of India / Department of Consumer Affairs header, compliance matrix, bounding box evidence, inspector remarks, and digital verification seal.

---

## 🔍 Defect Inspection Mode (AI & Computer-Vision Surface / Product Defects)

A **separate mode** alongside Legal Metrology (switch with the *Legal Metrology / Defect Inspection* toggle in the navbar). It reuses the platform's inspection, image, audit-trail and PDF infrastructure but has its own pipeline, pages, numbering (`DEF-YYYY-NNNN`) and statistics — legal inspections, dashboard and rule engine are unaffected.

```
Image / Live camera / Video ──► Hybrid defect detector ──► Classify + grade severity ──► Log (DB + audit)
                                                                                      │
             Inspector feedback (confirm / reject / relabel) ──► labelled training samples
                                                                                      ▼
                                        Analytics: frequency, trend, hotspots, per-product, root-cause hints
```

| Defect | Classical OpenCV method (no training data needed) |
| :--- | :--- |
| Scratch | Black-hat / top-hat line extraction + oriented line filter; straight strokes |
| Crack | Same line extraction; tortuous / branching dark strokes |
| Dent | Local shading anomaly against a masked large-scale illumination model |
| Discolouration | CIELAB chroma shift vs surface median (or full ΔE vs golden sample) |
| Dimensional anomaly | Product contour vs golden sample (aspect, area, shape) or edge notches via convexity defects |

- **Golden reference (optional):** a defect-free sample of the same product. It is aligned (ORB + homography) and used to suppress printed designs/logos, match colour exactly and compare dimensions. **Upload one for printed or branded products**, otherwise artwork can be reported as defects.
- **Deep-learning plug-in:** set `DEFECT_MODEL_PATH` to a YOLOv8 ONNX export (e.g. trained on NEU-DET / GC10-DET / MVTec AD). It runs through OpenCV DNN — no PyTorch or onnxruntime needed. Class names come from `DEFECT_MODEL_CLASSES` (comma separated) or a sidecar `<model>.names` file and are mapped onto the taxonomy above. `DEFECT_DETECTOR_BACKEND=hybrid` (default) merges model + OpenCV detections; `opencv` / `onnx` force one engine.
- **Real-time / edge:** live camera mode streams downscaled frames (≈100–150 ms per frame on a laptop CPU) with on-screen boxes, FPS and latency; videos are sampled (`sample_fps`, `max_frames`) and frames with defects are kept as evidence.
- **Retraining loop:** every confirm / relabel / reject saves a crop to `storage/defect_samples/<TYPE>/` (`_false_positive/` for rejects) and a line in `manifest.jsonl`.
- **Outcome:** `DEFECTIVE` if any confident high/critical defect, `REVIEW` for medium defects or under/over-exposed frames, otherwise `PASS`. Rejected detections are ignored.

Pages: `/defects` (new inspection + recent list), `/defects/[id]` (overlay, defect log, feedback, PDF), `/defects/analytics` (KPIs, trend, hotspots, product breakdown, root-cause hints, searchable log).

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/defects/inspections` | Create a defect inspection |
| `GET` | `/api/v1/defects/inspections` / `/{id}` | List / detail (detections, images, root-cause hints) |
| `POST` | `/api/v1/defects/inspections/{id}/reference` | Upload golden (defect-free) sample |
| `POST` | `/api/v1/defects/inspections/{id}/analyze` | Analyse an uploaded image |
| `POST` | `/api/v1/defects/inspections/{id}/capture` | Analyse a base64 camera snapshot |
| `POST` | `/api/v1/defects/inspections/{id}/video` | Sample and analyse a video |
| `POST` | `/api/v1/defects/analyze-frame` | Stateless live-frame detection (camera loop) |
| `POST` | `/api/v1/defects/detections/{id}/feedback` | `CONFIRM` / `REJECT` / `RELABEL` a detection |
| `GET` | `/api/v1/defects/inspections/{id}/overlay/{image_id}` | Annotated image (data URL) |
| `GET` | `/api/v1/defects/inspections/{id}/report` | Defect inspection PDF |
| `POST` | `/api/v1/defects/inspections/{id}/finalize` | Sign off (optional outcome override) |
| `GET` | `/api/v1/defects/analytics?days=30&product=` | Frequency, severity, trend, hotspots, products, root causes |
| `GET` | `/api/v1/defects/log` | Filterable detection log |
| `GET` | `/api/v1/defects/status` | Detector engine / model status |
| `POST` | `/api/v1/defects/demo/seed` | Seed synthetic defect samples |

---

## 🛠️ Technology Stack

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   FULL TECH STACK                                      │
├───────────────────┬───────────────────┬─────────────────────────┬──────────────────────┤
│  Frontend Layer   │   Backend Layer   │    Vision & AI Layer    │  DevOps & Testing    │
│  (Next.js 16/TS)  │  (FastAPI/Py3.13) │ (OpenCV / Ollama / RAG) │  (Docker / PyTest)   │
└───────────────────┴───────────────────┴─────────────────────────┴──────────────────────┘
```

| Layer / Domain | Technology | Purpose / Application |
| :--- | :--- | :--- |
| **Frontend Framework** | [Next.js 16](https://nextjs.org/) (App Router) | Modern React framework with server-side rendering, routing, and asset optimization |
| **UI Library & Language** | [React 19](https://react.dev/) + [TypeScript 5](https://www.typescriptlang.org/) | Declarative component hierarchy with strict end-to-end type safety |
| **Styling & Design System** | [Tailwind CSS 3](https://tailwindcss.com/) | Custom Notion-inspired, high-density government inspector design system |
| **Icons & Visuals** | [Lucide React](https://lucide.dev/) | Clean, accessible vector icons for compliance badges, status chips, and tools |
| **Device Hardware Access** | [WebRTC MediaDevices API](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices) | Native in-browser live camera capture (rear-facing mobile and PC webcam support) |
| **Backend REST API** | [FastAPI 0.115+](https://fastapi.tiangolo.com/) | High-performance asynchronous Python API framework with automatic OpenAPI docs |
| **Runtime Language** | [Python 3.13+](https://www.python.org/) | Latest Python release with performance improvements and native typing |
| **Data Validation & Schemas** | [Pydantic v2](https://docs.pydantic.dev/) | High-speed data parsing, strict statutory model validation, and schema definitions |
| **Database & ORM** | [SQLAlchemy 2.0](https://www.sqlalchemy.org/) + [SQLite](https://www.sqlite.org/) | Relational database abstraction with zero-configuration persistence (PostgreSQL compatible) |
| **Computer Vision Engine** | [OpenCV](https://opencv.org/) (`opencv-python-headless`) | Laplacian blur variance estimation, specular glare masking, and MSER region proposals |
| **Numerical Processing** | [NumPy](https://numpy.org/) | High-speed matrix operations, luminance calculations, and statistical sampling math |
| **Image Manipulation** | [Pillow (PIL)](https://python-pillow.org/) | Multi-surface format decoding, EXIF orientation correction, and thumbnail generation |
| **Local LLM Runtime** | [Ollama](https://ollama.com/) | Air-gapped, on-premise local model inference (Qwen2.5:7b, LLaVA vision models) |
| **Statutory RAG Engine** | [Scikit-learn](https://scikit-learn.org/) (TF-IDF + Cosine) | Vector semantic retrieval across Gazette amendments, PCR 2011 PDF, and official FAQs |
| **Asynchronous HTTP Client** | [HTTPX](https://www.python-httpx.org/) | Non-blocking async client for LLM communication with automatic offline fallbacks |
| **PDF Dossier Generation** | [ReportLab](https://www.reportlab.com/) | Programmatic generation of official Government of India inspection certificates |
| **Automated Testing** | [PyTest](https://pytest.org/) + [AnyIO](https://anyio.readthedocs.io/) | Async unit testing suite with 19 comprehensive test cases |
| **Containerization** | [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/) | Multi-stage containerized deployments for backend, frontend, and local LLM runtime |

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python**: 3.11+ (Tested on Python 3.13)
- **Node.js**: 18.x or 20.x (Tested with npm 10+)
- **Optional (for Local LLM)**: Docker & Docker Compose or [Ollama](https://ollama.com)

---

### Option 1: Running Locally (Fastest)

#### 1. Start the Backend (FastAPI on Port 8080)
```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment (optional but recommended)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run unit tests to verify system integrity
python -m pytest tests

# Start FastAPI application
python -m uvicorn app.main:app --port 8080 --host 0.0.0.0 --reload
```
- **API Swagger Docs**: [http://localhost:8080/docs](http://localhost:8080/docs)
- **API Health Check**: [http://localhost:8080/api/health](http://localhost:8080/api/health)

#### 2. Start the Frontend (Next.js on Port 3000)
```bash
# Open a new terminal and navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Next.js development server
npm run dev
```
- **Web Platform**: [http://localhost:3000](http://localhost:3000)
- **Rules & Inspector Tools**: [http://localhost:3000/rules](http://localhost:3000/rules)
- **Dashboard**: [http://localhost:3000/dashboard](http://localhost:3000/dashboard)

---

### Option 2: Docker Compose (Full Stack with Local LLM)

```bash
# Start Backend, Frontend, and Ollama Local LLM container
docker-compose up -d --build

# Pull the Qwen2.5 7B model inside the Ollama container
docker exec -it lm-ollama ollama pull qwen2.5:7b
```

Access points:
- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:8080](http://localhost:8080)
- Ollama LLM Service: [http://localhost:11434](http://localhost:11434)

---

## 🧪 Automated Testing Suite

The repository includes a comprehensive `pytest` test suite with 17 test cases validating all aspects of image processing, parsing, rule engine logic, statutory schedules, and API endpoints.

```bash
cd backend
python -m pytest tests -v
```

### Test Coverage Highlights:
- `test_image_quality.py`: Sharpness detection, blur rejection, specular glare evaluation, plain foil / blank pouch 0.0 confidence classification.
- `test_declaration_service.py`: Standard declaration regex extraction (MRP, Net Qty, Dates, Mfg details, USP, Country of Origin).
- `test_rule_engine.py`: 40+ statutory rules determinism, mandatory missing declaration flags, non-standard unit rejection, contradiction detection, and unprinted package behavior.
- `test_rag_and_llm.py`: Second Schedule standard pack sizes, First Schedule MPE error calculations, Fifth Schedule lot sampling evaluation, Rule 7 PDP font calculations, RAG vector retrieval, and Ollama fallback mechanisms.
- `test_api.py`: FastAPI endpoints, demo seeding, inspection creation, and review workflows.

---

## 📖 API Endpoints Reference

### Core Inspection & Compliance
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/inspections` | Upload package images (1–4 surfaces) and execute full compliance audit |
| `GET` | `/api/v1/inspections` | List inspection registry with pagination, search, and status filters |
| `GET` | `/api/v1/inspections/{id}` | Retrieve comprehensive inspection dossier, compliance matrix & evidence |
| `POST` | `/api/v1/reviews/{id}` | Submit inspector review (`CONFIRM`, `CORRECT`, `REJECT`, `REQUEST_IMAGE`) |
| `GET` | `/api/v1/reports/{id}/pdf` | Generate & download official Legal Metrology PDF inspection certificate |
| `POST` | `/api/v1/demo/seed` | Seed pre-configured statutory benchmark test cases |

### Statutory Inspector Tools
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/tools/rules-database` | Query statutory rules catalog with filters (category, rule ID, mandatory) |
| `POST` | `/api/v1/tools/mpe-calculate` | Calculate First Schedule Maximum Permissible Error (MPE) for given net qty |
| `POST` | `/api/v1/tools/lot-sample-evaluate` | Evaluate Fifth Schedule lot sampling ($n=32, 80, 125$) with Student's t-test |
| `POST` | `/api/v1/tools/pdp-font-check` | Rule 7 Principal Display Panel area & minimum font/numeral height calculator |
| `GET` | `/api/v1/tools/schedules` | Query Second Schedule notified commodity pack sizes |

---

## 📂 Repository Structure

```
prototype/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI application entrypoint & middleware
│   │   ├── core/                       # Config, database setup, JWT auth, security
│   │   ├── models/                     # SQLAlchemy models (Inspection, Image, Declaration, Rule, Result, Audit)
│   │   ├── schemas/                    # Pydantic validation models & tool request schemas
│   │   ├── api/                        # REST API routers (auth, inspections, reviews, reports, dashboard, tools, demo)
│   │   ├── services/
│   │   │   ├── image_quality.py        # OpenCV Laplacian blur, glare, and blank image detection
│   │   │   ├── ocr_service.py          # OCR span localization & bounding box extraction
│   │   │   ├── declaration_service.py  # Deterministic regex statutory declaration parser
│   │   │   ├── llm_service.py          # Ollama local LLM integration (qwen2.5:7b)
│   │   │   ├── rag_service.py          # Legal Metrology RAG vector retrieval service
│   │   │   ├── rule_engine.py          # 40+ statutory rules engine & contradiction detector
│   │   │   ├── mpe_calculator.py       # First & Fifth Schedule MPE / sampling statistics
│   │   │   ├── schedule_checker.py     # Second Schedule prescribed pack size validator
│   │   │   ├── pdp_calculator.py       # Rule 7 Principal Display Panel font height calculator
│   │   │   └── pdf_service.py          # Official ReportLab inspection certificate generator
│   │   └── data/                       # Compiled statutory rules JSON
│   ├── tests/                          # 17 automated pytest test suites
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx              # Root application layout
│   │   │   ├── page.tsx                # Landing page & quick workflow actions
│   │   │   ├── dashboard/page.tsx      # Analytics & KPI dashboard
│   │   │   ├── inspections/page.tsx    # Inspection registry with status filters
│   │   │   ├── inspections/new/page.tsx# New inspection creation & live camera capture
│   │   │   ├── inspections/[id]/page.tsx# Inspection dossier, matrix & evidence viewer
│   │   │   └── rules/page.tsx          # Statutory Rules Book & Inspector Tools Suite
│   │   ├── components/                 # Navbar, CameraCaptureModal, EvidenceViewer, ComplianceMatrix, ReviewModal
│   │   ├── lib/                        # API client & TypeScript interfaces
│   │   └── styles/                     # Modern design system & Tailwind tokens
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
│
├── SIH26034_RULES.json                 # 40+ statutory legal metrology rules specification
├── SIH26034_RULES.csv                  # Tabular rules register
├── SOURCE_REGISTER.csv                 # Official Gazette notifications & legal source register
├── Book_on_Legal_Metrology...pdf       # Reference statutory handbook
├── FAQs_on_Packaged_Commodities...pdf   # Official ministry clarifications
├── data.md                             # Comprehensive statutory domain knowledge & mappings
├── DESIGN.md                           # Architecture specification & schema design
├── work.md                             # Hackathon execution milestones & deliverables
├── docker-compose.yml                  # Multi-container orchestration (Backend + Frontend + Ollama)
└── README.md                           # Master project documentation
```

---

## 🏛️ Statutory References & Legal Basis

1. **Legal Metrology Act, 2009 (No. 1 of 2010)** — Sections 18, 36 (Penalties for non-standard packages).
2. **Legal Metrology (Packaged Commodities) Rules, 2011** (G.S.R. 202(E) dated 07-03-2011).
3. **G.S.R. 881(E) (2025/2026 Amendment)** — Mandatory Unit Sale Price (USP) declaration, e-commerce digital disclosures, and non-standard packaging exemptions.
4. **G.S.R. 128(E)** — Electronic labeling provisions for specified hardware commodities.
5. **G.S.R. 312(E) & G.S.R. 418(E)** — Pan Masala mandatory Retail Sale Price (RSP) standardization and Second Schedule commodity updates.

---

## 👥 Contributors & Hackathon Team

Developed for the **Smart India Hackathon 2026** (Problem Statement: `SIH26034`).

*Department of Consumer Affairs, Ministry of Consumer Affairs, Food & Public Distribution, Government of India.*
