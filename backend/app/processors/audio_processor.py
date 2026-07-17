from __future__ import annotations

import subprocess
from pathlib import Path
from time import perf_counter

from app.processors.base_processor import BaseProcessor
from app.services.analyzers.audio_analyzer import AudioAnalyzer
from app.services.fallback import keep_original_if_larger


class AudioProcessor(BaseProcessor):
    SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}

    _PROFILE_SETTINGS = {
        "smallest_size": {"codec": "libopus", "bitrate": "64k", "extension": "opus"},
        "balanced": {"codec": "libopus", "bitrate": "96k", "extension": "opus"},
        "web_optimized": {"codec": "libopus", "bitrate": "96k", "extension": "opus"},
        "best_quality": {"codec": "aac", "bitrate": "192k", "extension": "m4a"},
    }

    def __init__(self, source_path: str, profile: str, output_dir: str) -> None:
        super().__init__(source_path, profile)
        self.output_dir = Path(output_dir)
        self.analysis: dict | None = None
        self.optimized_path: str | None = None
        self.optimization_applied: bool | None = None
        self.codec_used: str | None = None
        self.processing_time: float | None = None

    def analyze(self) -> dict:
        self.analysis = AudioAnalyzer(self.source_path).analyze()
        return self.analysis

    def validate(self) -> None:
        if Path(self.source_path).suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError("Unsupported audio type")

    def optimize(self) -> dict:
        self.validate()
        started_at = perf_counter()
        if self.analysis is None:
            self.analyze()

        profile_key = (self.profile or "balanced").lower()
        settings = self._PROFILE_SETTINGS.get(profile_key, self._PROFILE_SETTINGS["balanced"])

        source_bitrate = int(self.analysis.get("bitrate") or 0)
        target_bitrate = settings["bitrate"]
        if source_bitrate and source_bitrate < int(target_bitrate.rstrip("k")) * 1000:
            target_bitrate = f"{max(source_bitrate // 1000, 32)}k"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = self.output_dir / f"{Path(self.source_path).stem}.{settings['extension']}"

        command = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-i",
            self.source_path,
            "-vn",
            "-c:a",
            settings["codec"],
            "-b:a",
            target_bitrate,
            str(candidate_path),
        ]
        completed = self._run_command(command)

        final_path, final_size, applied = keep_original_if_larger(self.source_path, str(candidate_path))
        self.optimized_path = final_path
        self.optimization_applied = applied
        self.codec_used = settings["codec"] if applied else "none"
        self.processing_time = perf_counter() - started_at

        return {
            "optimized_path": self.optimized_path,
            "thumbnail_path": None,
            "codec_used": self.codec_used,
            "format_after": settings["extension"].upper() if applied else str(self.analysis.get("codec", "original")).upper(),
            "optimized_size": final_size,
            "processing_time": self.processing_time,
            "recommendation": {
                "recommended_codec": settings["codec"],
                "target_bitrate": target_bitrate,
                "optimization_applied": applied,
                "optimization_result": (
                    "Compression applied successfully." if applied else "Original audio retained because transcoding increased file size."
                ),
                "reasoning": "Opus outperforms AAC/MP3 at low-mid bitrates for size; best_quality keeps AAC for compatibility.",
            },
        }

    def generate_report(self) -> dict:
        if self.analysis is None or self.optimized_path is None or self.processing_time is None:
            raise ValueError("Audio must be analyzed and optimized before report generation")

        original_size = Path(self.source_path).stat().st_size
        optimized_size = Path(self.optimized_path).stat().st_size
        compression_ratio = round((1 - (optimized_size / original_size)) * 100, 2) if original_size else 0.0

        return {
            "media_type": "audio",
            "original_size": original_size,
            "optimized_size": optimized_size,
            "compression_ratio": compression_ratio,
            "format_before": str(self.analysis.get("codec", "unknown")).upper(),
            "format_after": Path(self.optimized_path).suffix.lstrip(".").upper(),
            "processing_time": round(self.processing_time, 4),
            "profile_used": self.profile,
            "codec_used": self.codec_used,
            "thumbnail_path": None,
            "analysis": self.analysis,
            "quality_metrics": None,
            "benchmark_results": None,
            "chunk_plan": None,
        }

    @staticmethod
    def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ffmpeg timed out after 600s: {' '.join(command[:6])}...") from exc

        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Audio encode failed")
        return completed
