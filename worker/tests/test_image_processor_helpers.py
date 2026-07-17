from pathlib import Path

from worker.processors.image_processor import ImageProcessor


def test_build_output_path_uses_source_stem(tmp_path):
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"fake")
    processor = ImageProcessor(source_path=str(source), profile="balanced", output_dir=str(tmp_path / "out"))
    output_path = processor._build_output_path(".webp")
    assert output_path.endswith("photo.webp")


def test_derive_format_prefers_given_extension(tmp_path):
    source = tmp_path / "photo.png"
    source.write_bytes(b"fake")
    processor = ImageProcessor(source_path=str(source), profile="balanced", output_dir=str(tmp_path / "out"))
    assert processor._derive_format("jpeg") == ".jpg"
    assert processor._derive_format("webp") == ".webp"
