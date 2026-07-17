import tempfile
from pathlib import Path

from worker.services.fallback import keep_original_if_larger


def _write(path: Path, num_bytes: int) -> None:
    path.write_bytes(b"x" * num_bytes)


def test_keeps_optimized_when_smaller():
    with tempfile.TemporaryDirectory() as tmp:
        uploads = Path(tmp) / "uploads"
        outputs = Path(tmp) / "outputs"
        uploads.mkdir()
        outputs.mkdir()

        source = uploads / "clip.mp4"
        _write(source, 1000)
        optimized = outputs / "clip_opt.mp4"
        _write(optimized, 500)

        final_path, final_size, applied = keep_original_if_larger(str(source), str(optimized))

        assert applied is True
        assert final_size == 500
        assert final_path == str(optimized)


def test_falls_back_to_original_when_larger():
    with tempfile.TemporaryDirectory() as tmp:
        uploads = Path(tmp) / "uploads"
        outputs = Path(tmp) / "outputs"
        uploads.mkdir()
        outputs.mkdir()

        source = uploads / "clip.mp4"
        _write(source, 1000)
        optimized = outputs / "clip_opt.mp4"
        _write(optimized, 2000)

        final_path, final_size, applied = keep_original_if_larger(str(source), str(optimized))

        assert applied is False
        assert final_size == 1000
        assert Path(final_path).name == "clip.mp4"
        assert not optimized.exists()


def test_falls_back_when_sizes_equal():
    with tempfile.TemporaryDirectory() as tmp:
        uploads = Path(tmp) / "uploads"
        outputs = Path(tmp) / "outputs"
        uploads.mkdir()
        outputs.mkdir()

        source = uploads / "doc.pdf"
        _write(source, 1000)
        optimized = outputs / "doc_opt.pdf"
        _write(optimized, 1000)

        _, _, applied = keep_original_if_larger(str(source), str(optimized))
        assert applied is False
