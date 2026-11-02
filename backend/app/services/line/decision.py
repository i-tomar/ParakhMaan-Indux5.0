"""Deterministic accept / reject / manual-review decision for one production unit.

AI models produce evidence; this table-driven policy decides. The same evidence and policy always
give the same decision (R-29), and every decision lists its reasons.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

ACCEPT = "ACCEPT"
REJECT = "REJECT"
MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass
class DecisionPolicy:
    reject_severities: List[str] = field(default_factory=lambda: ["CRITICAL", "HIGH"])
    review_severities: List[str] = field(default_factory=lambda: ["MEDIUM"])
    min_reject_confidence: float = 0.5
    unknown_anomaly_action: str = MANUAL_REVIEW
    dimensional_fail_action: str = REJECT
    poor_image_action: str = MANUAL_REVIEW

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "DecisionPolicy":
        data = data or {}
        keys = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in keys})


def decide(
    detections: List[Dict[str, Any]],
    dimensional_status: Optional[str] = None,
    image_ok: bool = True,
    policy: Optional[DecisionPolicy] = None,
) -> Dict[str, Any]:
    policy = policy or DecisionPolicy()
    rejects: List[str] = []
    reviews: List[str] = []

    active = [d for d in detections if d.get("reviewer_status") != "REJECTED"]
    for d in active:
        kind, severity, conf = d.get("defect_type"), d.get("severity"), float(d.get("confidence", 0))
        label = f"{kind} {severity} ({conf:.0%})"
        if kind == "UNKNOWN_ANOMALY":
            (rejects if policy.unknown_anomaly_action == REJECT else reviews).append(f"{label}: unclassified anomaly")
        elif severity in policy.reject_severities and conf >= policy.min_reject_confidence:
            rejects.append(label)
        elif severity in policy.reject_severities or severity in policy.review_severities:
            reviews.append(label)

    if dimensional_status == "OUT_OF_TOLERANCE":
        (rejects if policy.dimensional_fail_action == REJECT else reviews).append("Dimension out of tolerance")
    elif dimensional_status == "PART_NOT_FOUND":
        reviews.append("Part outline not found for measurement")
    if not image_ok:
        (rejects if policy.poor_image_action == REJECT else reviews).append("Image too dark or saturated to inspect")

    if rejects:
        return {"decision": REJECT, "reasons": rejects + reviews}
    if reviews:
        return {"decision": MANUAL_REVIEW, "reasons": reviews}
    return {"decision": ACCEPT, "reasons": []}
