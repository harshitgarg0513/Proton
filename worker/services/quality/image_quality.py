from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio, structural_similarity


class ImageQualityMetric:
    def __init__(self, original_path: str, optimized_path: str) -> None:
        self.original_path = original_path
        self.optimized_path = optimized_path

    def compute(self) -> dict:
        original = self._load_image(self.original_path)
        optimized = self._load_image(self.optimized_path)
        optimized = cv2.resize(optimized, (original.shape[1], original.shape[0]))

        ssim_score = structural_similarity(original, optimized, data_range=255)
        psnr_score = peak_signal_noise_ratio(original, optimized, data_range=255)

        return {
            "ssim": round(float(ssim_score), 4),
            "psnr": round(float(psnr_score), 4),
        }

    @staticmethod
    def _load_image(path: str) -> np.ndarray:
        with Image.open(path) as image:
            return np.array(image.convert("L"))
