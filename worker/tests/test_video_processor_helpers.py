import pytest

from worker.processors.video_processor import VideoProcessor
from worker.services.strategy_engine import VideoOptimizationPlan


@pytest.mark.parametrize(
    "value,expected",
    [
        ("30000/1001", 29.97),
        ("25/1", 25.0),
        ("25", 25.0),
        ("0/0", 0.0),
        ("not-a-number", 0.0),
    ],
)
def test_parse_fps(value, expected):
    assert VideoProcessor._parse_fps(value) == expected


def _make_processor(tmp_path):
    return VideoProcessor(source_path=str(tmp_path / "in.mp4"), profile="balanced", output_dir=str(tmp_path / "out"))


def test_scale_filter_passthrough_when_already_within_bounds(tmp_path):
    processor = _make_processor(tmp_path)
    plan = VideoOptimizationPlan(
        codec="libx264",
        preset="medium",
        crf=23,
        max_width=1920,
        max_height=1080,
        audio_bitrate="128k",
        scale_label="balanced",
    )
    analysis = {"width": 1280, "height": 720}
    result = processor._build_scale_filter(plan, analysis)
    assert "trunc" in result


def test_scale_filter_downscales_when_larger_than_plan(tmp_path):
    processor = _make_processor(tmp_path)
    plan = VideoOptimizationPlan(
        codec="libx264",
        preset="medium",
        crf=23,
        max_width=1280,
        max_height=720,
        audio_bitrate="128k",
        scale_label="aggressive",
    )
    analysis = {"width": 3840, "height": 2160}
    result = processor._build_scale_filter(plan, analysis)
    assert "1280" in result


def test_replace_crf_updates_existing_flag(tmp_path):
    processor = _make_processor(tmp_path)
    command = ["ffmpeg", "-y", "-i", "in.mp4", "-crf", "23", "out.mp4"]
    updated = processor._replace_crf(command, 29)
    assert updated[updated.index("-crf") + 1] == "29"
    assert command[command.index("-crf") + 1] == "23"
