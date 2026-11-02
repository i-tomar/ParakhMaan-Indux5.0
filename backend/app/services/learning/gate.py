"""Promotion gate. A candidate replaces production only if it clears every criterion on the same
fixed holdout. Thresholds are explicit so a refusal can be explained and audited."""
from typing import Any, Dict, List, Optional

# metric -> (direction, largest allowed regression against production)
ANOMALY_CRITERIA = {"image_auroc": ("higher", 0.0), "recall": ("higher", 0.02), "false_reject_rate": ("lower", 0.02)}
SEGMENTATION_CRITERIA = {"map50": ("higher", 0.0), "recall": ("higher", 0.02), "false_reject_rate": ("lower", 0.02)}
MIN_HOLDOUT = {"good": 3, "defective": 3}


def evaluate_gate(kind: str, candidate: Dict[str, Any], production: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    criteria = ANOMALY_CRITERIA if kind == "ANOMALY" else SEGMENTATION_CRITERIA
    checks: List[Dict[str, Any]] = []

    for group, minimum in MIN_HOLDOUT.items():
        found = int(candidate.get(f"holdout_{group}", 0))
        checks.append({"check": f"holdout_{group}", "candidate": found, "required": minimum, "passed": found >= minimum})

    for metric, (direction, tolerance) in criteria.items():
        value = candidate.get(metric)
        if value is None:
            checks.append({"check": metric, "candidate": None, "passed": False, "note": "metric missing"})
            continue
        if not production or production.get(metric) is None:
            checks.append({"check": metric, "candidate": value, "production": None, "passed": True,
                           "note": "no production baseline"})
            continue
        baseline = production[metric]
        limit = baseline - tolerance if direction == "higher" else baseline + tolerance
        passed = value >= limit if direction == "higher" else value <= limit
        checks.append({"check": metric, "candidate": value, "production": baseline, "limit": round(limit, 4), "passed": passed})

    return {"passed": all(c["passed"] for c in checks), "checks": checks}
