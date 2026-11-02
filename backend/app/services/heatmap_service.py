import os
import cv2
import numpy as np
import base64
from typing import List, Dict, Any, Optional

class HeatmapService:
    """
    Generates visual attention, text density, and quality saliency heatmaps
    for Legal Metrology package images.
    Combines OCR bounding box concentration, morphological text energy,
    and luminance gradients into a calibrated thermal map.
    """

    def generate_heatmap_image(
        self,
        image_path: str,
        ocr_spans: Optional[List[Dict[str, Any]]] = None,
        alpha: float = 0.55
    ) -> Optional[np.ndarray]:
        """
        Generates an overlaid thermal heatmap on top of the original package image.
        """
        if not os.path.exists(image_path):
            return None

        img = cv2.imread(image_path)
        if img is None:
            return None

        h, w = img.shape[:2]
        density_map = np.zeros((h, w), dtype=np.float32)

        # 1. Add energy from detected OCR bounding boxes
        if ocr_spans:
            for span in ocr_spans:
                bbox = span.get("bbox", [])
                if len(bbox) == 4:
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    x1 = max(0, min(w - 1, x1))
                    y1 = max(0, min(h - 1, y1))
                    x2 = max(0, min(w - 1, x2))
                    y2 = max(0, min(h - 1, y2))
                    if x2 > x1 and y2 > y1:
                        conf = float(span.get("confidence", 0.9))
                        # Create local Gaussian-like weight in bounding box
                        density_map[y1:y2, x1:x2] += conf * 2.0

        # 2. Add morphological text gradient energy
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
        norm_grad = cv2.normalize(grad.astype(np.float32), None, 0.0, 1.0, cv2.NORM_MINMAX)
        density_map += norm_grad * 1.2

        # 3. Apply Gaussian blur to create smooth thermal contours
        ksize = max(21, (min(w, h) // 25) | 1)
        blurred_density = cv2.GaussianBlur(density_map, (ksize, ksize), 0)

        # 4. Normalize to 0-255 uint8
        norm_density = cv2.normalize(blurred_density, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # 5. Apply Jet / Turbo colormap
        heatmap_color = cv2.applyColorMap(norm_density, cv2.COLORMAP_JET)

        # 6. Blend with original image
        blended = cv2.addWeighted(img, 1.0 - alpha, heatmap_color, alpha, 0)
        return blended

    def generate_heatmap_base64(
        self,
        image_path: str,
        ocr_spans: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[str]:
        """
        Returns Base64 encoded JPEG data URL of the blended heatmap.
        """
        blended = self.generate_heatmap_image(image_path, ocr_spans)
        if blended is None:
            return None

        success, buffer = cv2.imencode(".jpg", blended, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            return None

        b64_str = base64.b64encode(buffer).decode("utf-8")
        return f"data:image/jpeg;base64,{b64_str}"

    # --- Defect Inspection mode ---
    DEFECT_COLOURS_BGR = {
        "SCRATCH": (222, 117, 0),
        "CRACK": (107, 24, 192),
        "DENT": (0, 122, 224),
        "DISCOLOURATION": (143, 154, 10),
        "DIMENSIONAL_ANOMALY": (208, 63, 122),
        "UNKNOWN_ANOMALY": (18, 122, 109),
    }

    def generate_defect_overlay(
        self,
        image_path: str,
        detections: List[Dict[str, Any]],
        alpha: float = 0.35
    ) -> Optional[np.ndarray]:
        """
        Draws defect bounding boxes with a translucent glow, type label, and confidence.
        Rejected detections are skipped.
        """
        if not os.path.exists(image_path):
            return None
        img = cv2.imread(image_path)
        if img is None:
            return None

        h, w = img.shape[:2]
        glow = img.copy()
        thickness = max(2, int(round(min(h, w) / 300)))
        font_scale = max(0.45, min(h, w) / 1400)

        active = [d for d in detections if d.get("reviewer_status") != "REJECTED"]
        for det in active:
            bbox = det.get("bbox") or []
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(round(v)) for v in bbox]
            colour = self.DEFECT_COLOURS_BGR.get(det.get("defect_type", ""), (80, 80, 80))
            cv2.rectangle(glow, (x1, y1), (x2, y2), colour, -1)

        blended = cv2.addWeighted(glow, alpha, img, 1.0 - alpha, 0)

        for det in active:
            bbox = det.get("bbox") or []
            if len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(round(v)) for v in bbox]
            colour = self.DEFECT_COLOURS_BGR.get(det.get("defect_type", ""), (80, 80, 80))
            cv2.rectangle(blended, (x1, y1), (x2, y2), colour, thickness)
            label = f"{det.get('defect_type', 'DEFECT')} {det.get('severity', '')} {det.get('confidence', 0) * 100:.0f}%"
            (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
            ty = y1 - 4 if y1 - th - base - 4 > 0 else y2 + th + 4
            cv2.rectangle(blended, (x1, ty - th - base), (x1 + tw + 6, ty + base - 2), colour, -1)
            cv2.putText(blended, label, (x1 + 3, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)
        return blended

    def generate_defect_overlay_base64(self, image_path: str, detections: List[Dict[str, Any]]) -> Optional[str]:
        overlay = self.generate_defect_overlay(image_path, detections)
        if overlay is None:
            return None
        success, buffer = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not success:
            return None
        return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"

    def save_defect_overlay(self, image_path: str, detections: List[Dict[str, Any]], output_path: str) -> Optional[str]:
        overlay = self.generate_defect_overlay(image_path, detections)
        if overlay is None:
            return None
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        cv2.imwrite(output_path, overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return output_path

heatmap_service = HeatmapService()
