from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


@dataclass(frozen=True)
class PdfAnalysisResult:
    page_count: int
    text_character_count: int
    image_count: int
    embedded_asset_count: int
    text_density: float
    image_density: float
    media_type: str = "pdf"


class PdfAnalyzer:
    def __init__(self, source_path: str) -> None:
        self.source_path = source_path

    def analyze(self) -> dict:
        document = fitz.open(self.source_path)
        try:
            page_count = document.page_count
            text_character_count = 0
            image_count = 0
            embedded_asset_count = 0

            for page in document:
                text_character_count += len(page.get_text("text"))
                image_count += len(page.get_images(full=True))
                embedded_asset_count += len(page.get_images(full=True)) + len(page.get_links())

            total_density_base = max(page_count, 1)
            text_density = text_character_count / total_density_base
            image_density = image_count / total_density_base

            result = PdfAnalysisResult(
                page_count=page_count,
                text_character_count=text_character_count,
                image_count=image_count,
                embedded_asset_count=embedded_asset_count,
                text_density=text_density,
                image_density=image_density,
            )
            return result.__dict__
        finally:
            document.close()
