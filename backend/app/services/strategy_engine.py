from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VideoOptimizationPlan:
    codec: str
    preset: str
    crf: int
    max_width: int
    max_height: int
    audio_bitrate: str
    scale_label: str


@dataclass(frozen=True)
class OptimizationRecommendation:
    recommended_codec: str
    expected_size_reduction: str
    quality_estimate: str
    processing_time: str
    reasoning: str


class OptimizationStrategy:
    def __init__(self, analysis: dict, profile: str) -> None:
        self.analysis = analysis
        self.profile = (profile or "balanced").lower()

    def select_codec(self) -> str:
        if self.profile == "smallest_size":
            return "AV1" if self.analysis.get("media_type") == "image" else "H265"
        if self.profile == "best_quality":
            return "WebP" if self.analysis.get("media_type") == "image" else "H264"
        if self.profile == "web_optimized":
            return "WebP" if self.analysis.get("media_type") == "image" else "H264"
        if self.analysis.get("media_type") == "video" and float(self.analysis.get("motion_intensity") or 0.0) > 0.35:
            return "H264"
        if self.analysis.get("media_type") == "video" and float(self.analysis.get("duration") or 0.0) > 20 * 60:
            return "H265"
        return "WebP" if self.analysis.get("media_type") == "image" else "H265"

    def select_bitrate(self) -> str:
        bitrate = int(self.analysis.get("bitrate") or 0)
        if bitrate <= 0:
            return "128k"
        if self.profile == "smallest_size":
            return "96k"
        if self.profile == "best_quality":
            return "160k"
        if bitrate > 8_000_000:
            return "128k"
        return "120k"

    def select_resolution(self) -> tuple[int, int]:
        width = int(self.analysis.get("width") or 0)
        height = int(self.analysis.get("height") or 0)
        if self.profile == "smallest_size":
            return min(width or 1280, 1280), min(height or 720, 720)
        if self.profile == "best_quality":
            return max(width or 1920, 1920), max(height or 1080, 1080)
        if width > 1920 or height > 1080:
            return 1920, 1080
        return width or 1280, height or 720

    def recommend(self) -> OptimizationRecommendation:
        codec = self.select_codec()
        bitrate = int(self.analysis.get("bitrate") or 0)
        motion_intensity = float(self.analysis.get("motion_intensity") or 0.0)

        if self.analysis.get("media_type") == "image":
            size_reduction = "62%" if codec == "AV1" else "45%"
            quality_estimate = "high" if float(self.analysis.get("entropy") or 0.0) < 6 else "balanced"
            processing_time = "slow" if codec == "AV1" else "medium"
            reasoning = "image entropy and edge density guide the codec choice"
        else:
            if motion_intensity > 0.45:
                size_reduction = "35%"
                quality_estimate = "high"
                processing_time = "medium"
                reasoning = "high motion favors preserving temporal detail"
            elif bitrate > 8_000_000:
                size_reduction = "55%"
                quality_estimate = "medium"
                processing_time = "slow"
                reasoning = "high bitrate allows more aggressive compression"
            else:
                size_reduction = "48%"
                quality_estimate = "high"
                processing_time = "medium"
                reasoning = "balanced content is suitable for adaptive compression"

        return OptimizationRecommendation(
            recommended_codec=codec,
            expected_size_reduction=size_reduction,
            quality_estimate=quality_estimate,
            processing_time=processing_time,
            reasoning=reasoning,
        )


def ffmpeg_codec_for(codec: str) -> str:
    normalized = codec.upper()
    mapping = {
        "H264": "libx264",
        "H265": "libx265",
        "VP9": "libvpx-vp9",
        "AV1": "libaom-av1",
        "WEBP": "WEBP",
    }
    return mapping.get(normalized, codec)


def crf_for_codec(codec: str, base_crf: int, base_codec: str = "libx264") -> int:
    """Convert a CRF tuned for base_codec into an equivalent CRF for codec."""
    if codec == base_codec:
        return base_crf
    if codec == "libx265":
        return min(base_crf + 6, 51)
    if codec == "libvpx-vp9":
        return min(round(base_crf * 1.4), 63)
    return base_crf


def resolve_video_plan(profile: str, analysis: dict) -> VideoOptimizationPlan:
    strategy = OptimizationStrategy({**analysis, "media_type": "video"}, profile)
    recommended_codec = ffmpeg_codec_for(strategy.select_codec())
    duration = float(analysis.get("duration") or 0.0)
    bitrate = int(analysis.get("bitrate") or 0)
    width = int(analysis.get("width") or 0)
    height = int(analysis.get("height") or 0)
    profile_name = (profile or "balanced").lower()

    if profile_name == "smallest_size":
        return VideoOptimizationPlan(
            codec=recommended_codec if recommended_codec != "WEBP" else "libx265",
            preset="medium",
            crf=28,
            max_width=1280,
            max_height=720,
            audio_bitrate="96k",
            scale_label="aggressive",
        )

    if profile_name == "best_quality":
        return VideoOptimizationPlan(
            codec=recommended_codec if recommended_codec != "WEBP" else "libx264",
            preset="slow",
            crf=18,
            max_width=3840,
            max_height=2160,
            audio_bitrate="160k",
            scale_label="quality",
        )

    if profile_name == "web_optimized":
        return VideoOptimizationPlan(
            codec=recommended_codec if recommended_codec != "WEBP" else "libx264",
            preset="fast",
            crf=21,
            max_width=1280,
            max_height=720,
            audio_bitrate="128k",
            scale_label="web",
        )

    if duration > 20 * 60 or bitrate > 8_000_000 or max(width, height) > 1920:
        return VideoOptimizationPlan(
            codec=recommended_codec if recommended_codec != "WEBP" else "libx265",
            preset="medium",
            crf=26,
            max_width=1280,
            max_height=720,
            audio_bitrate="128k",
            scale_label="adaptive-large",
        )

    return VideoOptimizationPlan(
        codec=recommended_codec if recommended_codec != "WEBP" else "libx264",
        preset="medium",
        crf=23,
        max_width=1920,
        max_height=1080,
        audio_bitrate="128k",
        scale_label="balanced",
    )

