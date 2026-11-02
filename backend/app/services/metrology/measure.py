"""Geometric measurement of one part in calibrated millimetres, and tolerance checks."""
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from app.services.metrology.calibration import Calibration, pixels_to_mm


def segment_part(image: np.ndarray) -> Optional[np.ndarray]:
    """Outer contour of the part, assuming contrast against a plain background (edge pixels sample it)."""
    h, w = image.shape[:2]
    blur = cv2.GaussianBlur(image, (5, 5), 0)
    lab = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB).astype(np.float32)
    b = max(3, int(0.02 * min(h, w)))
    border = np.concatenate([lab[:b].reshape(-1, 3), lab[-b:].reshape(-1, 3),
                             lab[:, :b].reshape(-1, 3), lab[:, -b:].reshape(-1, 3)])
    background = np.median(border, axis=0)
    distance = np.linalg.norm(lab - background, axis=2)
    spread = float(np.median(np.linalg.norm(border - background, axis=1)))
    floor = max(12.0, 4.0 * spread)
    # Otsu puts the cut midway between background and part, so the blurred edge is not counted
    # as part (a fixed low threshold grew every side by ~1.5 px).
    scaled = np.clip(distance, 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = max(floor, float(otsu))
    fg = (distance > threshold).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg = cv2.morphologyEx(cv2.morphologyEx(fg, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    area_ratio = cv2.contourArea(largest) / float(h * w)
    if area_ratio < 0.005 or area_ratio > 0.98:
        return None
    return largest


def measure_contour(contour: np.ndarray, calibration: Calibration) -> Dict[str, Any]:
    pts_mm = pixels_to_mm(contour.reshape(-1, 2), calibration).astype(np.float32)
    contour_mm = pts_mm.reshape(-1, 1, 2)
    area = float(cv2.contourArea(contour_mm))
    perimeter = float(cv2.arcLength(contour_mm, True))
    (_, _), (side_a, side_b), angle = cv2.minAreaRect(pts_mm)
    length, width = max(side_a, side_b), min(side_a, side_b)
    (_, _), enclosing_radius = cv2.minEnclosingCircle(pts_mm)
    centre = pts_mm.mean(axis=0)
    radial = np.linalg.norm(pts_mm - centre, axis=1)
    circularity = 4 * np.pi * area / max(perimeter ** 2, 1e-9)
    equivalent_diameter = 2 * np.sqrt(area / np.pi)
    hull = cv2.convexHull(pts_mm)
    hull_area = float(cv2.contourArea(hull))
    return {
        "length_mm": round(float(length), 3),
        "width_mm": round(float(width), 3),
        "area_mm2": round(area, 3),
        "perimeter_mm": round(perimeter, 3),
        "equivalent_diameter_mm": round(float(equivalent_diameter), 3),
        "enclosing_diameter_mm": round(float(2 * enclosing_radius), 3),
        "roundness_error_mm": round(float(radial.max() - radial.min()), 3),
        "circularity": round(float(circularity), 4),
        "solidity": round(area / hull_area, 4) if hull_area else 0.0,
        "rotation_deg": round(float(angle), 2),
    }


def contour_deviation(contour: np.ndarray, reference: np.ndarray, calibration: Calibration) -> Dict[str, Any]:
    """Largest outline deviation from the golden contour, after removing position and rotation."""
    def normalise(c: np.ndarray) -> np.ndarray:
        pts = pixels_to_mm(c.reshape(-1, 2), calibration).astype(np.float32)
        (cx, cy), _, angle = cv2.minAreaRect(pts)
        rot = cv2.getRotationMatrix2D((float(cx), float(cy)), float(angle), 1.0)
        out = cv2.transform(pts.reshape(-1, 1, 2), rot).reshape(-1, 2)
        return out - out.mean(axis=0)

    a, b = normalise(contour), normalise(reference)
    best = None
    for k in range(4):  # minAreaRect orientation is ambiguous by 90° steps
        theta = k * np.pi / 2
        R = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]], dtype=np.float32)
        rotated = a @ R.T
        sa = rotated[:: max(1, len(rotated) // 600)]
        sb = b[:: max(1, len(b) // 600)]
        d = np.sqrt(((sa[:, None, :] - sb[None, :, :]) ** 2).sum(axis=2))
        forward, backward = d.min(axis=1), d.min(axis=0)
        score = float(max(forward.max(), backward.max()))
        if best is None or score < best[0]:
            best = (score, float(np.mean(np.concatenate([forward, backward]))))
    return {"hausdorff_mm": round(best[0], 3), "mean_deviation_mm": round(best[1], 3)}


def check_tolerances(measured: Dict[str, Any], specification: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """specification rows: {feature, nominal, minus, plus}. Unknown features are reported as NOT_MEASURED."""
    rows = []
    for spec in specification:
        value = measured.get(spec["feature"])
        low, high = spec["nominal"] - abs(spec.get("minus", 0)), spec["nominal"] + abs(spec.get("plus", 0))
        if value is None:
            rows.append({**spec, "measured": None, "deviation": None, "status": "NOT_MEASURED"})
            continue
        rows.append({
            **spec, "measured": value, "deviation": round(value - spec["nominal"], 3),
            "status": "PASS" if low <= value <= high else "FAIL",
        })
    return rows


def inspect_dimensions(
    image: np.ndarray,
    calibration: Calibration,
    specification: Optional[List[Dict[str, Any]]] = None,
    reference_contour: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    contour = segment_part(image)
    if contour is None:
        return {"status": "PART_NOT_FOUND", "calibration": calibration.to_dict(), "tolerances": [],
                "note": "No part contour found. Needs a plain background with contrast."}
    measured = measure_contour(contour, calibration)
    if reference_contour is not None:
        measured.update(contour_deviation(contour, reference_contour, calibration))
    tolerances = check_tolerances(measured, specification or [])
    failed = [t for t in tolerances if t["status"] == "FAIL"]
    x, y, w, h = cv2.boundingRect(contour)
    return {
        "status": "OUT_OF_TOLERANCE" if failed else ("IN_TOLERANCE" if tolerances else "MEASURED_NO_SPEC"),
        "measurements": measured,
        "tolerances": tolerances,
        "bbox": [float(x), float(y), float(x + w), float(y + h)],
        "contour_points": len(contour),
        "calibration": calibration.to_dict(),
        "physical_accuracy_validated": False,
    }
