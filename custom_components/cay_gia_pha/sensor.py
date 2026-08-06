"""Summary and per-person sensors for Cây Gia Phả."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FamilyTreeRuntimeData
from .const import (
    CONF_BIRTH_DAY,
    CONF_BIRTH_MONTH,
    CONF_BIRTH_ORDER,
    CONF_BIRTH_YEAR,
    CONF_DEATH_DAY,
    CONF_DEATH_MONTH,
    CONF_DEATH_YEAR,
    CONF_DETAILS,
    CONF_FATHER_ID,
    CONF_FULL_NAME,
    CONF_GENDER,
    CONF_IMAGE_PATH,
    CONF_IS_ADOPTED,
    CONF_IS_DECEASED,
    CONF_LEVEL,
    CONF_MOTHER_ID,
    CONF_PERSON_ID,
    CONF_SPOUSE_ORDER,
    DOMAIN,
    GENDER_FEMALE,
    GENDER_MALE,
    IMAGE_API_URL,
    SUBENTRY_TYPE_PERSON,
)
from .coordinator import FamilyTreeCoordinator
from .date_utils import calculate_age, date_components_from_mapping

GENDER_LABELS = {
    GENDER_MALE: "Nam",
    GENDER_FEMALE: "Nữ",
    "other": "Khác",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[FamilyTreeRuntimeData],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the summary sensor and one sensor for every person."""
    coordinator = entry.runtime_data.coordinator
    summary = FamilyTreeSummarySensor(entry, coordinator)
    person_entities: dict[str, FamilyTreePersonSensor] = {}

    @callback
    def async_sync_person_entities() -> None:
        """Add new person sensors, update existing ones, and remove deleted ones."""
        people = coordinator.data.get("people", []) if coordinator.data else []
        current_ids = {
            str(person.get(CONF_PERSON_ID))
            for person in people
            if person.get(CONF_PERSON_ID)
        }
        subentry_by_person_id = {
            str(
                subentry.data.get(CONF_PERSON_ID)
                or subentry.unique_id
                or subentry.subentry_id
            ): subentry.subentry_id
            for subentry in entry.subentries.values()
            if subentry.subentry_type == SUBENTRY_TYPE_PERSON
        }

        for person_id in current_ids - person_entities.keys():
            entity = FamilyTreePersonSensor(entry, coordinator, person_id)
            person_entities[person_id] = entity
            subentry_id = subentry_by_person_id.get(person_id)
            if subentry_id is not None:
                async_add_entities([entity], config_subentry_id=subentry_id)
            else:
                # Imported legacy rows might not yet have a matching subentry.
                async_add_entities([entity])

        for person_id in list(person_entities):
            entity = person_entities[person_id]
            if person_id not in current_ids:
                person_entities.pop(person_id, None)
                hass.async_create_task(entity.async_remove())
                continue

        # Existing CoordinatorEntity instances receive the same coordinator
        # update through their own listener. Writing them again here doubles
        # state serialization work on every family-tree change.

    @callback
    def async_refresh_ages(_now: datetime) -> None:
        """Refresh age states once a day without polling SQLite."""
        for entity in person_entities.values():
            if entity.hass is not None:
                entity.async_write_ha_state()

    async_add_entities([summary])
    async_sync_person_entities()
    entry.async_on_unload(coordinator.async_add_listener(async_sync_person_entities))
    entry.async_on_unload(
        async_track_time_change(
            hass,
            async_refresh_ages,
            hour=0,
            minute=5,
            second=0,
        )
    )


