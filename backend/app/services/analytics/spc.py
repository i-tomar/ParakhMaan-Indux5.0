"""Statistics behind quality alerts and root-cause evidence. Output is association, never proof."""
import math
from typing import Any, Dict, List, Sequence

try:
    from scipy.stats import fisher_exact
except ImportError:  # pragma: no cover
    fisher_exact = None

MIN_SUBGROUP = 5


def p_chart(rows: Sequence[Dict[str, Any]], min_baseline: int = 3, sigma: float = 3.0) -> List[Dict[str, Any]]:
    """Attribute control chart. rows: {period, inspected, defective} in time order.

    The centre line comes only from periods BEFORE the one being judged, so a spike cannot inflate
    its own limit. Limits widen for small subgroups, as they must for a p-chart.
    """
    out = []
    for i, row in enumerate(rows):
        base = rows[:i]
        n, defective = row["inspected"], row["defective"]
        rate = defective / n if n else 0.0
        base_n = sum(r["inspected"] for r in base)
        point = {"period": row["period"], "inspected": n, "defective": defective, "rate": round(rate, 4),
                 "centre": None, "ucl": None, "out_of_control": False}
        if len(base) >= min_baseline and base_n and n >= MIN_SUBGROUP:
            p_bar = sum(r["defective"] for r in base) / base_n
            ucl = min(1.0, p_bar + sigma * math.sqrt(max(p_bar * (1 - p_bar), 1e-6) / n))
            point.update(centre=round(p_bar, 4), ucl=round(ucl, 4), out_of_control=rate > ucl)
        out.append(point)
    return out


def _fisher_p(a: int, b: int, c: int, d: int) -> float:
    return float(fisher_exact([[a, b], [c, d]], alternative="greater")[1])


def association(groups: Dict[str, Dict[str, int]], dimension: str, min_units: int = 10) -> List[Dict[str, Any]]:
    """Compares each group's defect rate with all other groups combined.

    groups: {name: {"units": n, "defective": k}}. p-values use Fisher's exact test and are adjusted
    with Benjamini-Hochberg because many groups are tested at once.
    """
    total_n = sum(g["units"] for g in groups.values())
    total_k = sum(g["defective"] for g in groups.values())
    rows = []
    for name, g in groups.items():
        n, k = g["units"], g["defective"]
        other_n, other_k = total_n - n, total_k - k
        if n < min_units or other_n < min_units:
            continue
        rate, other_rate = k / n, other_k / other_n
        odds = ((k + 0.5) * (other_n - other_k + 0.5)) / ((n - k + 0.5) * (other_k + 0.5))
        rows.append({
            "dimension": dimension, "group": name, "units": n, "defective": k,
            "rate": round(rate, 4), "rate_elsewhere": round(other_rate, 4), "odds_ratio": round(odds, 2),
            "p_value": _fisher_p(k, n - k, other_k, other_n - other_k),
        })
    rows.sort(key=lambda r: r["p_value"])
    m = len(rows)
    adjusted = 1.0
    for rank in range(m, 0, -1):
        adjusted = min(adjusted, rows[rank - 1]["p_value"] * m / rank)
        rows[rank - 1]["q_value"] = round(adjusted, 5)
    for r in rows:
        r["p_value"] = round(r["p_value"], 5)
        r["significant"] = r["q_value"] < 0.05 and r["odds_ratio"] > 1.0
        r["interpretation"] = (
            f"{r['group']} shows a higher defect rate than other {dimension}s. This is a statistical "
            "association and must be confirmed on the shop floor before it is treated as a cause."
            if r["significant"] else "No significant association."
        )
    return rows
