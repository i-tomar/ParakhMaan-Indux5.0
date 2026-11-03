# ParakhMaan Design System (PDS)
### *Industrial Precision, Paper-Calm Tactility, and High-Signal Safety*

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                    PARAKHMAAN DESIGN SYSTEM (v2.0)                     │
  │                  "Industrial Ergonomics at Edge Speed"                 │
  ├───────────────────┬───────────────────┬────────────────────────────────┤
  │ 🎨 Tone           │ 📐 Geometry       │ ⚡ Performance                  │
  │  • Calm Paper     │  • 12px Card Rad  │  • Sub-16ms Paint Latency      │
  │  • Dark Ink       │  • Hairline Grid  │  • Tabular Numerical Alignment │
  │  • Industrial Pop │  • Dense Padding  │  • Hardware-Accurate Sync      │
  └───────────────────┴───────────────────┴────────────────────────────────┘
```

---

## 1. Vision & Design Principles

ParakhMaan is an industrial visual inspection platform deployed in factory floor environments, quality control laboratories, and supervisor oversight stations. The design language balances **information density**, **operator ergonomic calm**, and **immediate safety signal clarity**.

### Core Tenets

1. **Paper-Calm Canvas, High-Signal Foreground**
   - The operating surface uses a warm, glare-reducing off-white canvas (`#f6f5f4`) with crisp white card containers (`#ffffff`) and hairline borders (`#e6e6e6`).
   - Saturated colors are reserved exclusively for defect localization, safety alerts, and inspection outcomes. The chrome stays quiet so defects pop instantly.

2. **Technical Honesty & Operational Transparency**
   - No black boxes or ambiguous labels. Every metric indicates units ($\text{mm}$, $\text{ms}$, $\text{FPS}$, $\%$), every calculation reveals its basis, and simulated hardware states are boldly labeled with a dedicated `SIMULATED` badge.

3. **Sub-Millimeter Optical Synchronization**
   - All visual overlay components (`DefectOverlay`, `EvidenceViewer`) use normalized SVG coordinate projections (`xMidYMid meet`) synchronized down to the exact pixel with OpenCV backend detection arrays.

4. **Dual-Mode Visual Independence**
   - Seamlessly houses both **Surface Defect Inspection Mode** (Amber/Blue tech palette) and **Legal Metrology Packaging Compliance Mode** (Statutory Blue palette) within a single unified application shell.

---

## 2. Color System & Semantic Tokens

### 2.1 Foundation Tokens
The interface relies on CSS Custom Properties defined in `frontend/src/app/globals.css`:

```css
:root {
  /* Surfaces & Canvas */
  --canvas: #f6f5f4;         /* Glare-reducing warm off-white app canvas */
  --surface: #ffffff;        /* Pure white card and modal surface */
  --hairline: #e6e6e6;       /* Subtle 1px structural dividing lines */

  /* Ink Hierarchy (Text & Glyph Contrast) */
  --ink: #000000;            /* Primary titles, headings, and high-contrast text */
  --ink-secondary: #31302e;  /* Secondary body text, table data, and labels */
  --ink-muted: #615d59;      /* Captions, metric hints, and disabled placeholders */
  --ink-faint: #a39e98;      /* Borders, scrollbars, and tertiary dividers */

  /* Brand & Navigation */
  --primary: #0075de;        /* Confident industrial engineering blue */
  --primary-active: #005bab; /* Pressed state blue */
  --secondary: #213183;      /* Deep navy for structural accents and banners */
  --on-primary: #ffffff;     /* High-contrast text on primary fills */
}
```

---

### 2.2 Defect Taxonomy & Color Synchronization
Defect colors in the frontend UI (`frontend/src/lib/defects.ts`) are **strictly byte-synchronized** with backend OpenCV visualization engines (`backend/app/services/defect_detection_service.py`):

