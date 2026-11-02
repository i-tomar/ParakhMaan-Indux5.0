"""Frame sources. All are generators of BGR frames paced like the real thing."""
import os
import time
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np


def paced(frames: Iterable[np.ndarray], fps: float) -> Iterator[np.ndarray]:
    period = 1.0 / fps
    next_at = time.perf_counter()
    for frame in frames:
        delay = next_at - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        yield frame
        next_at += period


def video_source(path_or_device: Union[str, int], realtime: bool = True) -> Iterator[np.ndarray]:
    """Video file, USB camera index, or RTSP URL. Files replay at their recorded rate."""
    cap = cv2.VideoCapture(path_or_device)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video source: {path_or_device}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    is_file = isinstance(path_or_device, str) and os.path.exists(path_or_device)

    def frames() -> Iterator[np.ndarray]:
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    return
                yield frame
        finally:
            cap.release()

    return paced(frames(), fps) if (is_file and realtime) else frames()


def conveyor_simulation(
    item_paths: Sequence[str],
    fps: float = 30.0,
    size: Tuple[int, int] = (1280, 480),
    part_px: int = 300,
    speed_px_frame: float = 12.0,
    pitch_px: int = 420,
    seed: int = 0,
    realtime: bool = True,
    lead_frames: int = 10,
) -> Iterator[np.ndarray]:
    """SIMULATION. Real part photographs ride a rendered belt.

    The parts are real images. The belt, the motion and the timing are generated. It exercises
    tracking and pacing, and proves nothing about optics or physical conveyor behaviour.
    """
    w, h = size
    rng = np.random.default_rng(seed)
    belt = np.full((h, w, 3), (58, 56, 54), dtype=np.uint8)
    belt = np.clip(belt.astype(np.int16) + rng.integers(-3, 4, (h, w, 1)), 0, 255).astype(np.uint8)
    for x in range(0, w, 120):
        belt[:, x:x + 1] = (72, 70, 68)
    top = (h - part_px) // 2

    parts = [cv2.resize(cv2.imread(p), (part_px, part_px), interpolation=cv2.INTER_AREA) for p in item_paths]

    def frames() -> Iterator[np.ndarray]:
        for _ in range(lead_frames):
            yield belt.copy()
        total = (w + part_px + pitch_px * len(parts)) / speed_px_frame
        for i in range(int(total) + 1):
            frame = belt.copy()
            offset = i * speed_px_frame
            for n, part in enumerate(parts):
                x = int(offset - part_px - n * pitch_px)
                x0, x1 = max(0, x), min(w, x + part_px)
                if x1 > x0:
                    frame[top:top + part_px, x0:x1] = part[:, x0 - x:x1 - x]
            yield frame

    return paced(frames(), fps) if realtime else frames()


def sample_paths(folder: str, limit: Optional[int] = None, seed: int = 0) -> List[str]:
    """Images under folder, including good/ and defect/ subfolders, in a fixed shuffled order.

    The shuffle mixes good and defective parts the way a line would; the fixed seed keeps a run repeatable.
    """
    import random
    paths = sorted(os.path.join(root, n) for root, _, files in os.walk(folder)
                   for n in files if n.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")))
    random.Random(seed).shuffle(paths)
    return paths[:limit]
