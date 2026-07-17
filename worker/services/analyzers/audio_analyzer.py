from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioAnalysisResult:
    duration: float
    bitrate: int
    sample_rate: int
    channels: int
    codec: str
    media_type: str = "audio"


class AudioAnalyzer:
    def __init__(self, source_path: str) -> None:
        self.source_path = source_path

    def analyze(self) -> dict:
        probe = self._probe_media()
        format_info = probe.get("format", {})
        streams = probe.get("streams", [])
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})

        result = AudioAnalysisResult(
            duration=float(format_info.get("duration") or 0.0),
            bitrate=int(format_info.get("bit_rate") or audio_stream.get("bit_rate") or 0),
            sample_rate=int(audio_stream.get("sample_rate") or 0),
            channels=int(audio_stream.get("channels") or 0),
            codec=audio_stream.get("codec_name") or "unknown",
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
