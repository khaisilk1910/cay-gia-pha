"""Config flow for Cây Gia Phả."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import callback
from homeassistant.helpers import selector

try:
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:  # Home Assistant versions before ConfigFlowResult was exported.
    ConfigFlowResult = dict  # type: ignore[misc, assignment]

try:
    from homeassistant.config_entries import ConfigSubentryFlow
except ImportError:  # Config subentries require Home Assistant 2025.3 or newer.
    _SUBENTRIES_SUPPORTED = False

    class ConfigSubentryFlow:  # type: ignore[no-redef]
        """Import-safe placeholder; never registered on unsupported versions."""

else:
    _SUBENTRIES_SUPPORTED = True

from .const import (
    CONF_BIRTH_DATE,
    CONF_BIRTH_DAY,
    CONF_BIRTH_MONTH,
    CONF_BIRTH_ORDER,
    CONF_BIRTH_YEAR,
    CONF_CREATED_AT,
    CONF_DEATH_DATE,
    CONF_DEATH_DAY,
    CONF_DEATH_MONTH,
    CONF_DEATH_YEAR,
    CONF_DETAILS,
    CONF_FATHER_ID,
    CONF_FULL_NAME,
    CONF_GENDER,
    CONF_IMAGE_PATH,
    CONF_IMAGE_UPLOAD,
    CONF_IS_ADOPTED,
    CONF_IS_DECEASED,
    CONF_LEVEL,
    CONF_MOTHER_ID,
    CONF_PERSON_ID,
    CONF_RELATED_PERSON_ID,
    CONF_RELATIONSHIP,
    CONF_SIBLING_IDS,
    CONF_SORT_ORDER,
    CONF_SPOUSE_ID,
    CONF_SPOUSE_IDS,
    CONF_SPOUSE_ORDER,
    CONF_TREE_NAME,
    CONF_UPDATED_AT,
    DOMAIN,
    FRONTEND_STATIC_URL,
    IMAGE_API_URL,
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_OTHER,
    GENDERS,
    RELATION_ADOPTED_CHILD,
    RELATION_CHILD,
    RELATION_PARENT,
    RELATION_SIBLING,
    RELATION_SPOUSE,
    SUBENTRY_TYPE_PERSON,
    UPLOAD_PREVIEW_API_URL,
)
from .date_utils import (
    PartialDateError,
    birth_definitely_after_death,
    is_future_partial_date,
    normalize_partial_date,
    partial_date_to_string,
)
_PERSON_DATA_KEYS = {
    CONF_PERSON_ID,
    CONF_FULL_NAME,
    CONF_GENDER,
    CONF_BIRTH_DATE,
    CONF_BIRTH_YEAR,
    CONF_BIRTH_MONTH,
    CONF_BIRTH_DAY,
    CONF_DEATH_DATE,
    CONF_DEATH_YEAR,
    CONF_DEATH_MONTH,
    CONF_DEATH_DAY,
    CONF_IS_DECEASED,
    CONF_LEVEL,
    CONF_FATHER_ID,
    CONF_MOTHER_ID,
    CONF_SPOUSE_ID,
    CONF_SPOUSE_IDS,
    CONF_SPOUSE_ORDER,
    CONF_SIBLING_IDS,
    CONF_BIRTH_ORDER,
    CONF_IS_ADOPTED,
    CONF_RELATED_PERSON_ID,
    CONF_RELATIONSHIP,
    CONF_DETAILS,
    CONF_IMAGE_PATH,
    CONF_SORT_ORDER,
    CONF_CREATED_AT,
    CONF_UPDATED_AT,
}


class CayGiaPhaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the main Cây Gia Phả config flow."""

    VERSION = 1
    MINOR_VERSION = 5

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the tree and, for a new database, its root person."""
        if not _SUBENTRIES_SUPPORTED:
            return self.async_abort(reason="unsupported_home_assistant_version")

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        from .storage import FamilyTreeStore

        existing_people = await FamilyTreeStore.async_load_existing_people(self.hass)
        errors: dict[str, str] = {}
        root_prepared: dict[str, Any] | None = None

        if user_input is not None:
            tree_name = str(user_input.get(CONF_TREE_NAME, "")).strip()
            if not tree_name:
                errors[CONF_TREE_NAME] = "required"

            subentries = [_person_subentry_data(person) for person in existing_people]
            if not existing_people:
                person_id = uuid4().hex
                root_prepared = await _async_prepare_person_data(
                    self.hass,
                    user_input,
                    [],
                    person_id=person_id,
                    is_first_person=True,
                    is_root_person=True,
                    current_person=None,
                    errors=errors,
                )
                if root_prepared is not None:
                    subentries = [_person_subentry_data(root_prepared)]

            if not errors and (existing_people or root_prepared is not None):
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=tree_name,
                    data={CONF_TREE_NAME: tree_name},
                    subentries=subentries,
                )

        schema = _initial_config_schema(include_root=not existing_people)
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "existing_count": str(len(existing_people)),
                "setup_mode": "restore" if existing_people else "new",
            },
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported config subentry types."""
        if not _SUBENTRIES_SUPPORTED:
            return {}
        return {SUBENTRY_TYPE_PERSON: PersonSubentryFlow}


