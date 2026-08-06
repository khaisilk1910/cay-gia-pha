"""Data coordinator for Cây Gia Phả."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .storage import FamilyTreeStore

_LOGGER = logging.getLogger(__name__)


class FamilyTreeCoordinator(DataUpdateCoordinator[dict]):
    """Load a local SQLite snapshot only when configuration changes."""

    def __init__(
        self,
        hass: HomeAssistant,
        store: FamilyTreeStore,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            config_entry=entry,
            update_interval=None,
        )
        self.store = store

    async def _async_update_data(self) -> dict:
        """Return the current family-tree snapshot."""
        return await self.store.async_snapshot()
