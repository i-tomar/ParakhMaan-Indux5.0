"""Metrology, decision, actuator, SPC, tracker and gate. No models required."""
import os

import cv2
import numpy as np
import pytest

from app.services.analytics.spc import association, p_chart
from app.services.learning.gate import evaluate_gate
from app.services.line.actuator import (
    RejectCommand, SerialActuator, SimulatedActuator, WebhookActuator, fire_delay_ms, latency_budget,
)
from app.services.line.decision import ACCEPT, MANUAL_REVIEW, REJECT, DecisionPolicy, decide
from app.services.metrology.calibration import calibrate_checkerboard, calibrate_reference_length, pixels_to_mm
from app.services.metrology.measure import check_tolerances, contour_deviation, inspect_dimensions, segment_part
from app.services.realtime.sources import conveyor_simulation
from app.services.realtime.tracker import UnitTracker


def board(cols=9, rows=6, square=40, margin=60):
    h, w = (rows + 1) * square + 2 * margin, (cols + 1) * square + 2 * margin
    img = np.full((h, w), 255, np.uint8)
    for r in range(rows + 1):
        for c in range(cols + 1):
            if (r + c) % 2 == 0:
                img[margin + r * square:margin + (r + 1) * square, margin + c * square:margin + (c + 1) * square] = 0
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def part_image(w_px, h_px, size=(600, 800)):
    img = np.full((*size, 3), 30, np.uint8)
    cx, cy = size[1] // 2, size[0] // 2
    cv2.rectangle(img, (cx - w_px // 2, cy - h_px // 2), (cx + w_px // 2 - 1, cy + h_px // 2 - 1), (200, 200, 200), -1)
    return img


def test_reference_calibration_scale_and_assumptions():
    cal = calibrate_reference_length(100.0, 400.0)
    assert cal.mm_per_px == 0.25
    assert any("perpendicular" in a for a in cal.assumptions)
    with pytest.raises(ValueError):
        calibrate_reference_length(0, 10)


def test_checkerboard_recovers_scale():
    cal = calibrate_checkerboard(board(), (9, 6), 10.0)
    assert abs(cal.mm_per_px - 0.25) < 0.005
    assert cal.reprojection_error_mm < 0.2
    assert cal.points_used == 54


def test_checkerboard_corrects_perspective():
    img = board()
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[40, 20], [w - 10, 0], [w, h - 15], [0, h]])
    warped = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(255, 255, 255))
    cal = calibrate_checkerboard(warped, (9, 6), 10.0)
    corners = cv2.findChessboardCornersSB(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), (9, 6))[1].reshape(-1, 2)
    mm = pixels_to_mm(corners[[0, 8]], cal)
    assert abs(np.linalg.norm(mm[0] - mm[1]) - 80.0) < 0.5


@pytest.mark.parametrize("w_px,h_px", [(400, 200), (300, 120), (500, 333)])
def test_measurement_error_under_one_percent(w_px, h_px):
    cal = calibrate_reference_length(1.0, 4.0)
    result = inspect_dimensions(part_image(w_px, h_px), cal)
    m = result["measurements"]
    assert abs(m["length_mm"] - max(w_px, h_px) / 4) / (max(w_px, h_px) / 4) < 0.01
    assert abs(m["width_mm"] - min(w_px, h_px) / 4) / (min(w_px, h_px) / 4) < 0.01
    assert result["physical_accuracy_validated"] is False


def test_diameter_and_tolerance_failure():
    img = np.full((600, 800, 3), 30, np.uint8)
    cv2.circle(img, (400, 300), 200, (210, 210, 210), -1, cv2.LINE_AA)
    cal = calibrate_reference_length(1.0, 2.0)
    spec = [{"feature": "equivalent_diameter_mm", "nominal": 190.0, "minus": 1.0, "plus": 1.0}]
    result = inspect_dimensions(img, cal, spec)
    assert abs(result["measurements"]["equivalent_diameter_mm"] - 200) < 2
    assert result["status"] == "OUT_OF_TOLERANCE"
    assert result["tolerances"][0]["status"] == "FAIL"


def test_unknown_feature_is_not_a_pass():
    rows = check_tolerances({"length_mm": 10.0}, [{"feature": "depth_mm", "nominal": 1, "minus": 0, "plus": 0}])
    assert rows[0]["status"] == "NOT_MEASURED"


