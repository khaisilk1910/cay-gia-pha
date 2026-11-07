"""Lovelace resource registration behavior in storage/YAML/no-resource modes."""

import asyncio
from types import SimpleNamespace

from custom_components.cay_gia_pha import _async_register_lovelace_resource

URL = "/cay_gia_pha_static/cay-gia-pha-card.js"


class ResourceStorage:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.loaded = False
        self.writes = 0

    async def async_get_info(self):
        self.loaded = True
        return {"resources": len(self.items)}

    def async_items(self):
        assert self.loaded
        return list(self.items)

    async def async_create_item(self, data):
        self.writes += 1
        self.items.append({"id": "one", "type": data["res_type"], "url": data["url"]})

    async def async_update_item(self, id_, data):
        self.writes += 1
        for item in self.items:
            if item["id"] == id_:
                item.update({"type": data["res_type"], "url": data["url"]})
                return
        raise KeyError(id_)


class ResourceYaml:
    def __init__(self, items=None):
        self.items = items or []

    async def async_get_info(self):
        return {"resources": len(self.items)}

    def async_items(self):
        return self.items


def run(coro):
    return asyncio.run(coro)


def test_storage_resources_create_once_then_upgrade():
    resources = ResourceStorage()
    hass = SimpleNamespace(data={"lovelace": SimpleNamespace(resources=resources)}, extras=[])
    run(_async_register_lovelace_resource(hass, URL, "a"))
    run(_async_register_lovelace_resource(hass, URL, "a"))
    run(_async_register_lovelace_resource(hass, URL, "b"))
    assert resources.writes == 2
    assert resources.items == [{"id": "one", "type": "module", "url": URL + "?v=b"}]
    assert hass.extras == []


def test_yaml_resources_use_frontend_fallback_only_when_absent():
    hass = SimpleNamespace(data={"lovelace": {"resources": ResourceYaml()}}, extras=[])
    run(_async_register_lovelace_resource(hass, URL, "a"))
    assert hass.extras == [URL + "?v=a"]
    hass = SimpleNamespace(
        data={"lovelace": {"resources": ResourceYaml([{"url": URL + "?v=old"}])}}, extras=[]
    )
    run(_async_register_lovelace_resource(hass, URL, "a"))
    assert hass.extras == []


def test_no_lovelace_loaded_uses_frontend_module():
    hass = SimpleNamespace(data={}, extras=[])
    run(_async_register_lovelace_resource(hass, URL, "a"))
    assert hass.extras == [URL + "?v=a"]
