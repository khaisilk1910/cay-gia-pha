"""WebSocket API for the Cây Gia Phả dashboard card."""

from __future__ import annotations

from datetime import timedelta

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_IMAGE_PATH,
    CONF_PERSON_ID,
    CONF_TREE_NAME,
    IMAGE_API_URL,
    WS_TYPE_GET_TREE,
)


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register WebSocket commands once."""
    websocket_api.async_register_command(hass, websocket_get_tree)


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_GET_TREE,
        vol.Required("entry_id"): str,
    }
)
@websocket_api.async_response
async def websocket_get_tree(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return tree data with temporary signed image URLs."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    runtime = getattr(entry, "runtime_data", None) if entry is not None else None
    if runtime is None:
        connection.send_error(msg["id"], "not_found", "Family tree is not loaded")
        return

    snapshot = runtime.coordinator.data
    people = []
    for stored_person in snapshot.get("people", []):
        person = dict(stored_person)
        if person.get(CONF_IMAGE_PATH):
            image_path = IMAGE_API_URL.format(
                entry_id=entry.entry_id,
                person_id=person[CONF_PERSON_ID],
            )
            person["image_url"] = async_sign_path(
                hass,
                image_path,
                timedelta(minutes=20),
            )
        person.pop(CONF_IMAGE_PATH, None)
        people.append(person)

    connection.send_result(
        msg["id"],
        {
            "entry_id": entry.entry_id,
            "title": entry.data.get(CONF_TREE_NAME, entry.title),
            "people": people,
            "stats": snapshot.get("stats", {}),
            "revision": snapshot.get("revision", 0),
        },
    )
