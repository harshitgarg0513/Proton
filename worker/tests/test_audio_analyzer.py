from pathlib import Path

from worker.services.analyzers.audio_analyzer import AudioAnalyzer


def test_audio_analyzer_builds_default_metadata(tmp_path):
    source = tmp_path / "sample.mp3"
    source.write_bytes(b"not-a-real-audio-file")
    analyzer = AudioAnalyzer(str(source))
    metadata = analyzer.analyze()
    assert metadata["media_type"] == "audio"
    assert metadata["duration"] == 0.0
