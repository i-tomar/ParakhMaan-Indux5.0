"""Manufacturing analytics over production units. All numbers are computed from stored rows."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.all_models import DefectDetection
from app.models.industrial import Batch, Machine, Product, ProductionLine, ProductionUnit, QualityAlert
from app.services.analytics.spc import association, p_chart
from app.services.defect_analytics_service import ROOT_CAUSE_KB, GENERIC_KB, _hotspot

CORRELATION_NOTE = (
    "These figures show statistical association in recorded data. They do not prove a cause. "
    "Confirm on the shop floor before changing the process."
)


def effective_decision(unit: ProductionUnit) -> str:
    return unit.final_decision or unit.decision


def is_flagged(unit: ProductionUnit) -> bool:
    """Nonconforming signal for trends and root cause: rejected, or still awaiting review.

    Counting only REJECT hid every anomaly-only finding (which goes to MANUAL_REVIEW by policy).
    A reviewer who accepts the part sets final_decision=ACCEPT and removes it from the count.
    """
    return effective_decision(unit) != "ACCEPT"


def load_units(
    db: Session, days: int = 30, product_id: Optional[str] = None, batch_id: Optional[str] = None,
    machine_id: Optional[str] = None, line_id: Optional[str] = None, shift: Optional[str] = None,
    include_synthetic: bool = True,
) -> List[ProductionUnit]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None)
    q = db.query(ProductionUnit).filter(ProductionUnit.inspected_at >= since)
    for column, value in ((ProductionUnit.product_id, product_id), (ProductionUnit.batch_id, batch_id),
                          (ProductionUnit.machine_id, machine_id), (ProductionUnit.line_id, line_id),
                          (ProductionUnit.shift, shift)):
        if value:
            q = q.filter(column == value)
    if not include_synthetic:
        q = q.filter(ProductionUnit.is_synthetic.is_(False))
    return q.order_by(ProductionUnit.inspected_at).all()


def detections_for(db: Session, units: List[ProductionUnit]) -> List[DefectDetection]:
    ids = [u.id for u in units]
    rows: List[DefectDetection] = []
    for start in range(0, len(ids), 500):
        rows += db.query(DefectDetection).filter(DefectDetection.unit_id.in_(ids[start:start + 500]),
                                                 DefectDetection.reviewer_status != "REJECTED").all()
    return rows


def summarise(units: List[ProductionUnit]) -> Dict[str, Any]:
    counts = Counter(effective_decision(u) for u in units)
    n = len(units)
    latencies = sorted(u.latency_ms for u in units if u.latency_ms is not None)
    return {
        "units": n,
        "accepted": counts.get("ACCEPT", 0),
        "rejected": counts.get("REJECT", 0),
        "manual_review": counts.get("MANUAL_REVIEW", 0),
        "first_pass_yield": round(counts.get("ACCEPT", 0) / n, 4) if n else None,
        "rejection_rate": round(counts.get("REJECT", 0) / n, 4) if n else None,
        "review_share": round(counts.get("MANUAL_REVIEW", 0) / n, 4) if n else None,
        "flagged_rate": round(sum(1 for u in units if is_flagged(u)) / n, 4) if n else None,
        "latency_ms_p50": round(latencies[len(latencies) // 2], 1) if latencies else None,
        "synthetic_units": sum(1 for u in units if u.is_synthetic),
    }


def pareto(detections: List[DefectDetection]) -> List[Dict[str, Any]]:
    counts = Counter(d.defect_type for d in detections)
    total = sum(counts.values())
    rows, running = [], 0
    for name, count in counts.most_common():
        running += count
        rows.append({"defect_type": name, "count": count, "share": round(count / total, 4),
                     "cumulative": round(running / total, 4)})
    return rows


def _name(unit: ProductionUnit, dimension: str) -> Optional[str]:
    if dimension == "machine":
        return unit.machine.code if unit.machine else None
    if dimension == "line":
        return unit.line.code if unit.line else None
    if dimension == "batch":
        return unit.batch.code if unit.batch else None
    if dimension == "product":
        return unit.product.name if unit.product else None
    return unit.shift


def group_by(units: List[ProductionUnit], detections: List[DefectDetection], dimension: str) -> List[Dict[str, Any]]:
    by_unit = defaultdict(list)
    for d in detections:
        by_unit[d.unit_id].append(d)
    groups: Dict[str, List[ProductionUnit]] = defaultdict(list)
    for u in units:
        name = _name(u, dimension)
        if name:
            groups[name].append(u)
    rows = []
    for name, members in groups.items():
        types = Counter(d.defect_type for u in members for d in by_unit[u.id])
        rows.append({"group": name, **summarise(members), "defects": sum(types.values()),
                     "top_defect": types.most_common(1)[0][0] if types else None})
    rows.sort(key=lambda r: -(r["flagged_rate"] or 0))
    return rows


def trend(units: List[ProductionUnit], bucket: str = "day") -> List[Dict[str, Any]]:
    buckets: Dict[str, List[ProductionUnit]] = defaultdict(list)
    for u in units:
        key = u.inspected_at.strftime("%Y-%m-%d %H:00" if bucket == "hour" else "%Y-%m-%d")
        buckets[key].append(u)
    points = [{"period": k, "inspected": len(v), "defective": sum(1 for u in v if is_flagged(u)),
               "rejected": sum(1 for u in v if effective_decision(u) == "REJECT"),
               "accepted": sum(1 for u in v if effective_decision(u) == "ACCEPT")} for k, v in sorted(buckets.items())]
    chart = p_chart(points)
    for point, row in zip(points, chart):
        row["first_pass_yield"] = round(point["accepted"] / point["inspected"], 4) if point["inspected"] else None
    return chart


def overview(db: Session, days: int = 30, **filters: Any) -> Dict[str, Any]:
    units = load_units(db, days, **filters)
    detections = detections_for(db, units)
    return {
        "window_days": days, "kpis": summarise(units), "pareto": pareto(detections), "trend": trend(units),
        "by_machine": group_by(units, detections, "machine"), "by_shift": group_by(units, detections, "shift"),
        "by_batch": group_by(units, detections, "batch"), "by_product": group_by(units, detections, "product"),
        "by_line": group_by(units, detections, "line"),
        "severity": dict(Counter(d.severity for d in detections)),
        "hotspot": _hotspot([{"metrics": d.metrics} for d in detections]),
    }


def root_cause(db: Session, days: int = 30, defect_type: Optional[str] = None, **filters: Any) -> Dict[str, Any]:
    units = load_units(db, days, **filters)
    detections = detections_for(db, units)
    if defect_type:
        flagged = {d.unit_id for d in detections if d.defect_type == defect_type}
        detections = [d for d in detections if d.defect_type == defect_type]
    else:
        flagged = {u.id for u in units if is_flagged(u)}

    findings: List[Dict[str, Any]] = []
    for dimension in ("machine", "shift", "batch", "line"):
        groups: Dict[str, Dict[str, int]] = defaultdict(lambda: {"units": 0, "defective": 0})
        for u in units:
            name = _name(u, dimension)
            if name:
                groups[name]["units"] += 1
                groups[name]["defective"] += u.id in flagged
        findings += association(groups, dimension)
    findings.sort(key=lambda f: (not f["significant"], f["p_value"]))

    top = pareto(detections)[:3]
    knowledge = []
    for row in top:
        kb = ROOT_CAUSE_KB.get(row["defect_type"], GENERIC_KB)
        knowledge.append({"defect_type": row["defect_type"], "count": row["count"], "hypotheses": kb["causes"],
                          "checks": kb["actions"], "source": "Built-in process knowledge, not derived from this data"})
    return {
        "note": CORRELATION_NOTE, "units": len(units), "flagged_units": len(flagged), "defect_type": defect_type,
        "findings": findings, "significant": [f for f in findings if f["significant"]],
        "hypotheses": knowledge, "hotspot": _hotspot([{"metrics": d.metrics} for d in detections]),
    }


def refresh_alerts(db: Session, days: int = 30) -> List[QualityAlert]:
    """Idempotent. Fingerprints stop one spike from being raised twice."""
    units = load_units(db, days)
    if not units:
        return []
    candidates: List[Tuple[str, Dict[str, Any]]] = []
    for point in trend(units):
        if point["out_of_control"]:
            candidates.append((f"SPIKE:{point['period']}", {
                "kind": "DEFECT_RATE_SPIKE", "dimension": "time", "group_name": point["period"],
                "value": point["rate"], "limit_value": point["ucl"],
                "message": f"Flagged rate (rejected or awaiting review) {point['rate']:.1%} on {point['period']} exceeds the control limit {point['ucl']:.1%}.",
            }))
    for finding in root_cause(db, days)["significant"]:
        candidates.append((f"ASSOC:{finding['dimension']}:{finding['group']}", {
            "kind": "ASSOCIATION", "dimension": finding["dimension"], "group_name": finding["group"],
            "value": finding["rate"], "limit_value": finding["rate_elsewhere"],
            "message": (f"{finding['dimension'].title()} {finding['group']}: flagged rate {finding['rate']:.1%} vs "
                        f"{finding['rate_elsewhere']:.1%} elsewhere (odds ratio {finding['odds_ratio']}, q={finding['q_value']}). "
                        "Association only: investigate."),
        }))
    created = []
    for fingerprint, fields in candidates:
        if not db.query(QualityAlert).filter(QualityAlert.fingerprint == fingerprint).first():
            row = QualityAlert(fingerprint=fingerprint, **fields)
            db.add(row)
            created.append(row)
    db.commit()
    return created


def batch_report_data(db: Session, batch: Batch) -> Dict[str, Any]:
    units = db.query(ProductionUnit).filter(ProductionUnit.batch_id == batch.id).order_by(ProductionUnit.inspected_at).all()
    detections = detections_for(db, units)
    return {"batch": batch.code, "product": batch.product.name if batch.product else None, "status": batch.status,
            "is_synthetic": batch.is_synthetic, "kpis": summarise(units), "pareto": pareto(detections),
            "by_machine": group_by(units, detections, "machine"), "by_shift": group_by(units, detections, "shift")}


__all__ = ["overview", "root_cause", "refresh_alerts", "batch_report_data", "Machine", "Product", "ProductionLine"]
