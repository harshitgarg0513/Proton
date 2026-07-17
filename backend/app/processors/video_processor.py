from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from app.processors.base_processor import BaseProcessor
from app.services.analyzers.video_analyzer import VideoAnalyzer
from app.services.benchmarking.video_benchmark import VideoBenchmarkEngine
from app.services.chunking.video_chunker import VideoChunker
from app.services.quality.video_quality import VideoQualityMetric
from app.services.fallback import keep_original_if_larger
from app.services.strategy_engine import OptimizationStrategy, VideoOptimizationPlan, crf_for_codec, ffmpeg_codec_for, resolve_video_plan


@dataclass(frozen=True)
class VideoOptimizationResult:
    optimized_path: str
    thumbnail_path: str | None
    codec_used: str
    format_after: str
    optimized_size: int
    processing_time: float
    optimization_applied: bool


class VideoProcessor(BaseProcessor):
    SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
    CHUNKABLE_PROFILES = frozenset({"smallest_size", "web_optimized"})
    CHUNK_DURATION_THRESHOLD_SECONDS = 60.0

    def __init__(self, source_path: str, profile: str, output_dir: str) -> None:
        super().__init__(source_path, profile)
        self.output_dir = Path(output_dir)
        self.analysis: dict | None = None
        self.plan: VideoOptimizationPlan | None = None
        self.result: VideoOptimizationResult | None = None
        self.recommendation: dict | None = None
        self.quality_metrics: dict | None = None
        self.benchmark_results: list[dict] | None = None
        self.chunk_plan: dict | None = None

    @classmethod
    def should_chunk(cls, profile: str, duration: float) -> bool:
        normalized_profile = (profile or "balanced").lower()
        return normalized_profile in cls.CHUNKABLE_PROFILES and duration > cls.CHUNK_DURATION_THRESHOLD_SECONDS

    @staticmethod
    def plan_to_dict(plan: VideoOptimizationPlan) -> dict:
        return asdict(plan)

    @staticmethod
    def plan_from_dict(payload: dict) -> VideoOptimizationPlan:
        return VideoOptimizationPlan(**payload)

    def analyze(self) -> dict:
        self.analysis = VideoAnalyzer(self.source_path).analyze()
        probe = self._probe_media()
        format_info = probe.get("format", {})
        streams = probe.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})

        self.analysis.update(
            {
                "width": int(video_stream.get("width") or self.analysis.get("width") or 0),
                "height": int(video_stream.get("height") or self.analysis.get("height") or 0),
                "codec": video_stream.get("codec_name") or self.analysis.get("codec") or "unknown",
                "bitrate": int(format_info.get("bit_rate") or video_stream.get("bit_rate") or self.analysis.get("bitrate") or 0),
                "duration": float(format_info.get("duration") or self.analysis.get("duration") or 0.0),
                "fps": self._parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or str(self.analysis.get("fps") or "0/1")),
                "format_before": (video_stream.get("codec_name") or Path(self.source_path).suffix.lstrip(".")).upper(),
                "container": format_info.get("format_name") or Path(self.source_path).suffix.lstrip("."),
                "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
            }
        )

        self.plan = resolve_video_plan(self.profile, self.analysis)
        return self.analysis

    def validate(self) -> None:
        if Path(self.source_path).suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise ValueError("Unsupported video type")

    def prepare_encode_plan(self) -> dict:
        analysis = self.analysis or self.analyze()
        strategy = OptimizationStrategy({**analysis, "media_type": "video"}, self.profile)
        recommendation = strategy.recommend()
        self.plan = self.plan or resolve_video_plan(self.profile, analysis)

        codec_override = ffmpeg_codec_for(recommendation.recommended_codec)
        if codec_override != "WEBP":
            self.plan = VideoOptimizationPlan(
                codec=codec_override,
                preset=self.plan.preset,
                crf=crf_for_codec(codec_override, self.plan.crf),
                max_width=self.plan.max_width,
                max_height=self.plan.max_height,
                audio_bitrate=self.plan.audio_bitrate,
                scale_label=self.plan.scale_label,
            )

        benchmark_results: list[dict] = []
        benchmark_source: str | None = self.source_path
        duration = float(analysis.get("duration") or 0.0)

        if duration > 30.0:
            clip_path = self.output_dir / f"_benchmark_clip_{Path(self.source_path).stem}.mp4"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._run_command([
                    "ffmpeg",
                    "-y",
                    "-nostdin",
                    "-ss",
                    "0",
                    "-i",
                    self.source_path,
                    "-t",
                    "10",
                    "-c",
                    "copy",
                    str(clip_path),
                ])
                benchmark_source = str(clip_path)
            except Exception:
                benchmark_source = None if duration > 30.0 else self.source_path

        if benchmark_source is not None:
            benchmark_results = VideoBenchmarkEngine(benchmark_source, str(self.output_dir / "benchmarks")).benchmark()
            if benchmark_results:
                best_codec = benchmark_results[0]["codec"]
                self.plan = VideoOptimizationPlan(
                    codec=best_codec,
                    preset=self.plan.preset,
                    crf=crf_for_codec(best_codec, self.plan.crf),
                    max_width=self.plan.max_width,
                    max_height=self.plan.max_height,
                    audio_bitrate=self.plan.audio_bitrate,
                    scale_label=self.plan.scale_label,
                )

        self.benchmark_results = benchmark_results
        self.recommendation = {
            "recommended_codec": recommendation.recommended_codec,
            "expected_size_reduction": recommendation.expected_size_reduction,
            "quality_estimate": recommendation.quality_estimate,
            "processing_time": recommendation.processing_time,
            "reasoning": recommendation.reasoning,
        }
        return analysis

    def optimize(self) -> dict:
        self.validate()
        started_at = perf_counter()
        analysis = self.prepare_encode_plan()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        optimized_path = self.output_dir / f"{Path(self.source_path).stem}.mp4"
        thumbnail_path = self.output_dir / f"{Path(self.source_path).stem}_thumb.jpg"

        chunk_plan = VideoChunker(self.source_path, str(self.output_dir)).plan(float(analysis.get("duration") or 0.0))
        self.chunk_plan = {
            "chunk_count": chunk_plan.chunk_count,
            "chunk_length_seconds": chunk_plan.chunk_length_seconds,
            "chunk_directory": chunk_plan.chunk_directory,
        }

        optimized_size, attempts, optimization_applied = self._encode_to_path(str(optimized_path), analysis)
        optimized_path, optimized_size, optimization_applied = keep_original_if_larger(self.source_path, str(optimized_path))

        self._extract_thumbnail(str(thumbnail_path), analysis)
        self.quality_metrics = VideoQualityMetric(self.source_path, str(optimized_path)).compute()
        self.recommendation = {
            **(self.recommendation or {}),
            "attempts": attempts,
            "optimization_applied": optimization_applied,
            "optimization_result": (
                "Compression applied successfully."
                if optimization_applied
                else "Original video retained because optimization increased file size."
            ),
        }

        self.result = VideoOptimizationResult(
            optimized_path=str(optimized_path),
            thumbnail_path=str(thumbnail_path),
            codec_used=self.plan.codec,
            format_after="MP4",
            optimized_size=optimized_size,
            processing_time=perf_counter() - started_at,
            optimization_applied=optimization_applied,
        )

        return {
            "optimized_path": self.result.optimized_path,
            "thumbnail_path": self.result.thumbnail_path,
            "codec_used": self.result.codec_used,
            "format_after": self.result.format_after,
            "optimized_size": self.result.optimized_size,
            "processing_time": self.result.processing_time,
            "quality_metrics": self.quality_metrics,
            "benchmark_results": self.benchmark_results,
            "chunk_plan": self.chunk_plan,
            "recommendation": self.recommendation,
        }

    def optimize_chunk(self, output_path: str | None = None) -> dict:
        self.validate()
        analysis = self.analysis or self.analyze()
        if self.plan is None:
            self.prepare_encode_plan()

        target_path = Path(output_path or self.output_dir / f"{Path(self.source_path).stem}.mp4")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        optimized_size, attempts, optimization_applied = self._encode_to_path(str(target_path), analysis)
        optimized_path, optimized_size, optimization_applied = keep_original_if_larger(self.source_path, str(target_path))

        return {
            "optimized_path": str(optimized_path),
            "optimized_size": optimized_size,
            "optimization_applied": optimization_applied,
            "attempts": attempts,
            "codec_used": self.plan.codec,
        }

    @staticmethod
    def merge_chunks(chunk_paths: list[str], output_path: str) -> str:
        if not chunk_paths:
            raise ValueError("At least one chunk path is required for merge")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        concat_list_path = output.parent / "concat_list.txt"

        with concat_list_path.open("w", encoding="utf-8") as handle:
            for chunk_path in chunk_paths:
                resolved = Path(chunk_path).resolve()
                handle.write(f"file '{resolved.as_posix()}'\n")

        VideoProcessor._run_command([
            "ffmpeg",
            "-y",
            "-nostdin",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ])
        return str(output)

    def generate_report(self) -> dict:
        if self.analysis is None or self.result is None:
            raise ValueError("Video must be analyzed and optimized before report generation")

        original_size = Path(self.source_path).stat().st_size
        compression_ratio = 0.0
        if original_size > 0:
            compression_ratio = round((1 - (self.result.optimized_size / original_size)) * 100, 2)

        return {
            "media_type": "video",
            "original_size": original_size,
            "optimized_size": self.result.optimized_size,
            "compression_ratio": compression_ratio,
            "format_before": self.analysis["format_before"],
            "format_after": self.result.format_after,
            "processing_time": round(self.result.processing_time, 4),
            "profile_used": self.profile,
            "codec_used": self.result.codec_used,
            "thumbnail_path": self.result.thumbnail_path,
            "quality_metrics": self.quality_metrics,
            "analysis": {
                "width": self.analysis["width"],
                "height": self.analysis["height"],
                "bitrate": self.analysis["bitrate"],
                "fps": self.analysis["fps"],
                "duration": self.analysis["duration"],
                "codec": self.analysis["codec"],
                "container": self.analysis["container"],
                "motion_intensity": self.analysis.get("motion_intensity"),
                "scene_change_frequency": self.analysis.get("scene_change_frequency"),
                "scene_complexity": self.analysis.get("scene_complexity"),
            },
            "strategy": {
                "codec": self.plan.codec,
                "preset": self.plan.preset,
                "crf": self.plan.crf,
                "scale": self.plan.scale_label,
            },
            "benchmark_results": self.benchmark_results,
            "chunk_plan": self.chunk_plan,
            "recommendation": self.recommendation,
        }

    def _encode_to_path(self, output_path: str, analysis: dict) -> tuple[int, int, bool]:
        command = self._build_encode_command(output_path, analysis)
        optimized_size, attempts = self._encode_with_retry(command, Path(output_path))
        return optimized_size, attempts, optimized_size < Path(self.source_path).stat().st_size

    def _build_encode_command(self, output_path: str, analysis: dict) -> list[str]:
        command = ["ffmpeg", "-y", "-nostdin", "-i", self.source_path, "-map", "0:v:0"]
        if analysis.get("has_audio"):
            command.extend(["-map", "0:a?", "-c:a", "aac", "-b:a", self.plan.audio_bitrate])
        else:
            command.append("-an")

        if self.plan.codec == "libvpx-vp9":
            command.extend(
                [
                    "-c:v",
                    self.plan.codec,
                    "-deadline",
                    self.plan.preset,
                    "-cpu-used",
                    "4",
                    "-crf",
                    str(self.plan.crf),
                    "-b:v",
                    "0",
                    "-movflags",
                    "+faststart",
                    "-vf",
                    self._build_scale_filter(self.plan, analysis),
                    output_path,
                ]
            )
        else:
            command.extend(
                [
                    "-c:v",
                    self.plan.codec,
                    "-preset",
                    self.plan.preset,
                    "-crf",
                    str(self.plan.crf),
                    "-movflags",
                    "+faststart",
                    "-vf",
                    self._build_scale_filter(self.plan, analysis),
                    output_path,
                ]
            )
        return command

    def _probe_media(self) -> dict:
        completed = self._run_command(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                self.source_path,
            ]
        )
        return json.loads(completed.stdout or "{}")

    def _extract_thumbnail(self, thumbnail_path: str, analysis: dict) -> None:
        second = "1"
        if analysis.get("duration", 0) and analysis["duration"] > 2:
            second = str(min(max(1, int(analysis["duration"] * 0.1)), max(int(analysis["duration"]) - 1, 1)))

        self._run_thumbnail_attempt(thumbnail_path, second)

        if not Path(thumbnail_path).exists() or Path(thumbnail_path).stat().st_size == 0:
            self._run_thumbnail_attempt(thumbnail_path, "0")

        if not Path(thumbnail_path).exists() or Path(thumbnail_path).stat().st_size == 0:
            raise RuntimeError("Thumbnail generation failed after retry")

    def _run_thumbnail_attempt(self, thumbnail_path: str, second: str) -> None:
        self._run_command(
            [
                "ffmpeg",
                "-y",
                "-nostdin",
                "-ss",
                second,
                "-i",
                self.source_path,
                "-frames:v",
                "1",
                "-vf",
                "scale=512:-2",
                "-q:v",
                "3",
                thumbnail_path,
            ]
        )

    MAX_ENCODE_ATTEMPTS = 3

    def _encode_with_retry(self, command: list[str], optimized_path: Path) -> tuple[int, int]:
        original_size = Path(self.source_path).stat().st_size
        current_crf = self.plan.crf
        attempts = 0

        while attempts < self.MAX_ENCODE_ATTEMPTS:
            attempt_command = self._replace_crf(command, current_crf)
            self._run_command(attempt_command)
            optimized_size = optimized_path.stat().st_size
            attempts += 1

            if optimized_size < original_size:
                return optimized_size, attempts

            max_crf = 51 if self.plan.codec == "libx264" else 63
            current_crf = min(current_crf + 6, max_crf)
            if current_crf == max_crf and attempts > 1:
                break

        return optimized_path.stat().st_size, attempts

    @staticmethod
    def _replace_crf(command: list[str], new_crf: int) -> list[str]:
        updated = command.copy()
        try:
            idx = updated.index("-crf")
            updated[idx + 1] = str(new_crf)
        except ValueError:
            pass
        return updated

    def _build_scale_filter(self, plan: VideoOptimizationPlan, analysis: dict) -> str:
        width = int(analysis.get("width") or 0)
        height = int(analysis.get("height") or 0)

        if width <= 0 or height <= 0:
            return f"scale={plan.max_width}:-2"

        if width <= plan.max_width and height <= plan.max_height:
            return "scale=trunc(iw/2)*2:trunc(ih/2)*2"

        return f"scale='min({plan.max_width},iw)':-2"

    @staticmethod
    def _parse_fps(value: str) -> float:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            try:
                return round(float(numerator) / float(denominator), 3)
            except ZeroDivisionError:
                return 0.0
            except ValueError:
                return 0.0

        try:
            return round(float(value), 3)
        except ValueError:
            return 0.0

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
            raise RuntimeError(completed.stderr.strip() or "Media command failed")
        return completed
