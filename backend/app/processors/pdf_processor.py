from __future__ import annotations

import io
from pathlib import Path
from time import perf_counter

import fitz
from PIL import Image

from app.processors.base_processor import BaseProcessor
from app.services.analyzers.pdf_analyzer import PdfAnalyzer
from app.services.fallback import keep_original_if_larger


class PdfProcessor(BaseProcessor):
    SUPPORTED_EXTENSIONS = {".pdf"}

    def __init__(self, source_path: str, profile: str, output_dir: str) -> None:
        super().__init__(source_path, profile)
        self.output_dir = Path(output_dir)
        self.analysis: dict | None = None
        self.optimized_path: str | None = None
        self.processing_time: float | None = None
        self.images_recompressed = 0

    def analyze(self) -> dict:
        self.analysis = PdfAnalyzer(self.source_path).analyze()
        return self.analysis

    def validate(self) -> None:
        if Path(self.source_path).suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError("Unsupported PDF type")

    def optimize(self) -> dict:
        self.validate()
        started_at = perf_counter()
        if self.analysis is None:
            self.analyze()

        recommendation = self._build_recommendation()
        save_options = self._save_options_for_profile()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{Path(self.source_path).stem}.optimized.pdf"

        document = fitz.open(self.source_path)
        try:
            images_recompressed = self._recompress_images(document)
            self.images_recompressed = images_recompressed
            document.ez_save(str(output_path), **save_options)
        finally:
            document.close()

        output_path, optimized_size, optimization_applied = keep_original_if_larger(self.source_path, str(output_path))

        self.optimized_path = str(output_path)
        self.processing_time = perf_counter() - started_at
        recommendation = {
            **recommendation,
            "images_recompressed": self.images_recompressed,
            "optimization_applied": optimization_applied,
            "optimization_result": (
                "Compression applied successfully."
                if optimization_applied
                else "Original PDF retained because optimization increased file size."
            ),
        }
        return {
            "optimized_path": self.optimized_path,
            "thumbnail_path": None,
            "codec_used": None,
            "format_after": "PDF",
            "optimized_size": optimized_size,
            "processing_time": self.processing_time,
            "recommendation": recommendation,
        }

    def _image_quality_for_profile(self) -> int:
        return {
            "smallest_size": 45,
            "balanced": 60,
            "web_optimized": 65,
            "best_quality": 82,
        }.get((self.profile or "balanced").lower(), 60)

    def _image_max_dimension_for_profile(self) -> int:
        return {
            "smallest_size": 1280,
            "balanced": 1600,
            "web_optimized": 1600,
            "best_quality": 2400,
        }.get((self.profile or "balanced").lower(), 1600)

    def _recompress_images(self, document: "fitz.Document") -> int:
        quality = self._image_quality_for_profile()
        max_dim = self._image_max_dimension_for_profile()
        recompressed = 0
        seen_xrefs: set[int] = set()

        for page in document:
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                try:
                    base_image = document.extract_image(xref)
                except Exception:
                    continue

                original_bytes = base_image["image"]
                if base_image.get("ext") == "jpx":
                    continue

                try:
                    pil_image = Image.open(io.BytesIO(original_bytes))
                    pil_image.load()
                except Exception:
                    continue

                has_alpha = pil_image.mode in ("RGBA", "LA") or "transparency" in pil_image.info
                if has_alpha:
                    continue
                if pil_image.mode not in ("RGB", "L"):
                    pil_image = pil_image.convert("RGB")

                width, height = pil_image.size
                if max(width, height) > max_dim:
                    scale = max_dim / max(width, height)
                    pil_image = pil_image.resize(
                        (max(1, int(width * scale)), max(1, int(height * scale))),
                        Image.LANCZOS,
                    )

                buffer = io.BytesIO()
                pil_image.save(buffer, format="JPEG", quality=quality, optimize=True)
                new_bytes = buffer.getvalue()

                if len(new_bytes) >= len(original_bytes):
                    continue

                try:
                    page.replace_image(xref, stream=new_bytes)
                    recompressed += 1
                except Exception:
                    continue

        return recompressed

    def _save_options_for_profile(self) -> dict:
        profile = (self.profile or "balanced").lower()

        if profile == "smallest_size":
            return {
                "garbage": 4,
                "clean": True,
                "deflate": True,
                "deflate_images": True,
                "deflate_fonts": True,
                "incremental": False,
                "expand": False,
                "pretty": False,
                "no_new_id": True,
                "use_objstms": 1,
                "compression_effort": 9,
            }

        if profile == "best_quality":
            return {
                "garbage": 3,
                "clean": False,
                "deflate": True,
                "deflate_images": True,
                "deflate_fonts": True,
                "incremental": False,
                "expand": False,
                "pretty": False,
                "no_new_id": True,
                "use_objstms": 1,
                "compression_effort": 4,
            }

        if profile == "web_optimized":
            return {
                "garbage": 4,
                "clean": True,
                "deflate": True,
                "deflate_images": True,
                "deflate_fonts": True,
                "incremental": False,
                "expand": False,
                "pretty": False,
                "no_new_id": True,
                "use_objstms": 1,
                "compression_effort": 7,
            }

        return {
            "garbage": 4,
            "clean": True,
            "deflate": True,
            "deflate_images": True,
            "deflate_fonts": True,
            "incremental": False,
            "expand": False,
            "pretty": False,
            "no_new_id": True,
            "use_objstms": 1,
            "compression_effort": 6,
        }
    
    
    def _build_recommendation(self) -> dict:
        profile = (self.profile or "balanced").lower()
        save_options = self._save_options_for_profile()

        compression_level = {
            "smallest_size": "Maximum Compression",
            "balanced": "Balanced Compression",
            "best_quality": "Quality Preserving",
            "web_optimized": "Web Optimized",
        }.get(profile, "Balanced Compression")

        return {
            "compression_method": "PyMuPDF Object Stream Optimization",
            "compression_level": compression_level,
            "garbage_collection": save_options["garbage"],
            "object_streams": bool(save_options["use_objstms"]),
            "deflate_images": save_options["deflate_images"],
            "deflate_fonts": save_options["deflate_fonts"],
            "compression_effort": save_options["compression_effort"],
            "reasoning": (
                "PDF optimization removes unused objects, compresses streams, "
                "and reduces embedded asset size without changing document content."
            ),
        }

    def generate_report(self) -> dict:
        if self.analysis is None or self.optimized_path is None or self.processing_time is None:
            raise ValueError("PDF must be analyzed and optimized before report generation")

        original_size = Path(self.source_path).stat().st_size
        optimized_size = Path(self.optimized_path).stat().st_size
        optimization_applied = optimized_size < original_size
        compression_ratio = 0.0
        if original_size > 0:
            compression_ratio = round((1 - (optimized_size / original_size)) * 100, 2)

        recommendation = self._build_recommendation()
        recommendation = {
            **recommendation,
            "images_recompressed": self.images_recompressed,
            "optimization_applied": optimization_applied,
            "optimization_result": (
                "Compression applied successfully."
                if optimization_applied
                else "Original PDF retained because optimization increased file size."
            ),
        }
        return {
            "media_type": "pdf",
            "original_size": original_size,
            "optimized_size": optimized_size,
            "compression_ratio": compression_ratio,
            "format_before": "PDF",
            "format_after": "PDF",
            "processing_time": round(self.processing_time, 4),
            "profile_used": self.profile,
            "codec_used": None,
            "thumbnail_path": None,
            "analysis": self.analysis,
            "quality_metrics": None,
            "benchmark_results": None,
            "chunk_plan": None,
            "recommendation": recommendation,
        }
