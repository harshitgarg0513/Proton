from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageStat
from skimage.filters.rank import entropy as local_entropy
from skimage.morphology import disk


@dataclass(frozen=True)
class ImageAnalysisResult:
    width: int
    height: int
    entropy: float
    color_variance: float
    noise_estimation: float
    edge_density: float
    dominant_colors: list[str]
    media_type: str = "image"


class ImageAnalyzer:
    def __init__(self, source_path: str) -> None:
        self.source_path = source_path

    def analyze(self) -> dict:
        with Image.open(self.source_path) as image:
            rgb_image = image.convert("RGB")
            width, height = rgb_image.size
            np_image = np.array(rgb_image)

            grayscale = cv2.cvtColor(np_image, cv2.COLOR_RGB2GRAY)
            edge_map = cv2.Canny(grayscale, 100, 200)
            entropy_map = local_entropy(grayscale, disk(5))
            dominant_colors = self._dominant_colors(rgb_image)

            stats = ImageStat.Stat(rgb_image)
            color_variance = float(sum(stats.var) / len(stats.var))
            noise_estimation = float(np.std(cv2.Laplacian(grayscale, cv2.CV_64F)))
            edge_density = float(np.count_nonzero(edge_map) / edge_map.size)

            result = ImageAnalysisResult(
                width=width,
                height=height,
                entropy=float(np.mean(entropy_map)),
                color_variance=color_variance,
                noise_estimation=noise_estimation,
                edge_density=edge_density,
                dominant_colors=dominant_colors,
            )

            return result.__dict__

    def _dominant_colors(self, image: Image.Image, count: int = 5) -> list[str]:
        reduced = image.resize((64, 64))
        pixels = list(reduced.getdata())
        clusters = Counter(pixels).most_common(count)
        return ["#{:02x}{:02x}{:02x}".format(*rgb) for rgb, _ in clusters]
