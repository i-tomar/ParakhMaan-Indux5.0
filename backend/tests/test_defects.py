import base64
import os
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.defect_analytics_service import build_defect_analytics
from app.services.defect_detection_service import (
    DefectDetector, compute_outcome, synthesize_surface_sample
)

client = TestClient(app)
detector = DefectDetector(model_path="", backend="opencv")

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "models", "best.onnx")
requires_model = pytest.mark.skipif(not os.path.exists(MODEL_PATH), reason="trained ONNX model not present")


def _types(result):
    return {d["defect_type"] for d in result["detections"]}


# ---------------------------------------------------------------- detector
def test_clean_surface_passes():
    result = detector.detect(synthesize_surface_sample([]))
    assert result["detections"] == []
    assert result["outcome"] == "PASS"
    assert result["latency_ms"] > 0


@pytest.mark.parametrize("defect, expected_outcome", [
    ("SCRATCH", "DEFECTIVE"),
    ("CRACK", "DEFECTIVE"),
    ("DENT", "REVIEW"),
    ("DISCOLOURATION", "REVIEW"),
])
def test_each_defect_type_is_detected(defect, expected_outcome):
    result = detector.detect(synthesize_surface_sample([defect]))
    assert _types(result) == {defect}
    assert result["outcome"] == expected_outcome


def test_scratch_and_crack_are_distinguished():
    result = detector.detect(synthesize_surface_sample(["SCRATCH", "CRACK"]))
    by_type = {d["defect_type"]: d for d in result["detections"]}
    assert set(by_type) == {"SCRATCH", "CRACK"}
    assert by_type["CRACK"]["metrics"]["tortuosity"] > by_type["SCRATCH"]["metrics"]["tortuosity"]
    assert by_type["CRACK"]["severity"] in ("HIGH", "CRITICAL")


@pytest.mark.parametrize("defects", [[], ["CRACK"], ["SCRATCH"]])
def test_textured_surface_does_not_hide_or_invent_defects(defects):
    # Heavy grain/speckle (like real brushed or pitted metal) must not raise the line threshold
    # above real cracks/scratches, nor produce defects on its own.
    rng = np.random.default_rng(3)
    img = synthesize_surface_sample(defects).astype(np.float32)
    img += rng.normal(0, 14, img.shape[:2]).astype(np.float32)[..., None]
    result = detector.detect(np.clip(img, 0, 255).astype(np.uint8))
    assert _types(result) == set(defects)


def test_dimensional_anomaly_on_notched_part():
    clean = detector.detect(synthesize_surface_sample([], product_on_background=True))
    notched = detector.detect(synthesize_surface_sample([], product_on_background=True, notch=True))
    assert clean["detections"] == []
    assert _types(notched) == {"DIMENSIONAL_ANOMALY"}
    assert notched["product_mask_used"] is True


def test_golden_reference_suppresses_design_features():
    # A printed band is "discolouration" on its own, but not when the golden sample has it too.
    img = synthesize_surface_sample([])
    cv2.rectangle(img, (0, 0), (img.shape[1], 90), (40, 60, 150), -1)
    assert "DISCOLOURATION" in _types(detector.detect(img))
    assert detector.detect(img, img.copy())["detections"] == []

    with_scratch = img.copy()
    cv2.line(with_scratch, (200, 400), (600, 480), (230, 232, 235), 2, cv2.LINE_AA)
    assert _types(detector.detect(with_scratch, img)) == {"SCRATCH"}


def test_bboxes_are_in_original_coordinates_when_downscaled():
    img = synthesize_surface_sample(["CRACK"], size=(1440, 1920))
    result = detector.detect(img)
    assert result["image_size"] == [1920, 1440]
    x1, y1, x2, y2 = result["detections"][0]["bbox"]
    assert x2 > 1000 and y2 > 600  # crack is drawn in the right half


def test_outcome_ignores_rejected_detections():
    dets = [{"defect_type": "CRACK", "severity": "CRITICAL", "confidence": 0.9, "reviewer_status": "REJECTED"}]
    assert compute_outcome(dets) == "PASS"
    dets[0]["reviewer_status"] = "CONFIRMED"
    assert compute_outcome(dets) == "DEFECTIVE"


# ---------------------------------------------------------------- ONNX model / hybrid
def test_fuse_merges_same_type_and_keeps_different_types():
    model = [
        {"defect_type": "DISCOLOURATION", "bbox": [100, 100, 200, 200], "confidence": 0.8, "detector": "ONNX",
         "metrics": {"method": "yolo_onnx", "model_class": "discolouration"}},
        {"defect_type": "DENT", "bbox": [400, 400, 450, 450], "confidence": 0.6, "detector": "ONNX",
         "metrics": {"method": "yolo_onnx", "model_class": "dent"}},
    ]
    cv = [
        {"defect_type": "DISCOLOURATION", "bbox": [110, 105, 205, 210], "confidence": 0.7, "detector": "OPENCV",
         "metrics": {"method": "cielab_colour_deviation", "mean_delta_e": 25.0}},
        {"defect_type": "SCRATCH", "bbox": [400, 400, 460, 455], "confidence": 0.9, "detector": "OPENCV",
         "metrics": {"method": "morphological_line_extraction"}},
    ]
    fused = DefectDetector._fuse(model, cv)
    by_type = {d["defect_type"]: d for d in fused}
    assert len(fused) == 3
    assert by_type["DISCOLOURATION"]["detector"] == "ONNX+OPENCV"
    assert by_type["DISCOLOURATION"]["metrics"]["mean_delta_e"] == 25.0  # OpenCV measurements kept
    assert by_type["DISCOLOURATION"]["confidence"] == pytest.approx(1 - 0.2 * 0.3)
    assert by_type["DENT"]["detector"] == "ONNX"  # different type on the same spot is not dropped
    assert by_type["SCRATCH"]["detector"] == "OPENCV"


