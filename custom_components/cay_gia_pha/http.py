"""Authenticated image endpoints for Cây Gia Phả."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .const import IMAGE_API_URL, UPLOAD_PREVIEW_API_URL
from .image_utils import resolve_image_path


class FamilyTreeImageView(HomeAssistantView):
    """Serve a person's stored image through Home Assistant authentication."""

    url = IMAGE_API_URL
    name = "api:cay_gia_pha:image"
    requires_auth = True

    async def get(
        self,
        request: web.Request,
        entry_id: str,
        person_id: str,
    ) -> web.StreamResponse:
        """Return one stored image."""
        hass = request.app[KEY_HASS]
        entry = hass.config_entries.async_get_entry(entry_id)
        runtime = getattr(entry, "runtime_data", None) if entry is not None else None
        if runtime is None:
            raise web.HTTPNotFound

        person = runtime.coordinator.person(person_id)
        if person is None or not person.get("image_path"):
            raise web.HTTPNotFound

        path = await hass.async_add_executor_job(
            resolve_image_path, hass, str(person["image_path"])
        )
        if path is None:
            raise web.HTTPNotFound
        return web.FileResponse(path)


class FamilyTreeUploadPreviewView(HomeAssistantView):
    """Preview a temporary image selected by Home Assistant's file selector.

    The file selector keeps an uploaded file in Home Assistant's temporary upload
    store until the config flow consumes it. This endpoint only reads that file;
    the final save still validates and moves it into /config/cay_gia_pha/.
    """

    url = UPLOAD_PREVIEW_API_URL
    name = "api:cay_gia_pha:upload_preview"
    requires_auth = True

    async def get(
        self,
        request: web.Request,
        file_id: str,
    ) -> web.StreamResponse:
        """Return an uploaded image without consuming it."""
        hass = request.app[KEY_HASS]
        path = _uploaded_file_path(hass, file_id)
        if path is None or not path.is_file():
            raise web.HTTPNotFound
        return web.FileResponse(path)


def _uploaded_file_path(hass: Any, file_id: str) -> Path | None:
    """Resolve a temporary file-selector upload across supported HA versions."""
    try:
        from homeassistant.components import file_upload
    except ImportError:
        return None

    keys: list[Any] = []
    private_key = getattr(file_upload, "_DATA", None)
    if private_key is not None:
        keys.append(private_key)
    domain = getattr(file_upload, "DOMAIN", "file_upload")
    keys.append(domain)

    upload_data = next((hass.data.get(key) for key in keys if key in hass.data), None)
    if upload_data is None:
        return None

    try:
        has_file = getattr(upload_data, "has_file", None)
        if callable(has_file) and not has_file(file_id):
            return None
        file_path = getattr(upload_data, "file_path", None)
        if not callable(file_path):
            return None
        return Path(file_path(file_id))
    except (KeyError, OSError, TypeError, ValueError):
        return None
