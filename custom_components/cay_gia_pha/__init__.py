"""Cây Gia Phả integration for Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, RUNTIME_SETUP_DONE

if TYPE_CHECKING:
    from .coordinator import FamilyTreeCoordinator
    from .storage import FamilyTreeStore


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

    from homeassistant.components import frontend
    from homeassistant.components.http import StaticPathConfig

    from .const import FRONTEND_MODULE_URL, FRONTEND_STATIC_URL
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
    frontend.add_extra_js_url(hass, FRONTEND_MODULE_URL)
    hass.http.register_view(FamilyTreeImageView())
    hass.http.register_view(FamilyTreeUploadPreviewView())
    async_register_websocket_commands(hass)
    domain_data[RUNTIME_SETUP_DONE] = True
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[FamilyTreeRuntimeData]
) -> bool:
    """Set up Cây Gia Phả from a config entry."""
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