@requires_model
def test_trained_model_loads_with_probed_input_size():
    hybrid = DefectDetector(model_path=MODEL_PATH, model_classes="scratch,crack,dent,discolouration", backend="hybrid")
    status = hybrid.status()
    assert status["model_loaded"] is True
    assert status["model_error"] is None
    assert status["model_input_size"] == 320
    assert status["model_classes"] == ["scratch", "crack", "dent", "discolouration"]


@requires_model
def test_relative_model_path_and_names_file_are_resolved():
    hybrid = DefectDetector(model_path="storage/models/best.onnx", model_classes="", backend="hybrid")
    assert hybrid.status()["model_loaded"] is True
    assert hybrid.status()["model_classes"] == ["scratch", "crack", "dent", "discolouration"]


@requires_model
def test_hybrid_pipeline_uses_model_and_opencv():
    hybrid = DefectDetector(model_path=MODEL_PATH, model_classes="scratch,crack,dent,discolouration", backend="hybrid")
    result = hybrid.detect(synthesize_surface_sample(["DISCOLOURATION", "CRACK"]))
    assert result["backend"] == "ONNX+OPENCV"
    detectors = {d["detector"] for d in result["detections"]}
    assert any("ONNX" in d for d in detectors)
    assert "CRACK" in _types(result) and "DISCOLOURATION" in _types(result)
    assert hybrid.detect(synthesize_surface_sample([]))["detections"] == []

    onnx_only = DefectDetector(model_path=MODEL_PATH, model_classes="scratch,crack,dent,discolouration", backend="onnx")
    assert onnx_only.detect(synthesize_surface_sample(["DISCOLOURATION"]))["backend"] == "ONNX"


# ---------------------------------------------------------------- analytics
def test_analytics_frequency_trend_and_root_causes():
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    inspections = [
        {"id": "a", "product_name": "Panel", "overall_outcome": "DEFECTIVE", "created_at": now},
        {"id": "b", "product_name": "Cover", "overall_outcome": "PASS", "created_at": now},
    ]
    detections = []
    for i in range(4):
        detections.append({
            "id": f"s{i}", "inspection_id": "a", "defect_type": "SCRATCH", "severity": "MEDIUM", "confidence": 0.8,
            "reviewer_status": "CONFIRMED" if i == 0 else "PENDING",
            "metrics": {"bbox_norm": [0.05, 0.05, 0.2, 0.2]}, "created_at": now - timedelta(days=i % 2),
        })
    detections.append({
        "id": "x", "inspection_id": "a", "defect_type": "DENT", "severity": "LOW", "confidence": 0.6,
        "reviewer_status": "REJECTED", "metrics": {}, "created_at": now,
    })
    result = build_defect_analytics(inspections, detections, days=14, now=now)

    assert result["most_frequent_type"] == "SCRATCH"
    assert result["totals"]["detections"] == 4  # rejected dent excluded
    assert result["totals"]["defect_rate"] == 0.5
    assert result["trend"][-1]["by_type"]["SCRATCH"] == 2
    assert result["hotspots"]["SCRATCH"]["dominant_region"] == "top-left"
    assert result["feedback"]["precision_estimate"] == 0.5
    rc = result["root_causes"][0]
    assert rc["defect_type"] == "SCRATCH"
    assert any("top-left" in e for e in rc["evidence"])


# ---------------------------------------------------------------- API
def _jpeg(img):
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()


