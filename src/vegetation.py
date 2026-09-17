import cv2
import numpy as np
from PIL import Image
from .types import DetectionCandidate


class VegetationDetector:
    def __init__(self, config: dict):
        self.config = config

    def mask(self, image: Image.Image) -> np.ndarray:
        rgb = np.asarray(image.convert("RGB"))
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        cfg = self.config
        h = cfg["hsv"]
        green = cv2.inRange(hsv, np.array([h["lower_h"], h["lower_s"], h["lower_v"]]),
                            np.array([h["upper_h"], h["upper_s"], h["upper_v"]]))
        r, g, b = rgb.astype(np.int16).transpose(2, 0, 1)
        exg = ((2*g-r-b) > cfg["exg"]["threshold"]).astype(np.uint8)*255
        method = cfg["method"]
        if method not in {"hsv", "exg", "combined"}:
            raise ValueError("Unknown vegetation method")
        mask = green if method == "hsv" else exg if method == "exg" else cv2.bitwise_and(green, exg)
        for name, operation in [("open_kernel", cv2.MORPH_OPEN), ("close_kernel", cv2.MORPH_CLOSE)]:
            size = cfg["morphology"][name]
            if size > 0:
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
                mask = cv2.morphologyEx(mask, operation, kernel)
        return mask

    def candidates(self, mask: np.ndarray) -> list[DetectionCandidate]:
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        c = self.config["components"]
        result = []
        for x, y, w, h, area in stats[1:count]:
            if (area >= c["min_area"] and area <= mask.size*c["max_area_ratio"]
                    and w >= c["min_width"] and h >= c["min_height"]
                    and area/(w*h) >= c["min_fill_ratio"]):
                result.append(DetectionCandidate(int(x), int(y), int(x+w), int(y+h)))
        return result

    def detect(self, image: Image.Image) -> list[DetectionCandidate]:
        return self.candidates(self.mask(image))
