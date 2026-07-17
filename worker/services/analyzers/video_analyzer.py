from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoAnalysisResult:
    duration: float
    bitrate: int
    fps: float
    codec: str
    motion_intensity: float
    scene_change_frequency: float
    scene_complexity: float
    media_type: str = "video"


class VideoAnalyzer:
    SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}

    def __init__(self, source_path: str) -> None:
        self.source_path = source_path

    def analyze(self) -> dict:
        probe = self._probe_media()
        format_info = probe.get("format", {})
        streams = probe.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})

        duration = float(format_info.get("duration") or 0.0)
        bitrate = int(format_info.get("bit_rate") or video_stream.get("bit_rate") or 0)
        fps = self._parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/1")
        codec = video_stream.get("codec_name") or "unknown"

        motion_intensity, scene_change_frequency, scene_complexity = self._sample_motion_metrics()

        result = VideoAnalysisResult(
            duration=duration,
            bitrate=bitrate,
            fps=fps,
            codec=codec,
            motion_intensity=motion_intensity,
            scene_change_frequency=scene_change_frequency,
            scene_complexity=scene_complexity,
        )

        return result.__dict__

    def _probe_media(self) -> dict:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                self.source_path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout or "{}")

    def _sample_motion_metrics(self, sample_count: int = 12) -> tuple[float, float, float]:
        capture = cv2.VideoCapture(self.source_path)
        if not capture.isOpened():
            return 0.0, 0.0, 0.0

        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if frame_count <= 1:
            capture.release()
            return 0.0, 0.0, 0.0

        indices = np.linspace(0, frame_count - 1, min(sample_count, frame_count), dtype=int)
        previous_gray = None
        motion_values = []
        scene_changes = 0
        complexity_scores = []

        for frame_index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
            success, frame = capture.read()
            if not success:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if previous_gray is not None:
                diff = cv2.absdiff(previous_gray, gray)
                motion_values.append(float(np.mean(diff) / 255.0))
                if float(np.mean(diff)) > 18.0:
                    scene_changes += 1

            laplacian = cv2.Laplacian(gray, cv2.CV_64F)
            complexity_scores.append(float(np.var(laplacian)))
            previous_gray = gray

        capture.release()

        if not motion_values:
            return 0.0, 0.0, float(np.mean(complexity_scores) if complexity_scores else 0.0)

        motion_intensity = float(min(max(np.mean(motion_values), 0.0), 1.0))
        scene_change_frequency = float(scene_changes / max(len(indices) - 1, 1))
        scene_complexity = float(np.mean(complexity_scores) if complexity_scores else 0.0)
        return motion_intensity, scene_change_frequency, scene_complexity

    @staticmethod
    def _parse_fps(value: str) -> float:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            try:
                return round(float(numerator) / float(denominator), 3)
            except (ZeroDivisionError, ValueError):
                return 0.0
        try:
            return round(float(value), 3)
        except ValueError:
            return 0.0