def test_defect_inspection_api_flow(tmp_path):
    created = client.post("/api/v1/defects/inspections", json={
        "product_name": "Test Steel Panel", "brand_name": "LOT-T1", "category": "METAL_SHEET", "location": "Line 1"
    })
    assert created.status_code == 200
    insp = created.json()
    assert insp["inspection_mode"] == "DEFECT"
    assert insp["inspection_number"].startswith("DEF-")
    insp_id = insp["id"]

    # Image analysis
    img = synthesize_surface_sample(["SCRATCH", "CRACK"])
    res = client.post(
        f"/api/v1/defects/inspections/{insp_id}/analyze",
        files={"file": ("panel.jpg", _jpeg(img), "image/jpeg")},
        data={"surface_type": "TOP"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert {d["defect_type"] for d in body["detections"]} == {"SCRATCH", "CRACK"}
    assert body["overall_outcome"] == "DEFECTIVE"
    image_id = body["image"]["id"]

    # Reject every detection -> outcome recovers to PASS, training samples saved
    for det in body["detections"]:
        fb = client.post(f"/api/v1/defects/detections/{det['id']}/feedback", json={"action": "REJECT", "note": "test"})
        assert fb.status_code == 200
        assert fb.json()["training_sample_saved"] is True
    detail = client.get(f"/api/v1/defects/inspections/{insp_id}").json()
    assert detail["overall_outcome"] == "PASS"
    assert all(d["reviewer_status"] == "REJECTED" for d in detail["defect_detections"])
    assert len(detail["reviewer_actions"]) == 2

    # Relabel one back
    det_id = body["detections"][0]["id"]
    fb = client.post(f"/api/v1/defects/detections/{det_id}/feedback", json={"action": "RELABEL", "defect_type": "CRACK"})
    assert fb.json()["detection"]["defect_type"] == "CRACK"
    assert fb.json()["overall_outcome"] == "DEFECTIVE"

    # Overlay + report
    overlay = client.get(f"/api/v1/defects/inspections/{insp_id}/overlay/{image_id}")
    assert overlay.status_code == 200
    assert overlay.json()["overlay_data_url"].startswith("data:image/jpeg;base64,")
    report = client.get(f"/api/v1/defects/inspections/{insp_id}/report")
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    assert client.get(f"/api/v1/inspections/{insp_id}/report").status_code == 200

    # Video: a short clip of the cracked surface
    video_path = str(tmp_path / "clip.avi")
    writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*"MJPG"), 10, (640, 480))
    frame = cv2.resize(synthesize_surface_sample(["CRACK"]), (640, 480))
    for _ in range(20):
        writer.write(frame)
    writer.release()
    with open(video_path, "rb") as f:
        vid = client.post(
            f"/api/v1/defects/inspections/{insp_id}/video",
            files={"file": ("clip.avi", f.read(), "video/x-msvideo")},
            data={"sample_fps": "5", "max_frames": "4"},
        )
    assert vid.status_code == 200, vid.text
    summary = vid.json()
    assert summary["frames_sampled"] == 4
    assert summary["frames_with_defects"] == 4
    assert summary["detections_by_type"].get("CRACK") == 4

    # Finalize
    fin = client.post(f"/api/v1/defects/inspections/{insp_id}/finalize", json={"final_remarks": "ok"})
    assert fin.status_code == 200
    assert fin.json()["status"] == "FINALIZED"

    # Analytics + log
    analytics = client.get("/api/v1/defects/analytics?days=30").json()
    assert analytics["totals"]["inspections"] >= 1
    assert analytics["by_type"]
    log = client.get("/api/v1/defects/log?defect_type=CRACK").json()
    assert log["total"] >= 1
    assert all(item["defect_type"] == "CRACK" for item in log["items"])


def test_clean_surface_inspection_passes_via_api():
    insp = client.post("/api/v1/defects/inspections", json={"product_name": "Clean Panel"}).json()
    res = client.post(
        f"/api/v1/defects/inspections/{insp['id']}/analyze",
        files={"file": ("clean.jpg", _jpeg(synthesize_surface_sample([], seed=13)), "image/jpeg")},
    )
    assert res.status_code == 200
    assert res.json()["detections"] == []
    assert res.json()["overall_outcome"] == "PASS"

    dark = (synthesize_surface_sample([]) * 0.1).astype(np.uint8)
    res = client.post(
        f"/api/v1/defects/inspections/{insp['id']}/analyze",
        files={"file": ("dark.jpg", _jpeg(dark), "image/jpeg")},
    )
    assert res.json()["overall_outcome"] == "REVIEW"


def test_live_frame_endpoint():
    img = synthesize_surface_sample(["SCRATCH"])
    b64 = "data:image/jpeg;base64," + base64.b64encode(_jpeg(img)).decode()
    res = client.post("/api/v1/defects/analyze-frame", json={"image_base64": b64, "max_side": 640})
    assert res.status_code == 200
    data = res.json()
    assert data["image_size"] == [960, 720]
    assert {d["defect_type"] for d in data["detections"]} == {"SCRATCH"}
    assert client.post("/api/v1/defects/analyze-frame", json={"image_base64": "not-an-image"}).status_code == 400


def test_modes_are_separated():
    defect = client.post("/api/v1/defects/inspections", json={"product_name": "Separation Check"}).json()

    legal_list = client.get("/api/v1/inspections").json()
    assert all(i.get("inspection_mode") == "LEGAL_METROLOGY" for i in legal_list)
    assert defect["id"] not in {i["id"] for i in legal_list}

    defect_list = client.get("/api/v1/defects/inspections").json()
    assert defect["id"] in {i["id"] for i in defect_list}

    # Legal pipeline refuses defect inspections; defect endpoints refuse legal ones
    assert client.post(f"/api/v1/inspections/{defect['id']}/process").status_code == 400
    legal = client.post("/api/v1/inspections", json={"product_name": "Legal Check"}).json()
    assert legal["inspection_mode"] == "LEGAL_METROLOGY"
    assert client.get(f"/api/v1/defects/inspections/{legal['id']}").status_code == 404