class PersonSubentryFlow(ConfigSubentryFlow):
    """Add and edit one person as a Home Assistant config subentry."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect personal information before family relationships."""
        entry = self._get_entry()
        people = _people_from_entry(entry)
        is_first_person = not people
        errors: dict[str, str] = {}
        values = getattr(self, "_pending_core", None) or {}

        if user_input is not None:
            prepared_core = _validate_person_core(user_input, errors)
            if prepared_core is not None:
                self._pending_core = prepared_core
                self._pending_people = people
                self._pending_person_id = uuid4().hex
                self._pending_current = None
                self._pending_relations = {}
                self._pending_is_first_person = is_first_person
                self._pending_is_root_person = is_first_person
                return await self.async_step_relationships()
            values = user_input

        return self.async_show_form(
            step_id="user",
            data_schema=_person_core_schema(values),
            errors=errors,
            description_placeholders=_preview_placeholders(
                self.hass,
                uploaded_file_id=_optional_string(values.get(CONF_IMAGE_UPLOAD)),
                entry_id=None,
                person_id=None,
                has_existing_image=False,
                gender=str(values.get(CONF_GENDER, GENDER_OTHER)),
            ),
        )

    async def async_step_relationships(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect family links using the gender selected in the first step."""
        if not hasattr(self, "_pending_core"):
            return await self.async_step_user()

        core = self._pending_core
        people = self._pending_people
        person_id = self._pending_person_id
        is_first_person = self._pending_is_first_person
        errors: dict[str, str] = {}
        relation_values = getattr(self, "_pending_relations", None) or {}

        if user_input is not None:
            self._pending_relations = dict(user_input)
            combined = {**core, **user_input}
            prepared = await self._async_prepare_person_data(
                combined,
                people,
                person_id=person_id,
                is_first_person=is_first_person,
                is_root_person=is_first_person,
                current_person=None,
                errors=errors,
            )
            if prepared is not None:
                return self.async_create_entry(
                    title=prepared[CONF_FULL_NAME],
                    unique_id=person_id,
                    data=prepared,
                )
            relation_values = user_input
            if CONF_IMAGE_UPLOAD in errors:
                core.pop(CONF_IMAGE_UPLOAD, None)
                return self.async_show_form(
                    step_id="user",
                    data_schema=_person_core_schema(core),
                    errors={CONF_IMAGE_UPLOAD: errors[CONF_IMAGE_UPLOAD]},
                )

        return self.async_show_form(
            step_id="relationships",
            data_schema=_person_relationship_schema(
                people,
                current=relation_values,
                gender=str(core.get(CONF_GENDER, GENDER_OTHER)),
                is_first_person=is_first_person,
            ),
            errors=errors,
            description_placeholders=_preview_placeholders(
                self.hass,
                uploaded_file_id=_optional_string(core.get(CONF_IMAGE_UPLOAD)),
                entry_id=None,
                person_id=None,
                has_existing_image=False,
                gender=str(core.get(CONF_GENDER, GENDER_OTHER)),
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect editable personal information for an existing person."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        person_id = str(subentry.data.get(CONF_PERSON_ID) or subentry.unique_id)
        all_people = _people_from_entry(entry)
        current = next(
            (
                person
                for person in all_people
                if str(person[CONF_PERSON_ID]) == person_id
            ),
            _normalize_person(dict(subentry.data), all_people),
        )
        people = [
            person
            for person in all_people
            if str(person[CONF_PERSON_ID]) != person_id
        ]
        is_root_person = (
            int(current.get(CONF_LEVEL, 1)) == 1
            and not _has_structured_link(current)
            and not current.get(CONF_RELATED_PERSON_ID)
        )
        errors: dict[str, str] = {}
        values = getattr(self, "_pending_core", None) or current

        if user_input is not None:
            prepared_core = _validate_person_core(user_input, errors)
            if prepared_core is not None:
                self._pending_core = prepared_core
                self._pending_people = people
                self._pending_person_id = person_id
                self._pending_current = current
                self._pending_entry = entry
                self._pending_subentry = subentry
                self._pending_is_first_person = False
                self._pending_is_root_person = is_root_person
                self._pending_relations = {}
                return await self.async_step_reconfigure_relationships()
            values = user_input

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_person_core_schema(values),
            errors=errors,
            description_placeholders=_preview_placeholders(
                self.hass,
                uploaded_file_id=_optional_string(values.get(CONF_IMAGE_UPLOAD)),
                entry_id=entry.entry_id,
                person_id=person_id,
                has_existing_image=bool(current.get(CONF_IMAGE_PATH)),
                gender=str(values.get(CONF_GENDER, GENDER_OTHER)),
            ),
        )

    async def async_step_reconfigure_relationships(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update family links after gender-specific spouse filtering."""
        if not hasattr(self, "_pending_current"):
            return await self.async_step_reconfigure()

        core = self._pending_core
        people = self._pending_people
        person_id = self._pending_person_id
        current = self._pending_current
        entry = self._pending_entry
        subentry = self._pending_subentry
        errors: dict[str, str] = {}
        relation_values = getattr(self, "_pending_relations", None) or current

        if user_input is not None:
            self._pending_relations = dict(user_input)
            combined = {**core, **user_input}
            prepared = await self._async_prepare_person_data(
                combined,
                people,
                person_id=person_id,
                is_first_person=False,
                is_root_person=self._pending_is_root_person,
                current_person=current,
                errors=errors,
            )
            if prepared is not None:
                return self.async_update_and_abort(
                    entry,
                    subentry,
                    title=prepared[CONF_FULL_NAME],
                    unique_id=person_id,
                    data=prepared,
                )
            relation_values = user_input
            if CONF_IMAGE_UPLOAD in errors:
                core.pop(CONF_IMAGE_UPLOAD, None)
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=_person_core_schema(core),
                    errors={CONF_IMAGE_UPLOAD: errors[CONF_IMAGE_UPLOAD]},
                    description_placeholders=_preview_placeholders(
                        self.hass,
                        uploaded_file_id=None,
                        entry_id=entry.entry_id,
                        person_id=person_id,
                        has_existing_image=bool(current.get(CONF_IMAGE_PATH)),
                        gender=str(core.get(CONF_GENDER, GENDER_OTHER)),
                    ),
                )

        return self.async_show_form(
            step_id="reconfigure_relationships",
            data_schema=_person_relationship_schema(
                people,
                current=relation_values,
                gender=str(core.get(CONF_GENDER, GENDER_OTHER)),
                is_first_person=False,
            ),
            errors=errors,
            description_placeholders=_preview_placeholders(
                self.hass,
                uploaded_file_id=_optional_string(core.get(CONF_IMAGE_UPLOAD)),
                entry_id=entry.entry_id,
                person_id=person_id,
                has_existing_image=bool(current.get(CONF_IMAGE_PATH)),
                gender=str(core.get(CONF_GENDER, GENDER_OTHER)),
            ),
        )

    async def _async_prepare_person_data(
        self,
        user_input: dict[str, Any],
        people: list[dict[str, Any]],
        *,
        person_id: str,
        is_first_person: bool,
        is_root_person: bool,
        current_person: dict[str, Any] | None,
        errors: dict[str, str],
    ) -> dict[str, Any] | None:
        """Prepare a person using the shared validator."""
        return await _async_prepare_person_data(
            self.hass,
            user_input,
            people,
            person_id=person_id,
            is_first_person=is_first_person,
            is_root_person=is_root_person,
            current_person=current_person,
            errors=errors,
        )

