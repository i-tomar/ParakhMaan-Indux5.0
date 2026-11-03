# Frontend Design & UI Standards (Impeccable Active)

All UI development in this directory must strictly comply with the **ParakhMaan Design System (PDS v2.0)** defined in `../DESIGN.md`.

## Mandatory Frontend Rules:
1. **Design Tokens:** Use `--canvas`, `--surface`, `--primary`, `--ink`, `--hairline` from `src/app/globals.css`.
2. **Tabular Numerals:** Always apply `tabular-nums` on metrics, coordinates, timestamps, and percentages.
3. **Defect Color Coding:** Synchronize strictly with `src/lib/defects.ts` and OpenCV BGR arrays.
4. **Touch & Glove Ergonomics:** Minimum $40\text{px} \times 40\text{px}$ touch targets for action buttons.
5. **Low-Distraction Motion:** Restrict transitions to 150ms-200ms `ease-in-out`.