def test_contour_deviation_finds_notch():
    cal = calibrate_reference_length(1.0, 1.0)
    good = part_image(400, 200)
    bad = good.copy()
    cv2.circle(bad, (600, 300), 40, (30, 30, 30), -1)
    assert contour_deviation(segment_part(good), segment_part(good), cal)["hausdorff_mm"] < 1
    assert contour_deviation(segment_part(bad), segment_part(good), cal)["hausdorff_mm"] > 20


def test_part_not_found_goes_to_review():
    result = inspect_dimensions(np.full((400, 400, 3), 128, np.uint8), calibrate_reference_length(1, 1))
    assert result["status"] == "PART_NOT_FOUND"
    assert decide([], result["status"])["decision"] == MANUAL_REVIEW


def det(kind="SCRATCH", severity="HIGH", conf=0.9, status="PENDING"):
    return {"defect_type": kind, "severity": severity, "confidence": conf, "reviewer_status": status}


@pytest.mark.parametrize("detections,dimensional,image_ok,expected", [
    ([], None, True, ACCEPT),
    ([det(severity="LOW")], None, True, ACCEPT),
    ([det(severity="MEDIUM")], None, True, MANUAL_REVIEW),
    ([det()], None, True, REJECT),
    ([det(conf=0.3)], None, True, MANUAL_REVIEW),
    ([det(status="REJECTED")], None, True, ACCEPT),
    ([det("UNKNOWN_ANOMALY", "MEDIUM")], None, True, MANUAL_REVIEW),
    ([], "OUT_OF_TOLERANCE", True, REJECT),
    ([], "IN_TOLERANCE", False, MANUAL_REVIEW),
])
def test_decision_table(detections, dimensional, image_ok, expected):
    assert decide(detections, dimensional, image_ok)["decision"] == expected


def test_decision_is_deterministic_and_policy_driven():
    d = [det("UNKNOWN_ANOMALY", "MEDIUM")]
    assert decide(d) == decide(d)
    strict = DecisionPolicy(unknown_anomaly_action=REJECT)
    assert decide(d, policy=strict)["decision"] == REJECT


def test_latency_budget_and_missed_window():
    b = latency_budget(200, 600, 300)
    assert b["travel_to_diverter_ms"] == 3000
    assert b["units_per_minute"] == 40
    assert b["max_decision_latency_ms"] == 2970
    assert fire_delay_ms(200, 600, 500) == pytest.approx(2470)
    assert fire_delay_ms(200, 600, 3000) is None


def test_simulated_actuator_is_labelled():
    event = SimulatedActuator().fire(RejectCommand("U1", 100, "x"))
    assert event["status"] == "SIMULATED_FIRED"


def test_serial_protocol_ack_and_timeout():
    class Link:
        def __init__(self, reply):
            self.reply, self.sent = reply, b""

        def write(self, data):
            self.sent += data

        def readline(self):
            return self.reply

    link = Link(b"A,U7\n")
    actuator = SerialActuator("x", serial_factory=lambda *a, **k: link)
    assert actuator.fire(RejectCommand("U7", 120.4, "r"))["status"] == "ACKNOWLEDGED"
    assert link.sent == b"R,U7,120\n"
    silent = SerialActuator("x", serial_factory=lambda *a, **k: Link(b""))
    assert silent.fire(RejectCommand("U7", 1, "r"))["status"] == "NO_ACK"


def test_webhook_rejects_bad_url_and_handles_failure():
    with pytest.raises(ValueError):
        WebhookActuator("file:///etc/passwd")

    def fail(*a, **k):
        raise OSError("down")

    assert WebhookActuator("http://plc.local/x", opener=fail).fire(RejectCommand("U", 1, "r"))["status"] == "NO_ACK"


def test_p_chart_flags_spike_only():
    rows = [{"period": str(i), "inspected": 100, "defective": 5 + (i % 2)} for i in range(8)]
    assert not any(p["out_of_control"] for p in p_chart(rows))
    rows.append({"period": "spike", "inspected": 100, "defective": 30})
    assert p_chart(rows)[-1]["out_of_control"]


def test_p_chart_needs_baseline():
    rows = [{"period": "a", "inspected": 100, "defective": 90}, {"period": "b", "inspected": 100, "defective": 1}]
    assert not any(p["out_of_control"] for p in p_chart(rows))


def test_association_finds_fault_and_ignores_noise():
    groups = {"M1": {"units": 100, "defective": 8}, "M2": {"units": 100, "defective": 40}, "M3": {"units": 100, "defective": 7}}
    rows = {r["group"]: r for r in association(groups, "machine")}
    assert rows["M2"]["significant"] and rows["M2"]["odds_ratio"] > 3
    assert "association" in rows["M2"]["interpretation"]
    assert not rows["M1"]["significant"]
    even = association({k: {"units": 100, "defective": 10} for k in ("A", "B", "C")}, "shift")
    assert not any(r["significant"] for r in even)