async def _async_prepare_person_data(
    hass: Any,
    user_input: dict[str, Any],
    people: list[dict[str, Any]],
    *,
    person_id: str,
    is_first_person: bool,
    is_root_person: bool,
    current_person: dict[str, Any] | None,
    errors: dict[str, str],
) -> dict[str, Any] | None:
    """Validate family links, calculate level, and process an image."""
    from .image_utils import (
        InvalidImageError,
        async_relocate_image,
        async_store_uploaded_image,
    )

    full_name = str(user_input.get(CONF_FULL_NAME, "")).strip()
    if not full_name:
        errors[CONF_FULL_NAME] = "required"

    gender = str(user_input.get(CONF_GENDER, GENDER_OTHER))
    if gender not in GENDERS:
        errors[CONF_GENDER] = "required"

    try:
        birth_parts = normalize_partial_date(
            user_input.get(CONF_BIRTH_YEAR),
            user_input.get(CONF_BIRTH_MONTH),
            user_input.get(CONF_BIRTH_DAY),
            fallback=user_input.get(CONF_BIRTH_DATE),
        )
    except PartialDateError:
        birth_parts = (None, None, None)
        errors[CONF_BIRTH_DAY] = "invalid_partial_date"

    is_deceased = bool(user_input.get(CONF_IS_DECEASED, False))
    try:
        death_parts = normalize_partial_date(
            user_input.get(CONF_DEATH_YEAR),
            user_input.get(CONF_DEATH_MONTH),
            user_input.get(CONF_DEATH_DAY),
            fallback=user_input.get(CONF_DEATH_DATE),
        )
    except PartialDateError:
        death_parts = (None, None, None)
        errors[CONF_DEATH_DAY] = "invalid_partial_date"

    if not is_deceased:
        death_parts = (None, None, None)
    if is_future_partial_date(birth_parts):
        errors[CONF_BIRTH_YEAR] = "date_in_future"
    if is_deceased and is_future_partial_date(death_parts):
        errors[CONF_DEATH_YEAR] = "date_in_future"
    if is_deceased and birth_definitely_after_death(birth_parts, death_parts):
        errors[CONF_DEATH_YEAR] = "death_before_birth"

    birth_year, birth_month, birth_day = birth_parts
    death_year, death_month, death_day = death_parts
    birth_date = partial_date_to_string(*birth_parts)
    death_date = partial_date_to_string(*death_parts)

    people_by_id = {
        str(person[CONF_PERSON_ID]): person for person in people
    }
    father_choices = _string_list(user_input.get(CONF_FATHER_ID))
    mother_choices = _string_list(user_input.get(CONF_MOTHER_ID))
    father_id = father_choices[0] if father_choices else None
    mother_id = mother_choices[0] if mother_choices else None
    spouse_ids = _string_list(user_input.get(CONF_SPOUSE_IDS))
    legacy_spouse_choices = _string_list(user_input.get(CONF_SPOUSE_ID))
    legacy_spouse_id = legacy_spouse_choices[0] if legacy_spouse_choices else None
    if gender == GENDER_FEMALE:
        spouse_ids = [legacy_spouse_id] if legacy_spouse_id else spouse_ids[:1]
    elif legacy_spouse_id and legacy_spouse_id not in spouse_ids:
        spouse_ids.insert(0, legacy_spouse_id)
    spouse_id = spouse_ids[0] if spouse_ids else None
    spouse_order = max(1, int(user_input.get(CONF_SPOUSE_ORDER, 1) or 1))
    sibling_ids = _string_list(user_input.get(CONF_SIBLING_IDS))
    is_adopted = bool(user_input.get(CONF_IS_ADOPTED, False))
    birth_order = max(1, int(user_input.get(CONF_BIRTH_ORDER, 1) or 1))

    if is_first_person:
        father_id = None
        mother_id = None
        spouse_ids = []
        spouse_id = None
        spouse_order = 1
        sibling_ids = []
        is_adopted = False
        birth_order = 1

    selected_ids = [
        value
        for value in (father_id, mother_id, *spouse_ids, *sibling_ids)
        if value
    ]
    for selected_id in selected_ids:
        if selected_id not in people_by_id:
            errors["base"] = "person_not_found"
            break

    if len(father_choices) > 1:
        errors[CONF_FATHER_ID] = "only_one_father"
    if len(mother_choices) > 1:
        errors[CONF_MOTHER_ID] = "only_one_mother"
    if father_id and mother_id and father_id == mother_id:
        errors[CONF_MOTHER_ID] = "parents_must_differ"
    spouse_field = CONF_SPOUSE_ID if gender == GENDER_FEMALE else CONF_SPOUSE_IDS
    if set(spouse_ids) & {value for value in (father_id, mother_id) if value}:
        errors[spouse_field] = "relationship_conflict"
    allowed_spouse_gender = _opposite_spouse_gender(gender)
    if allowed_spouse_gender is not None and any(
        people_by_id[spouse_person_id].get(CONF_GENDER) != allowed_spouse_gender
        for spouse_person_id in spouse_ids
        if spouse_person_id in people_by_id
    ):
        errors[spouse_field] = "spouse_gender_mismatch"
    if gender == GENDER_FEMALE and len(legacy_spouse_choices) > 1:
        errors[CONF_SPOUSE_ID] = "only_one_husband"
    if (
        gender == GENDER_FEMALE
        and spouse_id
        and _spouse_order_is_duplicate(
            spouse_order,
            spouse_id,
            person_id,
            people,
        )
    ):
        errors[CONF_SPOUSE_ORDER] = "spouse_order_duplicate"
    if set(sibling_ids) & {
        value for value in (father_id, mother_id, *spouse_ids) if value
    }:
        errors[CONF_SIBLING_IDS] = "relationship_conflict"

    for parent_id, field in (
        (father_id, CONF_FATHER_ID),
        (mother_id, CONF_MOTHER_ID),
    ):
        if parent_id and _creates_parent_cycle(person_id, parent_id, people):
            errors[field] = "relationship_cycle"

    has_new_link = bool(father_id or mother_id or spouse_ids or sibling_ids)
    legacy_related_id = _optional_string(
        current_person.get(CONF_RELATED_PERSON_ID) if current_person else None
    )
    legacy_relationship = _optional_string(
        current_person.get(CONF_RELATIONSHIP) if current_person else None
    )
    has_legacy_link = bool(legacy_related_id and legacy_relationship)

    if not is_first_person and not is_root_person and not has_new_link and not has_legacy_link:
        errors["base"] = "family_link_required"
    if is_adopted and not (father_id or mother_id):
        errors[CONF_IS_ADOPTED] = "adopted_parent_required"

    if _birth_order_is_duplicate(
        birth_order,
        father_id,
        mother_id,
        sibling_ids,
        people,
    ):
        errors[CONF_BIRTH_ORDER] = "birth_order_duplicate"

    level = 1
    related_id: str | None = None
    relationship: str | None = None
    if not is_first_person:
        parent_people = [
            people_by_id[parent_id]
            for parent_id in (father_id, mother_id)
            if parent_id in people_by_id
        ]
        if parent_people:
            level = max(
                max(1, int(parent.get(CONF_LEVEL, 1)))
                for parent in parent_people
            ) + 1
            related_id = father_id or mother_id
            relationship = (
                RELATION_ADOPTED_CHILD if is_adopted else RELATION_CHILD
            )
        elif spouse_ids and spouse_ids[0] in people_by_id:
            level = max(1, int(people_by_id[spouse_ids[0]].get(CONF_LEVEL, 1)))
            related_id = spouse_ids[0]
            relationship = RELATION_SPOUSE
        elif sibling_ids:
            sibling = people_by_id.get(sibling_ids[0])
            if sibling is not None:
                level = max(1, int(sibling.get(CONF_LEVEL, 1)))
                related_id = sibling_ids[0]
                relationship = RELATION_SIBLING
        elif has_legacy_link and legacy_related_id in people_by_id:
            related = people_by_id[legacy_related_id]
            level = _automatic_level(related, legacy_relationship or "")
            related_id = legacy_related_id
            relationship = legacy_relationship
        elif is_root_person:
            level = 1

        requested_level = int(user_input.get(CONF_LEVEL, 0) or 0)
        if requested_level > 0:
            level = requested_level

    if errors:
        return None

    image_path = _optional_string(
        current_person.get(CONF_IMAGE_PATH) if current_person else None
    )
    uploaded_file_id = _optional_string(user_input.get(CONF_IMAGE_UPLOAD))
    try:
        if uploaded_file_id:
            image_path = await async_store_uploaded_image(
                hass,
                uploaded_file_id,
                full_name,
                level,
                person_id,
            )
        elif current_person and image_path:
            old_level = int(current_person.get(CONF_LEVEL, 1))
            old_name = str(current_person.get(CONF_FULL_NAME, ""))
            if old_level != level or old_name != full_name:
                relocated = await async_relocate_image(
                    hass,
                    image_path,
                    full_name,
                    level,
                    person_id,
                )
                image_path = relocated or image_path
    except InvalidImageError as err:
        errors[CONF_IMAGE_UPLOAD] = str(err)
        return None
    except (OSError, ValueError):
        errors[CONF_IMAGE_UPLOAD] = "image_save_failed"
        return None

    return {
        CONF_PERSON_ID: person_id,
        CONF_FULL_NAME: full_name,
        CONF_GENDER: gender,
        CONF_BIRTH_DATE: birth_date,
        CONF_BIRTH_YEAR: birth_year,
        CONF_BIRTH_MONTH: birth_month,
        CONF_BIRTH_DAY: birth_day,
        CONF_DEATH_DATE: death_date if is_deceased else None,
        CONF_DEATH_YEAR: death_year if is_deceased else None,
        CONF_DEATH_MONTH: death_month if is_deceased else None,
        CONF_DEATH_DAY: death_day if is_deceased else None,
        CONF_IS_DECEASED: is_deceased,
        CONF_LEVEL: level,
        CONF_FATHER_ID: father_id,
        CONF_MOTHER_ID: mother_id,
        CONF_SPOUSE_ID: spouse_id,
        CONF_SPOUSE_IDS: spouse_ids,
        CONF_SPOUSE_ORDER: spouse_order,
        CONF_SIBLING_IDS: sibling_ids,
        CONF_BIRTH_ORDER: birth_order,
        CONF_IS_ADOPTED: is_adopted,
        CONF_RELATED_PERSON_ID: related_id,
        CONF_RELATIONSHIP: relationship,
        CONF_DETAILS: _optional_string(user_input.get(CONF_DETAILS)),
        CONF_IMAGE_PATH: image_path,
        CONF_SORT_ORDER: int(user_input.get(CONF_SORT_ORDER, 0) or 0),
        CONF_CREATED_AT: (
            current_person.get(CONF_CREATED_AT) if current_person else None
        ),
    }

