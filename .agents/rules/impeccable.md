# Impeccable Design System Guidelines

This workspace enforces the **ParakhMaan Design System (PDS v2.0)** documented in `DESIGN.md`.

## Active Guardrails

1. **Tokens Over Hardcoded Values**:
   - Always reference predefined semantic variables from `globals.css` or Tailwind tokens (`--canvas`, `--surface`, `--primary`, `--ink`, `--hairline`).
   - Do NOT introduce uncalibrated ad-hoc hex values.

2. **Defect Color Synchronization**:
   - Defect bounding boxes, overlays, tags, and charts must preserve the exact 6-class color mapping synchronized with OpenCV BGR:
     - `SCRATCH`: `#0075de`
     - `CRACK`: `#c0186b`
     - `DENT`: `#e07a00`
     - `DISCOLOURATION`: `#0a9a8f`
     - `DIMENSIONAL_ANOMALY`: `#7a3fd0`
     - `UNKNOWN_ANOMALY`: `#6d7a12`

3. **Tabular Numerals for Engineering Metrics**:
   - All measurements ($\text{mm}$), tolerances, latencies ($\text{ms}$), frame rates ($\text{FPS}$), timestamps, and confidence percentages **MUST** include the `tabular-nums` class to eliminate layout jitter.

4. **Line Decision & State Badge Contracts**:
   - `ACCEPT` → Emerald / Green (`bg-green-100 text-[#166534]`)
   - `REJECT` → Red / Ruby (`bg-red-100 text-[#991B1B]`)
   - `MANUAL_REVIEW` → Amber (`bg-amber-100 text-[#854D0E]`)
   - `SIMULATED` → Purple (`bg-[#f3e8ff] text-[#6b21a8]`)

5. **Visual Density & Elevation**:
   - Rely on `.elevation-0` (hairline flat), `.elevation-1` (layered shadow), and `.elevation-2` (modal overlay).
   - Maintain minimum $40\text{px} \times 40\text{px}$ touch targets for factory-floor operator ergonomics.
