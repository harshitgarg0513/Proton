from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter


@dataclass(frozen=True)
class BenchmarkResult:
    codec: str
    preset: str
    output_size: int
    elapsed_seconds: float


class VideoBenchmarkEngine:
    def __init__(self, source_path: str, output_dir: str) -> None:
        self.source_path = source_path
        self.output_dir = Path(output_dir)

    def benchmark(self) -> list[dict]:
        candidates = [
            {"codec": "libx264", "preset": "medium", "crf": "23", "extension": "mp4"},
            {"codec": "libx265", "preset": "medium", "crf": "28", "extension": "mp4"},
            {"codec": "libvpx-vp9", "preset": "good", "crf": "33", "extension": "webm", "vp9_mode": True},
        ]

        results: list[dict] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)

        for candidate in candidates:
            output_path = self.output_dir / f"benchmark_{candidate['codec']}.{candidate['extension']}"
            started_at = perf_counter()
            command = [
                "ffmpeg",
                "-y",
                "-i",
                self.source_path,
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
            ]
            if candidate.get("vp9_mode"):
                command += [
                    "-c:v",
                    candidate["codec"],
                    "-deadline",
                    candidate["preset"],
                    "-cpu-used",
                    "4",
                    "-crf",
                    candidate["crf"],
                    "-b:v",
                    "0",
                ]
            else:
                command += [
                    "-c:v",
                    candidate["codec"],
                    "-preset",
                    candidate["preset"],
                    "-crf",
                    candidate["crf"],
                ]
            command += [
                "-f",
                "webm" if candidate["extension"] == "webm" else candidate["extension"],
                str(output_path),
            ]
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            if completed.returncode != 0:
                continue
            results.append(
                {
                    "codec": candidate["codec"],
                    "preset": candidate["preset"],
                    "output_size": output_path.stat().st_size,
                    "elapsed_seconds": round(perf_counter() - started_at, 4),
                    "output_path": str(output_path),
                }
            )

        return sorted(results, key=lambda item: (item["output_size"], item["elapsed_seconds"]))
