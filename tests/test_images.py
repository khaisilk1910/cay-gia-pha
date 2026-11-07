"""Security and atomic-write regression tests for portrait images."""

import pytest

from custom_components.cay_gia_pha.image_utils import _atomic_copy, _is_image_file


@pytest.mark.parametrize(
    ("extension", "header", "valid"),
    [
        (".jpg", b"\xff\xd8\xff\xe0", True),
        (".png", b"\x89PNG\r\n\x1a\n", True),
        (".gif", b"GIF89a", True),
        (".webp", b"RIFF\x12\x00\x00\x00WEBP", True),
        (".jpg", b"<html>bad data", False),
        (".gif", b"<script>", False),
        (".png", b"", False),
        (".bmp", b"BM", False),
    ],
)
def test_image_signature(tmp_path, extension, header, valid):
    file = tmp_path / ("upload" + extension)
    file.write_bytes(header)
    assert _is_image_file(file, extension) is valid


def test_atomic_copy_does_not_destroy_old_image_on_error(tmp_path):
    old = tmp_path / "portrait.jpg"
    old.write_bytes(b"old portrait")
    with pytest.raises(FileNotFoundError):
        _atomic_copy(tmp_path / "missing.jpg", old)
    assert old.read_bytes() == b"old portrait"
    new = tmp_path / "incoming.jpg"
    new.write_bytes(b"replacement")
    _atomic_copy(new, old)
    assert old.read_bytes() == b"replacement"
    assert not list(tmp_path.glob(".cgp-*"))
