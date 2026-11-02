"""Camera-to-millimetre calibration.

Two methods, both planar: measurements are only valid for parts lying in the calibrated plane.

* CHECKERBOARD: finds the inner corners of a board with known square size, then fits a homography
  from image pixels to millimetres. This also removes perspective tilt.
* REFERENCE_LENGTH: the operator supplies a known length in pixels. It gives one mm-per-pixel
  scale and assumes the camera looks straight at the plane.

Every measurement carries `assumptions`, so a value in mm is never reported without its basis.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class Calibration:
    method: str
    mm_per_px: float
    homography: Optional[List[List[float]]] = None  # image px -> mm plane
    output_size_px: Optional[Tuple[int, int]] = None
    reprojection_error_mm: Optional[float] = None
    points_used: int = 0
    assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Calibration":
        keys = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in keys})


def calibrate_reference_length(known_mm: float, measured_px: float) -> Calibration:
    if known_mm <= 0 or measured_px <= 0:
        raise ValueError("known_mm and measured_px must both be positive")
    return Calibration(
        method="REFERENCE_LENGTH",
        mm_per_px=float(known_mm) / float(measured_px),
        assumptions=[
            "Single scale factor from one reference length",
            "Camera axis perpendicular to the part plane (no perspective correction)",
            "Part at the same distance from the camera as the reference",
            "Lens distortion ignored",
        ],
    )


def calibrate_checkerboard(image: np.ndarray, inner_corners: Tuple[int, int], square_mm: float) -> Calibration:
    """`inner_corners` is (columns, rows) of inner corners, e.g. (9, 6) for a 10x7 board."""
    if square_mm <= 0:
        raise ValueError("square_mm must be positive")
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCornersSB(gray, inner_corners, flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not found:
        found, corners = cv2.findChessboardCorners(gray, inner_corners)
        if found:
            corners = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1),
                                       (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.001))
    if not found:
        raise ValueError(f"Checkerboard with {inner_corners} inner corners not found")
    cols, rows = inner_corners
    grid = np.array([[c * square_mm, r * square_mm] for r in range(rows) for c in range(cols)], dtype=np.float32)
    pts = corners.reshape(-1, 2).astype(np.float32)
    H, _ = cv2.findHomography(pts, grid, 0)
    if H is None:
        raise ValueError("Homography could not be estimated")
    projected = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), H).reshape(-1, 2)
    error = float(np.sqrt(np.mean(np.sum((projected - grid) ** 2, axis=1))))
    # Scale at the board centre, for sizes reported in rectified pixels.
    centre = pts.mean(axis=0, keepdims=True)
    a = cv2.perspectiveTransform((centre + [[0, 0]]).reshape(-1, 1, 2), H)
    b = cv2.perspectiveTransform((centre + [[1, 0]]).reshape(-1, 1, 2), H)
    mm_per_px = float(np.linalg.norm(a - b))
    return Calibration(
        method="CHECKERBOARD",
        mm_per_px=mm_per_px,
        homography=H.tolist(),
        reprojection_error_mm=round(error, 5),
        points_used=len(pts),
        assumptions=[
            "Part lies in the same plane as the calibration board",
            "Homography corrects perspective tilt, not lens distortion",
            "Camera and board must not move after calibration",
        ],
    )


def pixels_to_mm(points: np.ndarray, calibration: Calibration) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if calibration.homography is not None:
        H = np.array(calibration.homography, dtype=np.float64)
        return cv2.perspectiveTransform(pts.reshape(-1, 1, 2), H).reshape(-1, 2)
    return pts * calibration.mm_per_px