def _person_subentry_data(person: dict[str, Any]) -> dict[str, Any]:
    """Build data accepted by ConfigFlow.async_create_entry subentries."""
    person_id = str(person[CONF_PERSON_ID])
    return {
        "subentry_type": SUBENTRY_TYPE_PERSON,
        "title": str(person[CONF_FULL_NAME]),
        "unique_id": person_id,
        "data": {key: person.get(key) for key in _PERSON_DATA_KEYS},
    }


def _initial_config_schema(*, include_root: bool) -> vol.Schema:
    """Return the initial setup form, including the root person for a new tree."""
    fields: dict[vol.Marker, Any] = {
        _required(CONF_TREE_NAME, "Gia phả gia đình"): selector.TextSelector(),
    }
    if include_root:
        fields.update(_person_schema([], current=None, is_first_person=True).schema)
    return vol.Schema(fields)


def _partial_date_schema_fields(
    values: dict[str, Any], *, birth: bool
) -> dict[vol.Marker, Any]:
    """Create editable dropdown fields for an incomplete date."""
    if birth:
        year_key, month_key, day_key = (
            CONF_BIRTH_YEAR,
            CONF_BIRTH_MONTH,
            CONF_BIRTH_DAY,
        )
    else:
        year_key, month_key, day_key = (
            CONF_DEATH_YEAR,
            CONF_DEATH_MONTH,
            CONF_DEATH_DAY,
        )

    current_year = date.today().year
    year_options = [str(year) for year in range(current_year, 1799, -1)]
    month_options = [
        {"value": f"{month:02d}", "label": f"{month:02d} - Tháng {month}"}
        for month in range(1, 13)
    ]
    day_options = [f"{day:02d}" for day in range(1, 32)]

    def suggested(key: str) -> str | None:
        value = values.get(key)
        if value in (None, ""):
            return None
        return f"{int(value):02d}" if key != year_key else str(int(value))

    return {
        _optional(year_key, suggested(year_key)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=year_options,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        _optional(month_key, suggested(month_key)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=month_options,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        _optional(day_key, suggested(day_key)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=day_options,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }


def _validate_person_core(
    user_input: dict[str, Any], errors: dict[str, str]
) -> dict[str, Any] | None:
    """Validate the first subentry step without consuming the uploaded file."""
    prepared = dict(user_input)
    full_name = str(user_input.get(CONF_FULL_NAME, "")).strip()
    if not full_name:
        errors[CONF_FULL_NAME] = "required"

    gender = str(user_input.get(CONF_GENDER, GENDER_OTHER))
    if gender not in GENDERS:
        errors[CONF_GENDER] = "required"

    try:
        birth_parts = normalize_partial_date(
            user_input.get(CONF_BIRTH_YEAR),
            user_input.get(CONF_BIRTH_MONTH),
            user_input.get(CONF_BIRTH_DAY),
            fallback=user_input.get(CONF_BIRTH_DATE),
        )
    except PartialDateError:
        birth_parts = (None, None, None)
        errors[CONF_BIRTH_DAY] = "invalid_partial_date"

    is_deceased = bool(user_input.get(CONF_IS_DECEASED, False))
    try:
        death_parts = normalize_partial_date(
            user_input.get(CONF_DEATH_YEAR),
            user_input.get(CONF_DEATH_MONTH),
            user_input.get(CONF_DEATH_DAY),
            fallback=user_input.get(CONF_DEATH_DATE),
        )
    except PartialDateError:
        death_parts = (None, None, None)
        errors[CONF_DEATH_DAY] = "invalid_partial_date"

    if not is_deceased:
        death_parts = (None, None, None)
    if is_future_partial_date(birth_parts):
        errors[CONF_BIRTH_YEAR] = "date_in_future"
    if is_deceased and is_future_partial_date(death_parts):
        errors[CONF_DEATH_YEAR] = "date_in_future"
    if is_deceased and birth_definitely_after_death(birth_parts, death_parts):
        errors[CONF_DEATH_YEAR] = "death_before_birth"

    if errors:
        return None

    prepared[CONF_FULL_NAME] = full_name
    prepared[CONF_GENDER] = gender
    prepared[CONF_IS_DECEASED] = is_deceased
    prepared[CONF_BIRTH_YEAR], prepared[CONF_BIRTH_MONTH], prepared[CONF_BIRTH_DAY] = birth_parts
    prepared[CONF_DEATH_YEAR], prepared[CONF_DEATH_MONTH], prepared[CONF_DEATH_DAY] = death_parts
    prepared[CONF_BIRTH_DATE] = partial_date_to_string(*birth_parts)
    prepared[CONF_DEATH_DATE] = (
        partial_date_to_string(*death_parts) if is_deceased else None
    )
    prepared[CONF_DETAILS] = _optional_string(user_input.get(CONF_DETAILS))
    return prepared


def _preview_placeholders(
    hass: Any,
    *,
    uploaded_file_id: str | None,
    entry_id: str | None,
    person_id: str | None,
    has_existing_image: bool,
    gender: str = GENDER_OTHER,
) -> dict[str, str]:
    """Return a signed image URL for config-flow avatar preview."""
    preview_path: str
    if uploaded_file_id:
        preview_path = UPLOAD_PREVIEW_API_URL.format(file_id=uploaded_file_id)
        preview_url = async_sign_path(hass, preview_path, timedelta(minutes=20))
        preview_note = "Ảnh mới đã chọn"
    elif entry_id and person_id and has_existing_image:
        preview_path = IMAGE_API_URL.format(entry_id=entry_id, person_id=person_id)
        preview_url = async_sign_path(hass, preview_path, timedelta(minutes=20))
        preview_note = "Ảnh hiện tại"
    else:
        default_avatar = {
            GENDER_MALE: "avatar-male.svg",
            GENDER_FEMALE: "avatar-female.svg",
        }.get(gender, "avatar-placeholder.svg")
        preview_url = f"{FRONTEND_STATIC_URL}/{default_avatar}?v=0.3.12"
        preview_note = "Ảnh đại diện mặc định theo giới tính"
    return {"preview_url": preview_url, "preview_note": preview_note}


def _person_core_schema(values: dict[str, Any]) -> vol.Schema:
    """Return personal fields shown before gender-dependent relationships."""
    schema: dict[vol.Marker, Any] = {
        _required(CONF_FULL_NAME, values.get(CONF_FULL_NAME, "")): selector.TextSelector(),
        _required(CONF_GENDER, values.get(CONF_GENDER, GENDER_MALE)): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    {"value": GENDER_MALE, "label": "Nam"},
                    {"value": GENDER_FEMALE, "label": "Nữ"},
                    {"value": GENDER_OTHER, "label": "Khác / không công bố"},
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        **_partial_date_schema_fields(values, birth=True),
        _required(
            CONF_IS_DECEASED, bool(values.get(CONF_IS_DECEASED, False))
        ): selector.BooleanSelector(),
        **_partial_date_schema_fields(values, birth=False),
        vol.Optional(CONF_IMAGE_UPLOAD): selector.FileSelector(
            selector.FileSelectorConfig(
                accept="image/jpeg,image/png,image/webp,image/gif,.jpg,.jpeg,.png,.webp,.gif"
            )
        ),
        _optional(CONF_DETAILS, values.get(CONF_DETAILS)): selector.TextSelector(
            selector.TextSelectorConfig(multiline=True)
        ),
    }
    return vol.Schema(schema)


def _person_relationship_schema(
    people: list[dict[str, Any]],
    *,
    current: dict[str, Any] | None,
    gender: str,
    is_first_person: bool,
) -> vol.Schema:
    """Return relationship fields with spouse choices filtered by gender."""
    values = current or {}
    schema: dict[vol.Marker, Any] = {}

    if not is_first_person and people:
        all_options = _person_options(people)
        father_options = _person_options(people, allowed_gender=GENDER_MALE)
        mother_options = _person_options(people, allowed_gender=GENDER_FEMALE)
        spouse_gender = _opposite_spouse_gender(gender)
        spouse_options = _person_options(people, allowed_gender=spouse_gender)
        schema.update(
            {
                _optional_list(
                    CONF_FATHER_ID, _string_list(values.get(CONF_FATHER_ID))[:1]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=father_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                _optional_list(
                    CONF_MOTHER_ID, _string_list(values.get(CONF_MOTHER_ID))[:1]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=mother_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        current_spouse_ids = _person_spouse_ids(values)
        if gender == GENDER_FEMALE:
            selected_husband = _string_list(values.get(CONF_SPOUSE_ID))[:1]
            if not selected_husband and current_spouse_ids:
                selected_husband = current_spouse_ids[:1]
            schema[
                _optional_list(CONF_SPOUSE_ID, selected_husband)
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=spouse_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            schema[
                _required(
                    CONF_SPOUSE_ORDER,
                    max(1, int(values.get(CONF_SPOUSE_ORDER, 1) or 1)),
                )
            ] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=99,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        else:
            schema[
                _optional_list(CONF_SPOUSE_IDS, current_spouse_ids)
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=spouse_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        schema.update(
            {
                _optional_list(
                    CONF_SIBLING_IDS, _string_list(values.get(CONF_SIBLING_IDS))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=all_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                _required(
                    CONF_BIRTH_ORDER, max(1, int(values.get(CONF_BIRTH_ORDER, 1) or 1))
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=99,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                _required(
                    CONF_IS_ADOPTED, bool(values.get(CONF_IS_ADOPTED, False))
                ): selector.BooleanSelector(),
                _required(CONF_LEVEL, values.get(CONF_LEVEL, 0)): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=99,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

    schema[
        _required(CONF_SORT_ORDER, values.get(CONF_SORT_ORDER, 0))
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=-999,
            max=999,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    return vol.Schema(schema)


def _person_schema(
    people: list[dict[str, Any]],
    *,
    current: dict[str, Any] | None,
    is_first_person: bool,
) -> vol.Schema:
    """Return the one-page schema used for the initial root-person setup."""
    values = current or {}
    fields = dict(_person_core_schema(values).schema)
    fields.update(
        _person_relationship_schema(
            people,
            current=values,
            gender=str(values.get(CONF_GENDER, GENDER_MALE)),
            is_first_person=is_first_person,
        ).schema
    )
    return vol.Schema(fields)


def _opposite_spouse_gender(gender: str) -> str | None:
    """Return the gender allowed in the spouse selector."""
    if gender == GENDER_MALE:
        return GENDER_FEMALE
    if gender == GENDER_FEMALE:
        return GENDER_MALE
    return None

def _person_options(
    people: list[dict[str, Any]],
    preferred_gender: str | None = None,
    *,
    allowed_gender: str | None = None,
) -> list[dict[str, str]]:
    """Build relationship options, optionally restricted to one gender."""
    filtered_people = [
        person
        for person in people
        if allowed_gender is None or person.get(CONF_GENDER) == allowed_gender
    ]

    def sort_key(person: dict[str, Any]) -> tuple[Any, ...]:
        gender_rank = 0 if person.get(CONF_GENDER) == preferred_gender else 1
        return (
            gender_rank,
            int(person.get(CONF_LEVEL, 1)),
            int(person.get(CONF_BIRTH_ORDER, 999) or 999),
            int(person.get(CONF_BIRTH_YEAR) or 9999),
            int(person.get(CONF_BIRTH_MONTH) or 13),
            int(person.get(CONF_BIRTH_DAY) or 32),
            str(person.get(CONF_FULL_NAME, "")).casefold(),
        )

    return [
        {
            "value": str(person[CONF_PERSON_ID]),
            "label": (
                f"Cấp {person.get(CONF_LEVEL, 1)} · "
                f"{person.get(CONF_FULL_NAME, '')} · "
                f"{_gender_label(str(person.get(CONF_GENDER, GENDER_OTHER)))}"
            ),
        }
        for person in sorted(filtered_people, key=sort_key)
    ]


def _people_from_entry(entry: ConfigEntry) -> list[dict[str, Any]]:
    raw_people: list[dict[str, Any]] = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_PERSON:
            continue
        data = dict(subentry.data)
        data.setdefault(CONF_PERSON_ID, subentry.unique_id or subentry.subentry_id)
        raw_people.append(data)

    people = [_normalize_person(person, raw_people) for person in raw_people]
    by_id = {str(person[CONF_PERSON_ID]): person for person in people}
    explicit_spouses = {
        person_id: _person_spouse_ids(person)
        for person_id, person in by_id.items()
    }

    # Resolve spouse links in both directions for editing. This means that when a
    # husband selected several wives, opening a wife's editor still shows her
    # husband and the correct wife position without requiring duplicate setup.
    for person_id, spouse_ids in explicit_spouses.items():
        for spouse_id in spouse_ids:
            spouse = by_id.get(spouse_id)
            if spouse is None:
                continue
            reciprocal = _person_spouse_ids(spouse)
            if person_id not in reciprocal:
                reciprocal.append(person_id)
            spouse[CONF_SPOUSE_IDS] = reciprocal
            spouse[CONF_SPOUSE_ID] = reciprocal[0] if reciprocal else None

    for husband in people:
        if husband.get(CONF_GENDER) != GENDER_MALE:
            continue
        husband_id = str(husband[CONF_PERSON_ID])
        explicit_order = {
            wife_id: index
            for index, wife_id in enumerate(
                explicit_spouses.get(husband_id, []), start=1
            )
        }
        wife_ids = [
            spouse_id
            for spouse_id in _person_spouse_ids(husband)
            if by_id.get(spouse_id, {}).get(CONF_GENDER) == GENDER_FEMALE
        ]
        wife_ids.sort(
            key=lambda wife_id: (
                0 if wife_id in explicit_order else 1,
                explicit_order.get(
                    wife_id,
                    max(1, int(by_id[wife_id].get(CONF_SPOUSE_ORDER, 1) or 1)),
                ),
                str(by_id[wife_id].get(CONF_FULL_NAME, "")).casefold(),
            )
        )
        other_spouses = [
            spouse_id
            for spouse_id in _person_spouse_ids(husband)
            if spouse_id not in wife_ids
        ]
        husband[CONF_SPOUSE_IDS] = [*wife_ids, *other_spouses]
        husband[CONF_SPOUSE_ID] = (
            husband[CONF_SPOUSE_IDS][0] if husband[CONF_SPOUSE_IDS] else None
        )
        for index, wife_id in enumerate(wife_ids, start=1):
            wife = by_id[wife_id]
            wife_spouses = _person_spouse_ids(wife)
            if husband_id in wife_spouses:
                wife[CONF_SPOUSE_ID] = husband_id
                if wife_id in explicit_order:
                    wife[CONF_SPOUSE_ORDER] = explicit_order[wife_id]
                elif not wife.get(CONF_SPOUSE_ORDER):
                    wife[CONF_SPOUSE_ORDER] = index

    return people


def _normalize_person(
    person: dict[str, Any], people: list[dict[str, Any]]
) -> dict[str, Any]:
    normalized = dict(person)
    try:
        birth_parts = normalize_partial_date(
            normalized.get(CONF_BIRTH_YEAR),
            normalized.get(CONF_BIRTH_MONTH),
            normalized.get(CONF_BIRTH_DAY),
            fallback=normalized.get(CONF_BIRTH_DATE),
        )
    except PartialDateError:
        birth_parts = (None, None, None)
    try:
        death_parts = normalize_partial_date(
            normalized.get(CONF_DEATH_YEAR),
            normalized.get(CONF_DEATH_MONTH),
            normalized.get(CONF_DEATH_DAY),
            fallback=normalized.get(CONF_DEATH_DATE),
        )
    except PartialDateError:
        death_parts = (None, None, None)
    if not bool(normalized.get(CONF_IS_DECEASED, False)):
        death_parts = (None, None, None)
    normalized[CONF_BIRTH_YEAR], normalized[CONF_BIRTH_MONTH], normalized[CONF_BIRTH_DAY] = birth_parts
    normalized[CONF_DEATH_YEAR], normalized[CONF_DEATH_MONTH], normalized[CONF_DEATH_DAY] = death_parts
    normalized[CONF_BIRTH_DATE] = partial_date_to_string(*birth_parts)
    normalized[CONF_DEATH_DATE] = partial_date_to_string(*death_parts)
    normalized[CONF_SIBLING_IDS] = _string_list(normalized.get(CONF_SIBLING_IDS))
    normalized[CONF_SPOUSE_IDS] = _person_spouse_ids(normalized)
    normalized[CONF_SPOUSE_ORDER] = max(
        1, int(normalized.get(CONF_SPOUSE_ORDER, 1) or 1)
    )
    normalized[CONF_BIRTH_ORDER] = max(
        1, int(normalized.get(CONF_BIRTH_ORDER, 1) or 1)
    )
    normalized[CONF_IS_ADOPTED] = bool(normalized.get(CONF_IS_ADOPTED, False))

    related_id = _optional_string(normalized.get(CONF_RELATED_PERSON_ID))
    relationship = _optional_string(normalized.get(CONF_RELATIONSHIP))
    by_id = {
        str(item.get(CONF_PERSON_ID)): item
        for item in people
        if item.get(CONF_PERSON_ID)
    }
    related = by_id.get(related_id or "")
    person_id = _optional_string(normalized.get(CONF_PERSON_ID))
    for field in (CONF_FATHER_ID, CONF_MOTHER_ID):
        value = _optional_string(normalized.get(field))
        normalized[field] = value if value in by_id and value != person_id else None
    normalized[CONF_SPOUSE_IDS] = [
        spouse_id
        for spouse_id in normalized[CONF_SPOUSE_IDS]
        if spouse_id in by_id and spouse_id != person_id
    ]
    normalized[CONF_SPOUSE_ID] = (
        normalized[CONF_SPOUSE_IDS][0] if normalized[CONF_SPOUSE_IDS] else None
    )
    normalized[CONF_SIBLING_IDS] = [
        sibling_id
        for sibling_id in normalized[CONF_SIBLING_IDS]
        if sibling_id in by_id and sibling_id != person_id
    ]

    if related_id and relationship in (RELATION_CHILD, RELATION_ADOPTED_CHILD):
        if not normalized.get(CONF_FATHER_ID) and not normalized.get(CONF_MOTHER_ID):
            if related and related.get(CONF_GENDER) == GENDER_FEMALE:
                normalized[CONF_MOTHER_ID] = related_id
            else:
                normalized[CONF_FATHER_ID] = related_id
        if relationship == RELATION_ADOPTED_CHILD:
            normalized[CONF_IS_ADOPTED] = True
    elif related_id and relationship == RELATION_SPOUSE:
        spouses = _person_spouse_ids(normalized)
        if related_id not in spouses:
            spouses.append(related_id)
        normalized[CONF_SPOUSE_IDS] = spouses
        normalized[CONF_SPOUSE_ID] = spouses[0] if spouses else None
    elif related_id and relationship == RELATION_SIBLING:
        siblings = _string_list(normalized.get(CONF_SIBLING_IDS))
        if related_id not in siblings:
            siblings.append(related_id)
        normalized[CONF_SIBLING_IDS] = siblings

    normalized.setdefault(CONF_FATHER_ID, None)
    normalized.setdefault(CONF_MOTHER_ID, None)
    normalized.setdefault(CONF_SPOUSE_ID, None)
    normalized.setdefault(CONF_SPOUSE_IDS, [])
    normalized.setdefault(CONF_SPOUSE_ORDER, 1)
    return normalized


def _automatic_level(related_person: dict[str, Any], relationship: str) -> int:
    related_level = max(1, int(related_person.get(CONF_LEVEL, 1)))
    if relationship in (RELATION_SPOUSE, RELATION_SIBLING):
        return related_level
    if relationship == RELATION_PARENT:
        return max(1, related_level - 1)
    return related_level + 1


def _creates_parent_cycle(
    person_id: str, parent_id: str, people: list[dict[str, Any]]
) -> bool:
    by_id = {str(person[CONF_PERSON_ID]): person for person in people}
    stack = [parent_id]
    seen: set[str] = set()
    while stack:
        cursor = stack.pop()
        if cursor == person_id:
            return True
        if cursor in seen:
            continue
        seen.add(cursor)
        parent = by_id.get(cursor)
        if parent is None:
            continue
        stack.extend(_parent_ids(parent))
    return False


def _parent_ids(person: dict[str, Any]) -> list[str]:
    parents = [
        value
        for value in (
            _optional_string(person.get(CONF_FATHER_ID)),
            _optional_string(person.get(CONF_MOTHER_ID)),
        )
        if value
    ]
    if not parents and person.get(CONF_RELATIONSHIP) in (
        RELATION_CHILD,
        RELATION_ADOPTED_CHILD,
    ):
        related = _optional_string(person.get(CONF_RELATED_PERSON_ID))
        if related:
            parents.append(related)
    return list(dict.fromkeys(parents))


def _birth_order_is_duplicate(
    birth_order: int,
    father_id: str | None,
    mother_id: str | None,
    sibling_ids: list[str],
    people: list[dict[str, Any]],
) -> bool:
    parent_key = _parent_key(father_id, mother_id)
    for person in people:
        existing_order = int(person.get(CONF_BIRTH_ORDER, 0) or 0)
        if existing_order != birth_order:
            continue
        if parent_key and parent_key == _parent_key(
            _optional_string(person.get(CONF_FATHER_ID)),
            _optional_string(person.get(CONF_MOTHER_ID)),
        ):
            return True
        if str(person.get(CONF_PERSON_ID)) in sibling_ids:
            return True
    return False


def _parent_key(father_id: str | None, mother_id: str | None) -> tuple[str, str] | None:
    if not father_id and not mother_id:
        return None
    return (father_id or "", mother_id or "")


def _has_structured_link(person: dict[str, Any]) -> bool:
    return bool(
        person.get(CONF_FATHER_ID)
        or person.get(CONF_MOTHER_ID)
        or _person_spouse_ids(person)
        or _string_list(person.get(CONF_SIBLING_IDS))
    )


def _person_spouse_ids(person: dict[str, Any]) -> list[str]:
    """Return ordered spouse IDs while retaining legacy spouse_id data."""
    spouse_ids = _string_list(person.get(CONF_SPOUSE_IDS))
    spouse_id = _optional_string(person.get(CONF_SPOUSE_ID))
    if spouse_id and spouse_id not in spouse_ids:
        spouse_ids.insert(0, spouse_id)
    return spouse_ids


def _spouse_order_is_duplicate(
    spouse_order: int,
    husband_id: str,
    person_id: str,
    people: list[dict[str, Any]],
) -> bool:
    """Return whether a husband already has another wife at this position."""
    by_id = {str(person[CONF_PERSON_ID]): person for person in people}
    husband = by_id.get(husband_id)
    if husband is not None:
        for index, wife_id in enumerate(_person_spouse_ids(husband), start=1):
            if wife_id != person_id and index == spouse_order:
                return True

    for person in people:
        other_id = str(person.get(CONF_PERSON_ID) or "")
        if not other_id or other_id == person_id:
            continue
        if person.get(CONF_GENDER) != GENDER_FEMALE:
            continue
        if husband_id not in _person_spouse_ids(person):
            continue
        if max(1, int(person.get(CONF_SPOUSE_ORDER, 1) or 1)) == spouse_order:
            return True
    return False



def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return []
    result: list[str] = []
    for item in values:
        text = _optional_string(item)
        if text and text not in result:
            result.append(text)
    return result


def _gender_label(gender: str) -> str:
    return {
        GENDER_MALE: "Nam",
        GENDER_FEMALE: "Nữ",
        GENDER_OTHER: "Khác",
    }.get(gender, "Khác")


def _required(key: str, suggested_value: Any) -> vol.Required:
    marker = vol.Required(key)
    if suggested_value is not None:
        marker.description = {"suggested_value": suggested_value}
    return marker


def _optional(key: str, suggested_value: Any) -> vol.Optional:
    marker = vol.Optional(key)
    if suggested_value not in (None, ""):
        marker.description = {"suggested_value": suggested_value}
    return marker


def _optional_list(key: str, suggested_value: list[str]) -> vol.Optional:
    marker = vol.Optional(key)
    marker.description = {"suggested_value": suggested_value}
    return marker
