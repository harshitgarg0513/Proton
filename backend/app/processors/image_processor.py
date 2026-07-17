from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from PIL import Image, ImageOps
from app.processors.base_processor import BaseProcessor
from app.services.analyzers.image_analyzer import ImageAnalyzer
from app.services.quality.image_quality import ImageQualityMetric
from app.services.strategy_engine import OptimizationStrategy
from app.services.fallback import keep_original_if_larger


@dataclass(frozen=True)
class ImageOptimizationResult:
    optimized_path: str
    thumbnail_path: str | None
    codec_used: str
    format_after: str
    optimized_size: int
    processing_time: float


class ImageProcessor(BaseProcessor):
    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}

    def __init__(self, source_path: str, profile: str, output_dir: str) -> None:
        super().__init__(source_path, profile)
        self.output_dir = Path(output_dir)
        self.analysis: dict | None = None
        self.result: ImageOptimizationResult | None = None
        self.recommendation: dict | None = None
        self.quality_metrics: dict | None = None

    def analyze(self) -> dict:
        self.analysis = ImageAnalyzer(self.source_path).analyze()
        with Image.open(self.source_path) as image:
            self.analysis.update(
                {
                    "format_before": image.format or Path(self.source_path).suffix.lstrip(".").upper(),
                    "mode": image.mode,
                    "has_transparency": "A" in image.getbands(),
                }
            )

        return self.analysis

    def validate(self) -> None:
        if Path(self.source_path).suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError("Unsupported image type")

    def optimize(self) -> dict:
        self.validate()
        started_at = perf_counter()

        analysis = self.analysis or self.analyze()
        strategy = OptimizationStrategy({**analysis, "media_type": "image"}, self.profile)
        recommendation = strategy.recommend()

        profile_settings = {
            "smallest_size": {"quality": 35, "max_side": 1920, "formats": ["AVIF", "WEBP"], "thumbnail": True},
            "balanced": {"quality": 65, "max_side": 2560, "formats": ["WEBP"], "thumbnail": False},
            "best_quality": {"quality": 90, "max_side": 3840, "formats": ["WEBP"], "thumbnail": False},
            "web_optimized": {"quality": 70, "max_side": 1920, "formats": ["WEBP"], "thumbnail": True},
        }
        settings = profile_settings.get(self.profile, profile_settings["balanced"])
        quality_adjustment = 0
        if float(analysis.get("entropy") or 0.0) > 6.0:
            quality_adjustment += 5
        if float(analysis.get("noise_estimation") or 0.0) > 40.0:
            quality_adjustment += 5
        if float(analysis.get("edge_density") or 0.0) < 0.05:
            quality_adjustment -= 5
        adaptive_quality = max(25, min(95, settings["quality"] + quality_adjustment))

        self.output_dir.mkdir(parents=True, exist_ok=True)
        optimized_path, codec_used, format_after = self._render_optimized_file({**settings, "quality": adaptive_quality})
        optimized_path, optimized_size, optimization_applied = keep_original_if_larger(self.source_path, optimized_path)
        thumbnail_path = self._render_thumbnail(optimized_path) if settings["thumbnail"] else None
        self.quality_metrics = ImageQualityMetric(self.source_path, optimized_path).compute()
        self.recommendation = {
            "recommended_codec": recommendation.recommended_codec,
            "expected_size_reduction": recommendation.expected_size_reduction,
            "quality_estimate": recommendation.quality_estimate,
            "processing_time": recommendation.processing_time,
            "reasoning": recommendation.reasoning,
            "optimization_applied": optimization_applied,
            "optimization_result": (
                "Compression applied successfully."
                if optimization_applied
                else "Original image retained because optimization increased file size."
            ),
        }

        self.result = ImageOptimizationResult(
            optimized_path=optimized_path,
            thumbnail_path=thumbnail_path,
            codec_used=codec_used,
            format_after=format_after,
            optimized_size=optimized_size,
            processing_time=perf_counter() - started_at,
        )

        return {
            "optimized_path": self.result.optimized_path,
            "thumbnail_path": self.result.thumbnail_path,
            "codec_used": self.result.codec_used,
            "format_after": self.result.format_after,
            "optimized_size": self.result.optimized_size,
            "processing_time": self.result.processing_time,
            "quality_metrics": self.quality_metrics,
            "recommendation": self.recommendation,
        }

    def generate_report(self) -> dict:
        if self.analysis is None or self.result is None:
            raise ValueError("Image must be analyzed and optimized before report generation")

        original_size = Path(self.source_path).stat().st_size
        compression_ratio = 0.0
        if original_size > 0:
            compression_ratio = round((1 - (self.result.optimized_size / original_size)) * 100, 2)

        recommendation = dict(self.recommendation or {})
        recommendation.update(
            {
                "optimization_applied": self.result.optimized_size < original_size,
                "optimization_result": (
                    "Compression applied successfully."
                    if self.result.optimized_size < original_size
                    else "Original image retained because optimization increased file size."
                ),
            }
        )

        return {
            "media_type": "image",
            "original_size": original_size,
            "optimized_size": self.result.optimized_size,
            "compression_ratio": compression_ratio,
            "format_before": self.analysis["format_before"],
            "format_after": self.result.format_after,
            "processing_time": round(self.result.processing_time, 4),
            "profile_used": self.profile,
            "codec_used": self.result.codec_used,
            "thumbnail_path": self.result.thumbnail_path,
            "analysis": self.analysis,
            "quality_metrics": self.quality_metrics,
            "recommendation": recommendation,
        }

    def _render_optimized_file(self, settings: dict) -> tuple[str, str, str]:
        with Image.open(self.source_path) as image:
            image = ImageOps.exif_transpose(image)
            resized_image = self._resize(image, settings["max_side"])

        candidates: list[tuple[str, str, int]] = []
        for candidate_format in settings["formats"]:
            extension = self._extension_for_format(candidate_format)
            output_path = self.output_dir / f"{Path(self.source_path).stem}_{extension}.{extension}"
            try:
                save_kwargs = {"optimize": True, "quality": settings["quality"]}
                if candidate_format == "WEBP":
                    save_kwargs["method"] = 6
                resized_image.save(output_path, format=candidate_format, **save_kwargs)
                candidates.append((str(output_path), candidate_format, output_path.stat().st_size))
            except Exception:
                continue

        if not candidates:
            fallback_path = self.output_dir / f"{Path(self.source_path).stem}.webp"
            resized_image.save(fallback_path, format="WEBP", optimize=True, quality=settings["quality"], method=6)
            return str(fallback_path), "webp", "WEBP"

        best_path, best_format, _ = min(candidates, key=lambda item: item[2])
        final_path = self.output_dir / f"{Path(self.source_path).stem}.{self._extension_for_format(best_format)}"
        Path(best_path).replace(final_path)
        for path, _, _ in candidates:
            if path != best_path:
                Path(path).unlink(missing_ok=True)

        return str(final_path), best_format.lower(), best_format

    def _render_thumbnail(self, optimized_path: str) -> str:
        thumbnail_path = self.output_dir / f"{Path(optimized_path).stem}_thumb.webp"
        with Image.open(optimized_path) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            image.save(thumbnail_path, format="WEBP", optimize=True, quality=60, method=6)
        return str(thumbnail_path)

    def _resize(self, image: Image.Image, max_side: int) -> Image.Image:
        if max(image.width, image.height) <= max_side:
            return image.copy()

        ratio = max_side / max(image.width, image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))
        return image.resize(new_size, Image.Resampling.LANCZOS)

    @staticmethod
    def _extension_for_format(image_format: str) -> str:
        return {
            "AVIF": "avif",
            "WEBP": "webp",
            "JPEG": "jpg",
            "JPG": "jpg",
            "PNG": "png",
        }.get(image_format.upper(), image_format.lower())
