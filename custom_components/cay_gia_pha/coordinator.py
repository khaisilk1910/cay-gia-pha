"""Data coordinator for Cây Gia Phả."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BIRTH_ORDER,
    CONF_BIRTH_YEAR,
    CONF_FATHER_ID,
    CONF_FULL_NAME,
    CONF_MOTHER_ID,
    CONF_PERSON_ID,
    CONF_SIBLING_IDS,
    CONF_SPOUSE_ID,
    CONF_SPOUSE_IDS,
    DOMAIN,
)
from .storage import FamilyTreeStore

_LOGGER = logging.getLogger(__name__)


class FamilyTreeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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
        self._people_by_id: dict[str, dict[str, Any]] = {}
        self._spouse_ids_by_person: dict[str, tuple[str, ...]] = {}
        self._sibling_ids_by_person: dict[str, tuple[str, ...]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Return the current family-tree snapshot."""
        snapshot = await self.store.async_snapshot()
        self._rebuild_relationship_indexes(snapshot.get("people", []))
        return snapshot

    def person(self, person_id: str) -> dict[str, Any] | None:
        """Return one person from the in-memory coordinator snapshot."""
        return self._people_by_id.get(str(person_id))

    def spouse_ids(self, person_id: str) -> tuple[str, ...]:
        """Return direct and reciprocal spouse IDs without rescanning all people."""
        return self._spouse_ids_by_person.get(str(person_id), ())

    def sibling_ids(self, person_id: str) -> tuple[str, ...]:
        """Return resolved sibling IDs without rescanning all people."""
        return self._sibling_ids_by_person.get(str(person_id), ())

    def _rebuild_relationship_indexes(
        self, people: list[dict[str, Any]]
    ) -> None:
        """Build fast person and relationship lookups once per refresh."""
        by_id = {
            str(person.get(CONF_PERSON_ID)): person
            for person in people
            if person.get(CONF_PERSON_ID)
        }
        spouse_lists: dict[str, list[str]] = {
            person_id: [] for person_id in by_id
        }
        sibling_sets: dict[str, set[str]] = {
            person_id: set() for person_id in by_id
        }

        for person_id, person in by_id.items():
            spouse_ids = _string_ids(person.get(CONF_SPOUSE_IDS))
            legacy_spouse_id = person.get(CONF_SPOUSE_ID)
            if legacy_spouse_id:
                spouse_ids.append(str(legacy_spouse_id))
            for spouse_id in spouse_ids:
                if spouse_id == person_id or spouse_id not in by_id:
                    continue
                if spouse_id not in spouse_lists[person_id]:
                    spouse_lists[person_id].append(spouse_id)
                if person_id not in spouse_lists[spouse_id]:
                    spouse_lists[spouse_id].append(person_id)

            for sibling_id in _string_ids(person.get(CONF_SIBLING_IDS)):
                if sibling_id == person_id or sibling_id not in by_id:
                    continue
                sibling_sets[person_id].add(sibling_id)
                sibling_sets[sibling_id].add(person_id)

        parent_groups: dict[tuple[str, str], list[str]] = {}
        for person_id, person in by_id.items():
            father_id = str(person.get(CONF_FATHER_ID) or "")
            mother_id = str(person.get(CONF_MOTHER_ID) or "")
            if not father_id and not mother_id:
                continue
            parent_groups.setdefault((father_id, mother_id), []).append(person_id)

        for group in parent_groups.values():
            if len(group) < 2:
                continue
            group_set = set(group)
            for person_id in group:
                sibling_sets[person_id].update(group_set - {person_id})

        def sibling_sort_key(person_id: str) -> tuple[int, int, str]:
            person = by_id[person_id]
            return (
                _safe_int(person.get(CONF_BIRTH_ORDER), 999),
                _safe_int(person.get(CONF_BIRTH_YEAR), 9999),
                str(person.get(CONF_FULL_NAME, "")).casefold(),
            )

        self._people_by_id = by_id
        self._spouse_ids_by_person = {
            person_id: tuple(spouse_ids)
            for person_id, spouse_ids in spouse_lists.items()
        }
        self._sibling_ids_by_person = {
            person_id: tuple(sorted(sibling_ids, key=sibling_sort_key))
            for person_id, sibling_ids in sibling_sets.items()
        }


def _string_ids(value: Any) -> list[str]:
    """Return unique string IDs from supported stored relationship values."""
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        return []

    result: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def _safe_int(value: Any, fallback: int) -> int:
    """Convert a stored value to int without making entity updates fail."""
    try:
        return int(value) if value is not None else fallback
    except (TypeError, ValueError):
        return fallback
