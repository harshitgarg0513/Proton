import pytest

from worker.processors.video_processor import VideoProcessor
from worker.services.chunking.video_chunker import VideoChunker
from worker.services.strategy_engine import VideoOptimizationPlan


@pytest.mark.parametrize(
    "duration,expected_count,expected_length",
    [
        (10, 1, 10),
        (30, 1, 30),
        (45, 3, 15),
        (60, 4, 15),
        (90, 6, 15),
    ],
)
def test_video_chunker_plan(duration, expected_count, expected_length):
    chunker = VideoChunker(source_path="/tmp/source.mp4", output_dir="/tmp/output")
    plan = chunker.plan(duration)

    assert plan.chunk_count == expected_count
    assert plan.chunk_length_seconds == expected_length


@pytest.mark.parametrize(
    "profile,duration,expected",
    [
        ("smallest_size", 30, False),
        ("smallest_size", 61, True),
        ("web_optimized", 120, True),
        ("balanced", 300, False),
        ("best_quality", 300, False),
    ],
)
def test_should_chunk(profile, duration, expected):
    assert VideoProcessor.should_chunk(profile, duration) is expected


def test_plan_round_trip():
    plan = VideoOptimizationPlan(
        codec="libx264",
        preset="fast",
        crf=21,
        max_width=1280,
        max_height=720,
        audio_bitrate="128k",
        scale_label="web",
    )

    restored = VideoProcessor.plan_from_dict(VideoProcessor.plan_to_dict(plan))
    assert restored == plan


def test_merge_chunks_writes_concat_list_and_invokes_ffmpeg(monkeypatch, tmp_path):
    chunk_paths = []
    for index in range(2):
        chunk_path = tmp_path / f"chunk_{index}.mp4"
        chunk_path.write_bytes(b"chunk")
        chunk_paths.append(str(chunk_path))

    output_path = tmp_path / "merged.mp4"
    captured: dict[str, list[str]] = {}

    def fake_run_command(command: list[str]):
        captured["command"] = command
        output_path.write_bytes(b"merged")
        return None

    monkeypatch.setattr(VideoProcessor, "_run_command", staticmethod(fake_run_command))

    result = VideoProcessor.merge_chunks(chunk_paths, str(output_path))

    assert result == str(output_path)
    assert "-f" in captured["command"]
    assert "concat" in captured["command"]
    assert "-c" in captured["command"]
    assert "copy" in captured["command"]

    concat_list = tmp_path / "concat_list.txt"
    assert concat_list.exists()
    contents = concat_list.read_text(encoding="utf-8")
    assert "chunk_0.mp4" in contents
    assert "chunk_1.mp4" in contents
