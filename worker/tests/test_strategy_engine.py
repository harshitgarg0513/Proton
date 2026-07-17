import pytest

from worker.services.strategy_engine import (
    OptimizationStrategy,
    crf_for_codec,
    ffmpeg_codec_for,
    resolve_video_plan,
)


@pytest.mark.parametrize(
    "codec,base_crf,expected",
    [
        ("libx264", 23, 23),
        ("libx265", 23, 29),
        ("libx265", 50, 51),
        ("libvpx-vp9", 23, 32),
        ("libvpx-vp9", 50, 63),
    ],
)
def test_crf_for_codec(codec, base_crf, expected):
    assert crf_for_codec(codec, base_crf) == expected


def test_ffmpeg_codec_for_maps_known_names():
    assert ffmpeg_codec_for("H264") == "libx264"
    assert ffmpeg_codec_for("H265") == "libx265"
    assert ffmpeg_codec_for("AV1") == "libaom-av1"


def test_ffmpeg_codec_for_passes_through_unknown():
    assert ffmpeg_codec_for("mystery") == "mystery"


def test_smallest_size_profile_prefers_smaller_resolution():
    analysis = {"media_type": "video", "width": 3840, "height": 2160, "bitrate": 5_000_000, "duration": 60}
    plan = resolve_video_plan("smallest_size", analysis)
    assert plan.max_width <= 1280
    assert plan.crf >= 26


def test_best_quality_profile_keeps_higher_resolution_ceiling():
    analysis = {"media_type": "video", "width": 1920, "height": 1080, "bitrate": 5_000_000, "duration": 60}
    plan = resolve_video_plan("best_quality", analysis)
    assert plan.max_width >= 1920
    assert plan.crf <= 18


def test_high_motion_video_favors_h264():
    analysis = {"media_type": "video", "motion_intensity": 0.5, "duration": 60, "bitrate": 4_000_000}
    codec = OptimizationStrategy(analysis, "balanced").select_codec()
    assert codec == "H264"
