"""Time the full inspection pipeline on real images, on THIS machine only.

    python -m scripts.benchmark_edge --samples storage/demo_samples/metal_nut --product metal_nut --runs 200

Uses the same engine call as the API (segmentation + anomaly + classical checks + fusion). The
result is written to storage/reports/benchmark_edge.json and shown on the Model Performance page.
It describes the device it ran on and nothing else: no Jetson, Raspberry Pi or other edge device
has been measured, and none is claimed.
"""
import argparse
import glob
import json
import os
import platform
import statistics
import time
from datetime import datetime, timezone

import cv2
import onnxruntime as ort

from app.core.config import settings
from app.services.inference.engine import engine


def pct(values, q):
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(q * (len(values) - 1))))], 2)


def device() -> dict:
    info = {"machine": platform.machine(), "system": platform.system(), "release": platform.release(),
            "python": platform.python_version(), "onnxruntime": ort.__version__, "opencv": cv2.__version__,
            "cpu_count": os.cpu_count(), "providers": ort.get_available_providers()}
    if platform.system() == "Darwin":
        try:
            import subprocess
            info["cpu"] = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
        except Exception:  # noqa: BLE001
            pass
    elif os.path.exists("/proc/cpuinfo"):
        for line in open("/proc/cpuinfo", encoding="utf-8", errors="ignore"):
            if line.lower().startswith(("model name", "hardware")):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
    info["in_container"] = os.path.exists("/.dockerenv")
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", required=True, help="folder of real images (searched recursively)")
    ap.add_argument("--product", default="metal_nut")
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--out", default=os.path.join(settings.REPORTS_DIR, "benchmark_edge.json"))
    ap.add_argument("--label", default="", help="free text, e.g. 'docker linux/arm64 on M1 Pro'")
    args = ap.parse_args()

    paths = sorted(p for p in glob.glob(os.path.join(args.samples, "**", "*"), recursive=True)
                   if p.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")))
    if not paths:
        raise SystemExit(f"No images under {args.samples}")
    images = [cv2.imread(p) for p in paths]
    engine.inspect(images[0], args.product, want_heatmap=False)  # warm-up, not counted

    total, stages = [], {}
    started = time.perf_counter()
    for i in range(args.runs):
        result = engine.inspect(images[i % len(images)], args.product, want_heatmap=False)
        total.append(result["latency_ms"])
        for name, ms in (result.get("timings") or {}).items():
            stages.setdefault(name, []).append(ms)
    wall = time.perf_counter() - started

    report = {
        "data": f"real images: {len(paths)} files from {args.samples}, cycled for {args.runs} runs",
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": args.label or None,
        "device": device(),
        "product": args.product,
        "models": engine.status(),
        "runs": args.runs,
        "frame_sizes": sorted({f"{im.shape[1]}x{im.shape[0]}" for im in images}),
        "latency_ms": {"p50": pct(total, 0.5), "p95": pct(total, 0.95), "p99": pct(total, 0.99),
                       "mean": round(statistics.mean(total), 2), "max": round(max(total), 2)},
        "throughput_fps_sequential": round(args.runs / wall, 2),
        "stage_ms_p50": {k: pct(v, 0.5) for k, v in stages.items()},
        "not_measured": "No embedded edge device (Jetson, Raspberry Pi, industrial PC) was available; "
                        "figures apply only to the device above.",
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({k: report[k] for k in ("latency_ms", "throughput_fps_sequential", "stage_ms_p50")}, indent=1))


if __name__ == "__main__":
    main()