| Defect Class | UI Hex Color | Backend BGR Tuple | Semantic Role |
| :--- | :--- | :--- | :--- |
| **SCRATCH** | `#0075de` | `(222, 117, 0)` | Surface abrasion, linear scuffs, tooling marks |
| **CRACK** | `#c0186b` | `(107, 24, 192)` | Material fracture, structural parting line |
| **DENT** | `#e07a00` | `(0, 122, 224)` | Impact depression, contour deformation |
| **DISCOLOURATION** | `#0a9a8f` | `(143, 154, 10)` | Thermal scorch, chemical stain, finish flaw |
| **DIMENSIONAL_ANOMALY** | `#7a3fd0` | `(208, 63, 122)` | Length/width out of tolerance, contour skew |
| **UNKNOWN_ANOMALY** | `#6d7a12` | `(18, 122, 109)` | Zero-shot PatchCore heatmap novelty capture |

---

### 2.3 Decision & Safety State Tokens

```css
/* Line Decision Tokens */
--decision-accept-bg: #dcfce7;  /* Tailwind green-100 */
--decision-accept-fg: #166534;  /* Deep emerald */
--decision-reject-bg: #fee2e2;  /* Tailwind red-100 */
--decision-reject-fg: #991b1b;  /* High-alert ruby red */
--decision-review-bg: #fef3c7;  /* Tailwind amber-100 */
--decision-review-fg: #854d0e;  /* Warm cautionary amber */

/* Simulation Mode Token */
--simulated-bg: #f3e8ff;        /* Muted lavender-purple */
--simulated-fg: #6b21a8;        /* Deep technical violet */
```

---

## 3. Typography & Numerical Hierarchy

