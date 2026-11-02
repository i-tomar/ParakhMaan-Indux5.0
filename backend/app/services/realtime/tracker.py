"""Light per-frame unit tracker. It runs on every frame so each physical unit is decided once.

Products are found by difference from a learned empty-belt image. A unit gets a stable ID, is
followed by nearest centroid, keeps its sharpest full-view frame, and is released for AI
inspection when it reaches the trigger line.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


def merge_boxes(boxes: List[Box], gap: int) -> List[Box]:
    """Union boxes that overlap or lie within `gap` px of each other, until nothing changes.

    Assumes parts on the belt are separated by more than `gap` (pitch is set well above it);
    two parts touching would be merged into one and sent to review by the size check downstream.
    """
    merged = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out: List[List[int]] = []
        for x, y, w, h in merged:
            for o in out:
                if x - gap <= o[0] + o[2] and o[0] - gap <= x + w and y - gap <= o[1] + o[3] and o[1] - gap <= y + h:
                    x2, y2 = max(x + w, o[0] + o[2]), max(y + h, o[1] + o[3])
                    o[0], o[1] = min(x, o[0]), min(y, o[1])
                    o[2], o[3] = x2 - o[0], y2 - o[1]
                    changed = True
                    break
            else:
                out.append([x, y, w, h])
        merged = out
    return [tuple(b) for b in merged]  # type: ignore[misc]


@dataclass
class Track:
    track_id: int
    centroid: Tuple[float, float]
    box: Box
    first_frame: int
    last_frame: int
    frames_seen: int = 1
    best_sharpness: float = -1.0
    best_crop: Optional[np.ndarray] = None
    best_frame_index: int = 0
    triggered: bool = False
    positions: List[float] = field(default_factory=list)


class UnitTracker:
    def __init__(self, trigger_x_ratio: float = 0.55, min_area_ratio: float = 0.01, max_missing: int = 6,
                 diff_threshold: float = 22.0, travel_direction: int = 1, max_jump_ratio: float = 0.2,
                 merge_gap_ratio: float = 0.03):
        self.merge_gap_ratio = merge_gap_ratio
        self.trigger_x_ratio = trigger_x_ratio
        self.min_area_ratio = min_area_ratio
        self.max_missing = max_missing
        self.diff_threshold = diff_threshold
        self.direction = travel_direction
        self.max_jump_ratio = max_jump_ratio
        self.background: Optional[np.ndarray] = None
        self.tracks: Dict[int, Track] = {}
        self._next_id = 1
        self.frame_index = -1
        self.units_seen = 0

    def learn_background(self, frame: np.ndarray) -> None:
        self.background = cv2.GaussianBlur(frame, (7, 7), 0).astype(np.float32)

    def detect(self, frame: np.ndarray) -> List[Box]:
        h, w = frame.shape[:2]
        blur = cv2.GaussianBlur(frame, (7, 7), 0).astype(np.float32)
        diff = np.abs(blur - self.background).max(axis=2)
        binary = (diff > self.diff_threshold).astype(np.uint8) * 255
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        binary = cv2.morphologyEx(cv2.morphologyEx(binary, cv2.MORPH_OPEN, k), cv2.MORPH_CLOSE, k, iterations=2)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # Merge first, filter after: a part whose silhouette splits (dark part on a dark belt) must
        # stay ONE unit. Counting a fragment as a second unit double-logs and double-decides it.
        boxes = merge_boxes([cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= 0.0005 * h * w],
                            gap=int(self.merge_gap_ratio * w))
        return [b for b in boxes if b[2] * b[3] >= self.min_area_ratio * h * w]

    def update(self, frame: np.ndarray) -> Tuple[List[Track], List[Dict[str, Any]]]:
        """Returns (triggered tracks ready for inspection, per-frame display rows)."""
        self.frame_index += 1
        if self.background is None:
            self.learn_background(frame)
            return [], []
        h, w = frame.shape[:2]
        boxes = self.detect(frame)
        unmatched = set(range(len(boxes)))
        max_jump = self.max_jump_ratio * w
        centroids = [(x + bw / 2.0, y + bh / 2.0) for x, y, bw, bh in boxes]

        for track in sorted(self.tracks.values(), key=lambda t: t.track_id):
            best, best_d = None, max_jump
            for i in unmatched:
                d = float(np.hypot(centroids[i][0] - track.centroid[0], centroids[i][1] - track.centroid[1]))
                if d < best_d:
                    best, best_d = i, d
            if best is not None:
                unmatched.discard(best)
                track.centroid, track.box, track.last_frame = centroids[best], boxes[best], self.frame_index
                track.frames_seen += 1
                self._consider(track, frame, w, h)

        for i in sorted(unmatched):
            self.units_seen += 1
            track = Track(self._next_id, centroids[i], boxes[i], self.frame_index, self.frame_index)
            self._next_id += 1
            self.tracks[track.track_id] = track
            self._consider(track, frame, w, h)

        triggered: List[Track] = []
        line = self.trigger_x_ratio * w
        for track in self.tracks.values():
            passed = track.centroid[0] >= line if self.direction > 0 else track.centroid[0] <= line
            if passed and not track.triggered and track.best_crop is not None:
                track.triggered = True
                triggered.append(track)
        for tid in [t.track_id for t in self.tracks.values() if self.frame_index - t.last_frame > self.max_missing]:
            track = self.tracks.pop(tid)
            if not track.triggered and track.best_crop is not None:  # left the view early: still inspect it
                track.triggered = True
                triggered.append(track)
        rows = [{"track_id": t.track_id, "box": list(t.box), "triggered": t.triggered}
                for t in self.tracks.values() if t.last_frame == self.frame_index]
        return triggered, rows

    @staticmethod
    def _consider(track: Track, frame: np.ndarray, w: int, h: int) -> None:
        x, y, bw, bh = track.box
        margin = 3
        if x <= margin or y <= margin or x + bw >= w - margin or y + bh >= h - margin:
            return  # keep only frames that show the whole part
        crop = frame[y:y + bh, x:x + bw]
        sharpness = float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_32F).var())
        if sharpness > track.best_sharpness:
            track.best_sharpness = sharpness
            track.best_crop = crop.copy()
            track.best_frame_index = track.last_frame
