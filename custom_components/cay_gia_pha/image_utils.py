"""Image upload and filesystem helpers for Cây Gia Phả."""

from __future__ import annotations

from pathlib import Path
import logging
import os
import re
import shutil
import tempfile
import unicodedata

from homeassistant.core import HomeAssistant

from .const import ALLOWED_IMAGE_EXTENSIONS, DATA_DIR_NAME, MAX_IMAGE_BYTES


_LOGGER = logging.getLogger(__name__)


class InvalidImageError(ValueError):
    """Raised when an uploaded image is invalid."""


async def async_store_uploaded_image(
    hass: HomeAssistant,
    file_id: str,
    full_name: str,
    level: int,
    person_id: str,
) -> str:
    """Consume a Home Assistant uploaded file and store it permanently."""
    return await hass.async_add_executor_job(
        _store_uploaded_image,
        hass,
        file_id,
        full_name,
        level,
        person_id,
    )


def _store_uploaded_image(
    hass: HomeAssistant,
    file_id: str,
    full_name: str,
    level: int,
    person_id: str,
) -> str:
    root = Path(hass.config.path(DATA_DIR_NAME))
    root.mkdir(parents=True, exist_ok=True)

    from homeassistant.components.file_upload import process_uploaded_file

    with process_uploaded_file(hass, file_id) as uploaded_path:
        extension = uploaded_path.suffix.lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise InvalidImageError("unsupported_image_type")
        if uploaded_path.stat().st_size > MAX_IMAGE_BYTES:
            raise InvalidImageError("image_too_large")
        if not _is_image_file(uploaded_path, extension):
            raise InvalidImageError("unsupported_image_type")

        folder = root / f"level_{max(1, int(level))}"
        folder.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{_slugify(full_name)}_level_{max(1, int(level))}_"
            f"{person_id[:8]}{extension}"
        )
        destination = folder / filename
        _atomic_copy(uploaded_path, destination)

    return destination.relative_to(root).as_posix()


async def async_relocate_image(
    hass: HomeAssistant,
    relative_path: str | None,
    full_name: str,
    level: int,
    person_id: str,
) -> str | None:
    """Copy a stored image to its new deterministic path before config commit."""
    if not relative_path:
        return None
    return await hass.async_add_executor_job(
        _relocate_image,
        hass,
        relative_path,
        full_name,
        level,
        person_id,
    )


def _relocate_image(
    hass: HomeAssistant,
    relative_path: str,
    full_name: str,
    level: int,
    person_id: str,
) -> str | None:
    root = Path(hass.config.path(DATA_DIR_NAME)).resolve()
    source = _safe_path(root, relative_path)
    if source is None or not source.is_file():
        return None

    folder = root / f"level_{max(1, int(level))}"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / (
        f"{_slugify(full_name)}_level_{max(1, int(level))}_"
        f"{person_id[:8]}{source.suffix.lower()}"
    )
    if destination.resolve() == source.resolve():
        return relative_path
    _atomic_copy(source, destination)
    return destination.relative_to(root).as_posix()


async def async_delete_images(
    hass: HomeAssistant, relative_paths: list[str]
) -> None:
    """Delete image files no longer referenced by a person."""
    if not relative_paths:
        return
    await hass.async_add_executor_job(_delete_images, hass, relative_paths)


def _delete_images(hass: HomeAssistant, relative_paths: list[str]) -> None:
    root = Path(hass.config.path(DATA_DIR_NAME)).resolve()
    failures = 0
    for relative_path in relative_paths:
        target = _safe_path(root, relative_path)
        if target is None:
            continue
        try:
            target.unlink(missing_ok=True)
            _remove_empty_parent(target.parent, root)
        except OSError:
            failures += 1
    if failures:
        _LOGGER.warning("Unable to remove %d orphaned family portraits", failures)


def resolve_image_path(hass: HomeAssistant, relative_path: str) -> Path | None:
    """Resolve and validate an image path under the persistent data directory."""
    root = Path(hass.config.path(DATA_DIR_NAME)).resolve()
    path = _safe_path(root, relative_path)
    if path is None or not path.is_file():
        return None
    return path


def _safe_path(root: Path, relative_path: str) -> Path | None:
    try:
        candidate = (root / relative_path).resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return None
    return candidate


def _remove_empty_parent(folder: Path, root: Path) -> None:
    if folder == root:
        return
    try:
        folder.rmdir()
    except OSError:
        pass


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return slug or "ca-the"


def _is_image_file(path: Path, extension: str) -> bool:
    """Verify file signature rather than trusting the upload extension."""
    with path.open("rb") as stream:
        header = stream.read(12)
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".gif":
        return header[:6] in (b"GIF87a", b"GIF89a")
    if extension == ".webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return False


def _atomic_copy(source: Path, destination: Path) -> None:
    """Write a new image before replacing an existing portrait."""
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=".cgp-", delete=False
        ) as target:
            temp_name = target.name
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, target)
        os.replace(temp_name, destination)
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
