from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VideoChunkPlan:
    chunk_count: int
    chunk_length_seconds: int
    chunk_directory: str


@dataclass(frozen=True)
class VideoChunkSplitResult:
    plan: VideoChunkPlan
    chunk_paths: tuple[str, ...]


class VideoChunker:
    DEFAULT_CHUNK_LENGTH_SECONDS = 15
    SINGLE_CHUNK_MAX_DURATION_SECONDS = 30

    def __init__(self, source_path: str, output_dir: str) -> None:
        self.source_path = source_path
        self.output_dir = Path(output_dir)

    def plan(self, duration_seconds: float) -> VideoChunkPlan:
        if duration_seconds <= self.SINGLE_CHUNK_MAX_DURATION_SECONDS:
            return VideoChunkPlan(
                chunk_count=1,
                chunk_length_seconds=max(int(duration_seconds), 1),
                chunk_directory=str(self.output_dir),
            )

        chunk_length = self.DEFAULT_CHUNK_LENGTH_SECONDS
        chunk_count = max(int(duration_seconds // chunk_length) + (1 if duration_seconds % chunk_length else 0), 1)
        return VideoChunkPlan(
            chunk_count=chunk_count,
            chunk_length_seconds=chunk_length,
            chunk_directory=str(self.output_dir / "chunks"),
        )

    def split(self, duration_seconds: float) -> VideoChunkSplitResult:
        plan = self.plan(duration_seconds)
        if plan.chunk_count <= 1:
            return VideoChunkSplitResult(plan=plan, chunk_paths=(self.source_path,))

        chunk_dir = Path(plan.chunk_directory)
        chunk_dir.mkdir(parents=True, exist_ok=True)

        for existing in chunk_dir.glob("chunk_*.mp4"):
            existing.unlink(missing_ok=True)

        segment_pattern = str(chunk_dir / "chunk_%03d.mp4")
        command = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-i",
            self.source_path,
            "-map",
            "0",
            "-f",
            "segment",
            "-segment_time",
            str(plan.chunk_length_seconds),
            "-reset_timestamps",
            "1",
            "-c",
            "copy",
            segment_pattern,
        ]
        self._run_command(command)

        chunk_paths = tuple(str(path) for path in sorted(chunk_dir.glob("chunk_*.mp4")))
        if not chunk_paths:
            raise RuntimeError("Video chunk split produced no output segments")

        return VideoChunkSplitResult(
            plan=VideoChunkPlan(
                chunk_count=len(chunk_paths),
                chunk_length_seconds=plan.chunk_length_seconds,
                chunk_directory=str(chunk_dir),
            ),
            chunk_paths=chunk_paths,
        )

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
            raise RuntimeError(completed.stderr.strip() or "Video chunk split failed")
        return completed