ParakhMaan uses **Inter** with native browser system font fallbacks (`-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `Roboto`). 

### Critical Rule for Industrial Data: Tabular Numerals
All engineering measurements, defect coordinates, timestamps, confidence scores, and line FPS counters **MUST** use the `tabular-nums` CSS utility to prevent visual jitter during live updates:

```tsx
<p className="text-2xl font-bold tracking-tight text-[#000000] tabular-nums">
  {value} mm
</p>
```

### Type Scale

| Token | Size / Line Height | Weight | Tracking | Usage |
| :--- | :--- | :--- | :--- | :--- |
| `display-hero` | 26px / 1.25 | Bold (700) | `-0.025em` | Page Titles, Primary System Headers |
| `heading-section`| 18px / 1.35 | Bold (700) | `-0.015em` | Section Titles, Modal Headers |
| `card-title` | 14px / 1.40 | Semibold (600) | `normal` | Card Headers, Widget Titles |
| `body-default` | 13px / 1.50 | Regular (400) | `normal` | Standard Body, Inspector Notes, Descriptions |
| `label-meta` | 11px / 1.40 | Medium (500) | `normal` | Field Labels, Badge Text, Stat Hints |
| `micro-badge` | 10px / 1.20 | Bold (700) | `+0.05em` | `SIMULATED` pill, Severity tags, Status flags |

---

## 4. Elevation, Radii & Grid System

### Layered Elevation
Shadows are rendered with multiple subtle, realistic occlusion layers rather than harsh black blurs:

```css
/* Hairline Flat - Default for clean cards */
.elevation-0 {
  border: 1px solid var(--hairline);
}

/* Floating Surface - Popovers, Tooltips, Active Modals */
.elevation-1 {
  border: 1px solid var(--hairline);
  box-shadow: 
    rgba(0,0,0,0.01) 0 0.175px 1.041px,
    rgba(0,0,0,0.02) 0 0.8px 2.925px,
    rgba(0,0,0,0.027) 0 2.025px 7.847px,
    rgba(0,0,0,0.04) 0 4px 18px;
}

/* Modal Dialog Backdrop Elevation */
.elevation-2 {
  border: 1px solid var(--hairline);
  box-shadow: rgba(0, 0, 0, 0.08) 0 20px 45px;
}
```

### Border Radii
- **`rounded-lg` (8px):** Buttons, Text Inputs, Form Controls, Badge Pills.
- **`rounded-xl` (12px):** Metric Tiles (`Stat`), Content Cards (`Card`), Modal Shells.
- **`rounded-full` (9999px):** Decision Pills, Avatars, Active Status Dots.

---

## 5. Component System Specifications

### 5.1 Application Shell (`AppShell.tsx`)
- **Structure:** Left-hand 240px fixed navigation rail with mobile drawer fallback.
- **Categorization:** Operations, Production, Quality, AI Models, and Optional Modules.
- **Session Capsule:** Compact footer capsule rendering the authenticated user's email, role badge (`INSPECTOR`, `SUPERVISOR`, `ADMIN`), and instant sign-out control.

### 5.2 Metrics Tile (`Stat.tsx`)
```tsx
<div className="bg-white rounded-xl elevation-0 px-4 py-3">
  <p className="text-[11px] font-medium text-[#615d59]">{label}</p>
  <p className="text-2xl font-bold tracking-tight text-[#000000] mt-1 tabular-nums">{value}</p>
  {hint && <p className="text-[11px] text-[#615d59] mt-0.5">{hint}</p>}
</div>
```

### 5.3 Interactive Defect Overlay (`DefectOverlay.tsx`)
- **Rendering:** Responsive `<svg>` overlay matching container aspect ratio via `preserveAspectRatio="xMidYMid meet"`.
- **Bounding Polygon:** High-contrast 2px-3px dynamic stroke with semi-transparent fill (`fill-opacity="0.15"`).
- **Interactive Inspection:** Hover or click highlights the corresponding row in `DefectTable.tsx`.
- **Reviewed State:** Discarded or rejected detections attenuate to 35% opacity (`opacity-35`) with strike-through annotations.

### 5.4 Decision Badge Matrix (`DecisionBadge.tsx`)
```
┌────────────────────┬──────────────────────────────────────────────────┐
│ DECISION           │ VISUAL ENCODING                                  │
├────────────────────┼──────────────────────────────────────────────────┤
│ ACCEPT             │ [ ● Accept ]         (bg-green-100 text-green-800)│
│ REJECT             │ [ ✕ Reject ]         (bg-red-100 text-red-800)    │
│ MANUAL_REVIEW      │ [ ▲ Manual Review ]  (bg-amber-100 text-amber-800)│
│ SIMULATED          │ [ SIMULATED ]        (bg-purple-100 text-purple-800)│
└────────────────────┴──────────────────────────────────────────────────┘
```

---

## 6. Motion & Visual Ergonomics

ParakhMaan enforces a **low-distraction motion policy**:
- **Durations:** 150ms to 200ms `ease-in-out` for all micro-interactions (button hover, modal fade, drawer slide).
- **Live Video Pulsing:** Continuous live streams feature a subtle 2s pulsing indicator (`animate-pulse`) to confirm frame reception without distracting operator attention.
- **Reduced Motion:** Fully honors `prefers-reduced-motion: reduce` by disabling non-essential transitions.

---

## 7. Factory-Floor Accessibility & Ergonomics

1. **Touch-Target Sizing:** All critical buttons (e.g. *Trigger Capture*, *Accept*, *Reject*, *Arm Hardware*) feature a minimum hit-box of $40\text{px} \times 40\text{px}$ for glove-wearing industrial operators.
2. **Colorblind-Safe Redundancy:** No state relies on color alone:
   - Green `Accept` is always paired with a checkmark icon or text label.
   - Red `Reject` is always paired with a warning cross or triangle.
   - Text descriptions accompany all severity pills.
3. **High Ambient Light Contrast:** Dark text tokens (`#000000`, `#31302e`) exceed WCAG AAA contrast ratios (> 7:1) on white surfaces, guaranteeing legibility under high factory bay lighting.

---

## 8. UX Copywriting & Industrial Standards

| Avoid Generic Software Phrases | Use ParakhMaan Industrial Terms |
| :--- | :--- |
| "Something went wrong" | "Actuator link failed: COM port unavailable" |
| "Processing..." | "Running YOLO11n-seg & PatchCore inference (p50: 70ms)" |
| "Success" | "Unit #304 verified: ACCEPT (within ±0.20mm tolerance)" |
| "Our AI found defects" | "2 anomalies detected (1 Crack, 1 Dent; Max Confidence: 94%)" |
| "Cause identified" | "Machine M-02 shows statistically significant defect association ($p < 0.001$, Fisher test)" |