def test_small_groups_are_not_tested():
    assert association({"A": {"units": 3, "defective": 3}, "B": {"units": 100, "defective": 1}}, "batch") == []


def test_gate_refuses_regression_and_small_holdout():
    production = {"image_auroc": 0.95, "recall": 0.9, "false_reject_rate": 0.05}
    base = {"holdout_good": 10, "holdout_defective": 10}
    assert evaluate_gate("ANOMALY", {**base, "image_auroc": 0.96, "recall": 0.9, "false_reject_rate": 0.05}, production)["passed"]
    assert not evaluate_gate("ANOMALY", {**base, "image_auroc": 0.90, "recall": 0.95, "false_reject_rate": 0.01}, production)["passed"]
    assert not evaluate_gate("ANOMALY", {**base, "image_auroc": 0.99, "recall": 0.95, "false_reject_rate": 0.20}, production)["passed"]
    assert not evaluate_gate("ANOMALY", {"holdout_good": 1, "holdout_defective": 0, "image_auroc": 1, "recall": 1, "false_reject_rate": 0}, None)["passed"]
    assert not evaluate_gate("ANOMALY", base, None)["passed"]


def test_tracker_counts_each_unit_once(tmp_path):
    paths = []
    for i in range(5):
        p = str(tmp_path / f"{i}.png")
        cv2.imwrite(p, np.full((200, 200, 3), (120 + i * 20, 90, 180 - i * 15), np.uint8))
        paths.append(p)
    frames = list(conveyor_simulation(paths, realtime=False))
    tracker = UnitTracker(trigger_x_ratio=0.5)
    triggered = []
    for frame in frames:
        hits, _ = tracker.update(frame)
        triggered += hits
    assert tracker.units_seen == 5
    assert len(triggered) == 5
    assert len({t.track_id for t in triggered}) == 5
    for t in triggered:
        assert t.best_crop.shape[0] > 250 and t.best_crop.shape[1] > 250  # full view, not a clipped part


def test_review_units_count_as_flagged_until_a_reviewer_accepts():
    from types import SimpleNamespace
    from app.services.analytics.quality import is_flagged
    assert is_flagged(SimpleNamespace(decision="REJECT", final_decision=None))
    assert is_flagged(SimpleNamespace(decision="MANUAL_REVIEW", final_decision=None))
    assert not is_flagged(SimpleNamespace(decision="MANUAL_REVIEW", final_decision="ACCEPT"))
    assert not is_flagged(SimpleNamespace(decision="ACCEPT", final_decision=None))


def test_conveyor_samples_include_subfolders(tmp_path):
    from app.services.realtime.sources import sample_paths
    for sub in ("good", "defect"):
        (tmp_path / sub).mkdir()
        for i in range(3):
            cv2.imwrite(str(tmp_path / sub / f"{i}.png"), np.zeros((8, 8, 3), np.uint8))
    (tmp_path / "SOURCE.txt").write_text("x")
    paths = sample_paths(str(tmp_path))
    assert len(paths) == 6 and {os.path.basename(os.path.dirname(p)) for p in paths} == {"good", "defect"}
    assert sample_paths(str(tmp_path)) == paths  # repeatable
    assert len(sample_paths(str(tmp_path), limit=4)) == 4


def test_split_silhouette_is_one_unit(tmp_path):
    """A part that segments into two blobs (dark band across it) must be tracked and logged once."""
    paths = []
    for i in range(3):
        img = np.full((300, 300, 3), 200, np.uint8)
        img[140:160, :] = (56, 56, 54)  # matches the belt colour: silhouette splits in two
        p = str(tmp_path / f"{i}.png")
        cv2.imwrite(p, img)
        paths.append(p)
    tracker = UnitTracker(trigger_x_ratio=0.5)
    triggered = []
    for frame in conveyor_simulation(paths, realtime=False):
        triggered += tracker.update(frame)[0]
    assert tracker.units_seen == 3 and len(triggered) == 3


def test_classical_findings_need_anomaly_support():
    from app.services.inference.engine import _anomaly_support
    amap = np.zeros((32, 32), np.float32)
    amap[8:12, 20:24] = 3.0  # hot spot in the upper right of a 640x640 image
    assert _anomaly_support(amap, [400, 160, 480, 240], 640, 640) == 3.0
    assert _anomaly_support(amap, [0, 400, 100, 500], 640, 640) == 0.0
