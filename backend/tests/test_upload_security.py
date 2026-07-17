import sys
from io import BytesIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.routes import _detect_file_type, _validate_upload_file


class DummyUpload:
    def __init__(self, filename: str, payload: bytes, content_type: str):
        self.filename = filename
        self.file = BytesIO(payload)
        self.content_type = content_type


@pytest.mark.parametrize(
    ("filename", "content_type", "payload", "expected"),
    [
        ("photo.jpg", "image/jpeg", b"\xff\xd8\xff", "image/jpeg"),
        ("photo.png", "image/png", b"\x89PNG\r\n\x1a\n", "image/png"),
        ("doc.pdf", "application/pdf", b"%PDF-1.4", "application/pdf"),
        ("video.mp4", "video/mp4", b"\x00\x00\x00f\x66\x74\x79\x70", "video/mp4"),
    ],
)
def test_detect_file_type_matches_known_magic_bytes(filename, content_type, payload, expected):
    upload = DummyUpload(filename=filename, payload=payload, content_type=content_type)
    assert _detect_file_type(upload) == expected


def test_validate_upload_file_rejects_unknown_type_and_large_files():
    large_upload = DummyUpload(filename="evil.exe", payload=b"MZ" + b"x" * 1024, content_type="application/x-msdownload")

    with pytest.raises(ValueError):
        _validate_upload_file(large_upload, max_size_bytes=10)
