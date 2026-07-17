from __future__ import annotations

import json
import subprocess
from pathlib import Path


class VideoQualityMetric:
    def __init__(self, original_path: str, optimized_path: str) -> None:
        self.original_path = original_path
        self.optimized_path = optimized_path

    def compute(self) -> dict:
        vmaf_score = self._compute_vmaf()
        return {"vmaf": vmaf_score}

    def _compute_vmaf(self) -> float | None:
        log_path = Path(self.optimized_path).with_suffix(".vmaf.json")
        command = [
            "ffmpeg",
            "-y",
            "-i",
            self.original_path,
            "-i",
            self.optimized_path,
            "-lavfi",
            f"libvmaf=log_fmt=json:log_path={log_path}",
            "-f",
            "null",
            "-",
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0 or not log_path.exists():
            return None

        try:
            payload = json.loads(log_path.read_text())
            frames = payload.get("frames", [])
            scores = [float(frame.get("metrics", {}).get("vmaf", 0.0)) for frame in frames if frame.get("metrics")]
            if not scores:
                return None
            return round(sum(scores) / len(scores), 4)
        finally:
            try:
                log_path.unlink(missing_ok=True)
            except OSError:
                pass
