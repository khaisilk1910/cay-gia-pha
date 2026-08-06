"""Cây Gia Phả integration for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    FRONTEND_CARD_FILENAME,
    FRONTEND_MODULE_URL,
    PLATFORMS,
    RUNTIME_SETUP_DONE,
)

if TYPE_CHECKING:
    from .coordinator import FamilyTreeCoordinator
    from .storage import FamilyTreeStore


async def _async_register_lovelace_resource(
    hass: HomeAssistant, url: str, version: str
) -> bool:
    """Register or update one Lovelace module with deterministic cache busting.

    This follows the same strategy used by Shopping History: prefer Lovelace's
    resource storage, update an existing URL in place, and only fall back to
    ``add_extra_js_url`` when resource storage is unavailable. Registering by one
    route avoids loading the same custom element twice.
    """
    from homeassistant.components.frontend import add_extra_js_url

    versioned_url = f"{url}?v={version}"
    lovelace = hass.data.get("lovelace")
    if not lovelace:
        add_extra_js_url(hass, versioned_url)
        return False

    resources = getattr(lovelace, "resources", None)
    if resources is None and hasattr(lovelace, "get"):
        resources = lovelace.get("resources")

    if not resources or not hasattr(resources, "async_items"):
        add_extra_js_url(hass, versioned_url)
        return False

    if hasattr(resources, "async_get_info"):
        await resources.async_get_info()
    elif hasattr(resources, "async_load") and not getattr(resources, "loaded", True):
        await resources.async_load()

    for item in resources.async_items():
        item_url = item.get("url", "")
        if item_url.split("?", 1)[0] != url:
            continue
        if item_url != versioned_url:
            await resources.async_update_item(
                item["id"], {"res_type": "module", "url": versioned_url}
            )
        return True

    await resources.async_create_item(
        {"res_type": "module", "url": versioned_url}
    )
    return True


def _frontend_file_version(file_path: str, fallback: str) -> str:
    """Build a cache key from integration version and actual JS file content."""
    try:
        stat = os.stat(file_path)
        with open(file_path, "rb") as file_obj:
            digest = hashlib.sha256(file_obj.read()).hexdigest()[:12]
        return f"{fallback}-{int(stat.st_mtime)}-{stat.st_size}-{digest}"
    except OSError:
        return fallback


@dataclass(slots=True)
class FamilyTreeRuntimeData:
    """Runtime data for one family tree config entry."""

    store: FamilyTreeStore
    coordinator: FamilyTreeCoordinator


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up shared HTTP, WebSocket, and frontend resources.

    Imports are deliberately kept inside this function. Home Assistant imports the
    package before importing config_flow.py; eager imports here could therefore make
    the config flow appear as an "Invalid handler" when an optional frontend API
    changes or is unavailable.
    """
    from pathlib import Path

    from homeassistant.components.http import StaticPathConfig

    from .const import FRONTEND_STATIC_URL
    from .http import FamilyTreeImageView, FamilyTreeUploadPreviewView
    from .websocket_api import async_register_websocket_commands

    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(RUNTIME_SETUP_DONE):
        return True

    frontend_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_STATIC_URL,
                str(frontend_dir),
                cache_headers=True,
            )
        ]
    )
    hass.http.register_view(FamilyTreeImageView())
    hass.http.register_view(FamilyTreeUploadPreviewView())
    async_register_websocket_commands(hass)
    domain_data[RUNTIME_SETUP_DONE] = True
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[FamilyTreeRuntimeData]
) -> bool:
    """Set up Cây Gia Phả from a config entry."""
    integration = await async_get_integration(hass, DOMAIN)
    fallback_version = integration.version if integration.version else "0"
    frontend_file = hass.config.path(
        "custom_components", DOMAIN, "frontend", FRONTEND_CARD_FILENAME
    )
    frontend_version = await hass.async_add_executor_job(
        _frontend_file_version, frontend_file, fallback_version
    )
    await _async_register_lovelace_resource(
        hass, FRONTEND_MODULE_URL, frontend_version
    )

    from .coordinator import FamilyTreeCoordinator
    from .image_utils import async_delete_images
    from .storage import FamilyTreeStore

    store = FamilyTreeStore(hass)
    await store.async_initialize()
    removed_images = await store.async_sync_subentries(entry.subentries.values())
    await async_delete_images(hass, removed_images)

    coordinator = FamilyTreeCoordinator(hass, store, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = FamilyTreeRuntimeData(store=store, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_entry_updated(
    hass: HomeAssistant, entry: ConfigEntry[FamilyTreeRuntimeData]
) -> None:
    """Synchronize subentry changes to SQLite without reloading Home Assistant."""
    from .image_utils import async_delete_images

    runtime = entry.runtime_data
    removed_images = await runtime.store.async_sync_subentries(entry.subentries.values())
    await async_delete_images(hass, removed_images)
    await runtime.coordinator.async_request_refresh()


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry[FamilyTreeRuntimeData]
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
