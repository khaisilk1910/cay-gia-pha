"""Cây Gia Phả integration for Home Assistant."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import sqlite3
from time import monotonic
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryError, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    FRONTEND_MODULE_URL,
    PLATFORMS,
    RUNTIME_SETUP_DONE,
)

if TYPE_CHECKING:
    from .coordinator import FamilyTreeCoordinator
    from .storage import FamilyTreeStore

_LOGGER = logging.getLogger(__name__)


async def _async_register_lovelace_resource(
    hass: HomeAssistant, url: str, version: str
) -> None:
    """Install exactly one card module, without holding up entry setup.

    On dashboards with YAML-only resources, use the supported frontend module
    registry instead of trying to edit read-only YAML. Do not use the mutable
    resource API until it is fully loaded (HA 2026.11).
    """
    from homeassistant.components.frontend import add_extra_js_url

    versioned_url = f"{url}?v={version}"
    lovelace = hass.data.get("lovelace")
    resources = (
        getattr(lovelace, "resources", None) if lovelace is not None else None
    )
    if resources is None and isinstance(lovelace, dict):
        resources = lovelace.get("resources")
    if resources is None or not hasattr(resources, "async_items"):
        add_extra_js_url(hass, versioned_url)
        _LOGGER.debug("Lovelace resources unavailable; card registered as frontend module")
        return

    if hasattr(resources, "async_get_info"):
        await resources.async_get_info()
    elif hasattr(resources, "async_load") and not getattr(resources, "loaded", False):
        await resources.async_load()

    matches = [
        item for item in resources.async_items()
        if str(item.get("url", "")).split("?", 1)[0] == url
    ]
    # ResourceYAMLCollection is read-only; never call its non-existent writer.
    if not hasattr(resources, "async_create_item") or not hasattr(
        resources, "async_update_item"
    ):
        if not matches:
            add_extra_js_url(hass, versioned_url)
            _LOGGER.debug("Read-only Lovelace resources; using frontend module")
        elif all(item.get("url") != versioned_url for item in matches):
            _LOGGER.warning(
                "Cây Gia Phả card is configured via YAML with an older URL; "
                "update the dashboard resource to %s to refresh browser cache",
                versioned_url,
            )
        return

    # Preserve the first existing resource so users keep its identity.
    if matches:
        if matches[0].get("url") != versioned_url or matches[0].get("type") != "module":
            await resources.async_update_item(
                matches[0]["id"], {"res_type": "module", "url": versioned_url}
            )
        if len(matches) > 1:
            _LOGGER.warning(
                "Multiple Cây Gia Phả Lovelace resources found (%d); remove duplicates in dashboard resources",
                len(matches),
            )
    else:
        await resources.async_create_item({"res_type": "module", "url": versioned_url})
    _LOGGER.debug("Lovelace card resource ready: %s", versioned_url)


async def _async_setup_card_resource(hass: HomeAssistant) -> None:
    """Register frontend card as optional background work after core is ready."""
    try:
        integration = await async_get_integration(hass, DOMAIN)
        await _async_register_lovelace_resource(
            hass, FRONTEND_MODULE_URL, integration.version or "0"
        )
    except Exception:  # A card issue must never prevent backend integration setup.
        _LOGGER.exception(
            "Cannot automatically register Lovelace card; add %s as a module resource manually",
            FRONTEND_MODULE_URL,
        )


@dataclass(slots=True)
class FamilyTreeRuntimeData:
    """Runtime data for one family tree config entry."""

    store: FamilyTreeStore
    coordinator: FamilyTreeCoordinator
    update_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


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
    started_at = monotonic()

    from .coordinator import FamilyTreeCoordinator
    from .image_utils import async_delete_images
    from .storage import FamilyTreeStore

    store = FamilyTreeStore(hass)
    try:
        await store.async_initialize()
        removed_images = await store.async_sync_subentries(
            entry.subentries.values(), preserve_existing_if_empty=True
        )
        await async_delete_images(hass, removed_images)

        coordinator = FamilyTreeCoordinator(hass, store, entry)
        await coordinator.async_config_entry_first_refresh()
    except sqlite3.OperationalError as err:
        _LOGGER.warning("SQLite temporarily unavailable for tree %s: %s", entry.entry_id, err)
        raise ConfigEntryNotReady("Cây Gia Phả SQLite is temporarily unavailable") from err
    except (sqlite3.DatabaseError, OSError, ValueError) as err:
        _LOGGER.exception("Unable to initialize family tree database for %s", entry.entry_id)
        raise ConfigEntryError("Cây Gia Phả cannot read the family database; restore from backup if needed") from err

    entry.runtime_data = FamilyTreeRuntimeData(store=store, coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The card only enriches the UI: its registration must not hold up the
    # integration's state sensors, and any Lovelace failure is logged separately.
    entry.async_create_background_task(
        hass,
        _async_setup_card_resource(hass),
        f"{DOMAIN} Lovelace card resource",
    )
    _LOGGER.info(
        "Family tree ready: entry_id=%s people=%d revision=%s elapsed=%.3fs",
        entry.entry_id,
        len(coordinator.data.get("people", [])),
        coordinator.data.get("revision", 0),
        monotonic() - started_at,
    )
    return True


async def _async_entry_updated(
    hass: HomeAssistant, entry: ConfigEntry[FamilyTreeRuntimeData]
) -> None:
    """Synchronize subentry changes to SQLite without reloading Home Assistant."""
    from .image_utils import async_delete_images

    runtime = entry.runtime_data
    async with runtime.update_lock:
        try:
            removed_images = await runtime.store.async_sync_subentries(entry.subentries.values())
            # Preserve the data update even if a superseded image cannot be deleted.
            await runtime.coordinator.async_request_refresh()
        except (sqlite3.Error, OSError, ValueError):
            _LOGGER.exception("Failed to synchronize people for tree %s", entry.entry_id)
            raise
        await async_delete_images(hass, removed_images)
        _LOGGER.debug(
            "Family tree synchronized: entry_id=%s people=%d revision=%s",
            entry.entry_id,
            len(runtime.coordinator.data.get("people", [])),
            runtime.coordinator.data.get("revision", 0),
        )


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry[FamilyTreeRuntimeData]
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
