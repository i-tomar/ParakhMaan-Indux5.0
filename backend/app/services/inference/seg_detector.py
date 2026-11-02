"""YOLO instance-segmentation inference on ONNX Runtime, without PyTorch or Ultralytics.

Expected export: `model.export(format="onnx", nms=False)`:
    output 0: (1, 4 + classes + mask_dim, N) boxes in input pixels (cx, cy, w, h), sigmoid scores
    output 1: (1, mask_dim, H, W) prototype masks
"""
import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


def _letterbox(image: np.ndarray, size: int) -> Tuple[np.ndarray, float, int, int]:
    h, w = image.shape[:2]
    r = size / max(h, w)
    nw, nh = int(round(w * r)), int(round(h * r))
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_AREA if r < 1 else cv2.INTER_LINEAR)
    dx, dy = (size - nw) // 2, (size - nh) // 2
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[dy:dy + nh, dx:dx + nw] = resized
    return canvas, r, dx, dy


class SegDetector:
    def __init__(self, model_path: str, classes: Optional[List[str]] = None, conf: float = 0.25, iou: float = 0.5,
                 threads: int = 0):
        import onnxruntime as ort

        if not os.path.exists(model_path):
            raise FileNotFoundError(model_path)
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(model_path, options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.input_size = int(self.session.get_inputs()[0].shape[2])
        self.providers = self.session.get_providers()
        self.conf, self.iou = conf, iou
        self.classes = classes or self._metadata_classes()
        self._lock = threading.Lock()

    def _metadata_classes(self) -> List[str]:
        names = self.session.get_modelmeta().custom_metadata_map.get("names")
        if not names:
            return []
        import ast
        return [str(v) for _, v in sorted(ast.literal_eval(names).items())]

    def detect(self, image: np.ndarray, conf: Optional[float] = None) -> List[Dict[str, Any]]:
        threshold = self.conf if conf is None else conf
        h0, w0 = image.shape[:2]
        canvas, r, dx, dy = _letterbox(image, self.input_size)
        blob = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
        with self._lock:
            outputs = self.session.run(None, {self.input_name: blob})
        pred, protos = outputs[0][0].T, outputs[1][0]  # (N, 4+nc+nm), (nm, H, W)
        nm = protos.shape[0]
        nc = pred.shape[1] - 4 - nm
        boxes, scores, coefs = pred[:, :4], pred[:, 4:4 + nc], pred[:, 4 + nc:]
        class_ids, confs = scores.argmax(1), scores.max(1)
        keep = confs >= threshold
        if not keep.any():
            return []
        boxes, class_ids, confs, coefs = boxes[keep], class_ids[keep], confs[keep], coefs[keep]
        xyxy = np.stack([boxes[:, 0] - boxes[:, 2] / 2, boxes[:, 1] - boxes[:, 3] / 2,
                         boxes[:, 0] + boxes[:, 2] / 2, boxes[:, 1] + boxes[:, 3] / 2], axis=1)
        xywh = np.stack([xyxy[:, 0], xyxy[:, 1], boxes[:, 2], boxes[:, 3]], axis=1)
        # Class-aware NMS, by offsetting each class into its own coordinate range.
        offset = (class_ids[:, None] * self.input_size * 2).astype(np.float32)
        idx = cv2.dnn.NMSBoxes((xywh + np.hstack([offset, offset, 0 * offset, 0 * offset])).tolist(),
                               confs.astype(float).tolist(), threshold, self.iou)
        results = []
        ph, pw = protos.shape[1:]
        scale_x, scale_y = pw / self.input_size, ph / self.input_size
        for i in np.array(idx).flatten():
            mask_logits = (coefs[i] @ protos.reshape(nm, -1)).reshape(ph, pw)
            x1, y1, x2, y2 = xyxy[i]
            crop = np.zeros_like(mask_logits, dtype=bool)
            crop[max(0, int(y1 * scale_y)):int(np.ceil(y2 * scale_y)), max(0, int(x1 * scale_x)):int(np.ceil(x2 * scale_x))] = True
            full = cv2.resize(mask_logits * crop, (self.input_size, self.input_size), interpolation=cv2.INTER_LINEAR) > 0
            nh, nw = int(round(h0 * r)), int(round(w0 * r))
            unpadded = full[dy:dy + nh, dx:dx + nw].astype(np.uint8)
            mask = cv2.resize(unpadded, (w0, h0), interpolation=cv2.INTER_NEAREST).astype(bool)
            cid = int(class_ids[i])
            results.append({
                "defect_type": self.classes[cid] if cid < len(self.classes) else f"CLASS_{cid}",
                "bbox": [float((x1 - dx) / r), float((y1 - dy) / r), float((x2 - dx) / r), float((y2 - dy) / r)],
                "confidence": float(confs[i]),
                "detector": "YOLO_SEG",
                "mask": mask,
            })
        return results


def mask_to_polygon(mask: np.ndarray, max_points: int = 80) -> List[List[float]]:
    """Largest contour of a mask, simplified, in image pixels (the UI draws this as an SVG path)."""
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    c = max(contours, key=cv2.contourArea)
    eps = 0.002 * cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, eps, True)
    while len(approx) > max_points:
        eps *= 1.5
        approx = cv2.approxPolyDP(c, eps, True)
    return [[float(x), float(y)] for x, y in approx.reshape(-1, 2)]


def load_metadata(model_path: str) -> Dict[str, Any]:
    path = os.path.splitext(model_path)[0] + ".json"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}