class FamilyTreeSummarySensor(CoordinatorEntity[FamilyTreeCoordinator], SensorEntity):
    """Expose family tree totals without polling."""

    _attr_has_entity_name = True
    _attr_translation_key = "summary"
    _attr_icon = "mdi:family-tree"

    def __init__(
        self,
        entry: ConfigEntry[FamilyTreeRuntimeData],
        coordinator: FamilyTreeCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_summary"
        self._attr_device_info = _tree_device_info(entry)

    @property
    def native_value(self) -> int:
        """Return total people as the sensor state."""
        return int(self.coordinator.data.get("stats", {}).get("total", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return aggregate counts used by dashboards and automations."""
        stats = dict(self.coordinator.data.get("stats", {}))
        return {
            "integration": DOMAIN,
            "entry_id": self._entry.entry_id,
            "revision": self.coordinator.data.get("revision", 0),
            "total_people": stats.get("total", 0),
            "male": stats.get("male", 0),
            "female": stats.get("female", 0),
            "other": stats.get("other", 0),
            "living": stats.get("living", 0),
            "deceased": stats.get("deceased", 0),
            "adopted": stats.get("adopted", 0),
            "levels": stats.get("levels", 0),
            "root_name": stats.get("root_name"),
        }


class FamilyTreePersonSensor(CoordinatorEntity[FamilyTreeCoordinator], SensorEntity):
    """Expose one person's age as state and all other data as attributes."""

    _attr_has_entity_name = False

    def __init__(
        self,
        entry: ConfigEntry[FamilyTreeRuntimeData],
        coordinator: FamilyTreeCoordinator,
        person_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._person_id = person_id
        self._attr_unique_id = f"{entry.entry_id}_person_{person_id}"
        self._signed_picture_url: str | None = None
        self._signed_picture_source: str | None = None
        self._signed_picture_refresh_at: datetime | None = None

    @property
    def name(self) -> str:
        """Return the person's full name."""
        person = self._person
        return str(person.get(CONF_FULL_NAME) if person else self._person_id)

    @property
    def icon(self) -> str:
        """Return an icon matching the person's status and gender."""
        person = self._person
        if person and person.get(CONF_IS_DECEASED):
            return "mdi:account-off-outline"
        if person and person.get(CONF_GENDER) == GENDER_FEMALE:
            return "mdi:face-woman-outline"
        if person and person.get(CONF_GENDER) == GENDER_MALE:
            return "mdi:face-man-outline"
        return "mdi:account-outline"

    @property
    def available(self) -> bool:
        """Return whether this person still exists in the coordinator snapshot."""
        return super().available and self._person is not None

    @property
    def native_value(self) -> str | None:
        """Return age text so the entity state is immediately useful."""
        person = self._person
        if person is None:
            return None
        age = _person_age(person)
        return f"{age} tuổi" if age is not None else "Không rõ"

    @property
    def entity_picture(self) -> str | None:
        """Return a signed portrait URL for the entity dialog."""
        person = self._person
        if (
            person is None
            or not person.get(CONF_IMAGE_PATH)
            or self.hass is None
        ):
            self._signed_picture_url = None
            self._signed_picture_source = None
            self._signed_picture_refresh_at = None
            return None
        source = (
            f"{person[CONF_IMAGE_PATH]}:"
            f"{self.coordinator.data.get('revision', 0)}"
        )
        now = datetime.now(UTC)
        if (
            self._signed_picture_url is not None
            and self._signed_picture_source == source
            and self._signed_picture_refresh_at is not None
            and now < self._signed_picture_refresh_at
        ):
            return self._signed_picture_url
        path = IMAGE_API_URL.format(
            entry_id=self._entry.entry_id,
            person_id=self._person_id,
        )
        self._signed_picture_url = async_sign_path(
            self.hass, path, timedelta(days=7)
        )
        self._signed_picture_source = source
        self._signed_picture_refresh_at = now + timedelta(days=6)
        return self._signed_picture_url

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all stored and resolved family information."""
        person = self._person
        if person is None:
            return {}

        father = self.coordinator.person(str(person.get(CONF_FATHER_ID) or ""))
        mother = self.coordinator.person(str(person.get(CONF_MOTHER_ID) or ""))
        spouse_ids = self.coordinator.spouse_ids(self._person_id)
        sibling_ids = self.coordinator.sibling_ids(self._person_id)
        age = _person_age(person)

        return {
            "integration": DOMAIN,
            "entry_id": self._entry.entry_id,
            "person_id": self._person_id,
            "full_name": person.get(CONF_FULL_NAME),
            "gender": person.get(CONF_GENDER),
            "gender_name": GENDER_LABELS.get(str(person.get(CONF_GENDER)), "Khác"),
            "status": "Đã mất" if person.get(CONF_IS_DECEASED) else "Còn sống",
            "is_deceased": bool(person.get(CONF_IS_DECEASED)),
            "age": age if age is not None else "Không rõ",
            "birth_date": _format_partial_date(person, birth=True) or "Không rõ",
            "birth_year": person.get(CONF_BIRTH_YEAR),
            "birth_month": person.get(CONF_BIRTH_MONTH),
            "birth_day": person.get(CONF_BIRTH_DAY),
            "death_date": (
                _format_partial_date(person, birth=False) or "Không rõ"
                if person.get(CONF_IS_DECEASED)
                else None
            ),
            "death_year": person.get(CONF_DEATH_YEAR),
            "death_month": person.get(CONF_DEATH_MONTH),
            "death_day": person.get(CONF_DEATH_DAY),
            "level": person.get(CONF_LEVEL),
            "birth_order": person.get(CONF_BIRTH_ORDER),
            "is_adopted": bool(person.get(CONF_IS_ADOPTED)),
            "father": father.get(CONF_FULL_NAME) if father else None,
            "father_id": person.get(CONF_FATHER_ID),
            "mother": mother.get(CONF_FULL_NAME) if mother else None,
            "mother_id": person.get(CONF_MOTHER_ID),
            "spouse": [
                spouse.get(CONF_FULL_NAME)
                for person_id in spouse_ids
                if (spouse := self.coordinator.person(person_id)) is not None
            ],
            "spouse_ids": list(spouse_ids),
            "spouse_order": person.get(CONF_SPOUSE_ORDER, 1),
            "siblings": [
                sibling.get(CONF_FULL_NAME)
                for person_id in sibling_ids
                if (sibling := self.coordinator.person(person_id)) is not None
            ],
            "sibling_ids": list(sibling_ids),
            "details": person.get(CONF_DETAILS),
            "revision": self.coordinator.data.get("revision", 0),
        }

    @property
    def _person(self) -> dict[str, Any] | None:
        """Return this person's current coordinator record."""
        return self.coordinator.person(self._person_id)


def _tree_device_info(entry: ConfigEntry[FamilyTreeRuntimeData]) -> DeviceInfo:
    """Return the shared family-tree device metadata."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Cây Gia Phả",
        model="Family Tree",
    )


def _person_age(person: dict[str, Any]) -> int | None:
    """Calculate a person's age from complete or incomplete dates."""
    try:
        return calculate_age(
            birth=date_components_from_mapping(person, birth=True),
            deceased=bool(person.get(CONF_IS_DECEASED)),
            death=date_components_from_mapping(person, birth=False),
        )
    except (TypeError, ValueError):
        return None


def _format_partial_date(person: dict[str, Any], *, birth: bool) -> str:
    """Format known date components without inventing missing information."""
    try:
        year, month, day = date_components_from_mapping(person, birth=birth)
    except (TypeError, ValueError):
        return ""
    if year is None and month is None and day is None:
        return ""
    if year is not None and month is not None and day is not None:
        return f"{day:02d}/{month:02d}/{year}"
    if year is not None and month is not None:
        return f"{month:02d}/{year}"
    if year is not None and day is not None:
        return f"Ngày {day:02d}, năm {year}"
    if year is not None:
        return str(year)
    if month is not None and day is not None:
        return f"{day:02d}/{month:02d}"
    if month is not None:
        return f"Tháng {month:02d}"
    return f"Ngày {day:02d}"


