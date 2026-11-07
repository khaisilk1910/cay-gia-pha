"""Regression tests for SQLite persistence and update semantics."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import sqlite3

import pytest

from custom_components.cay_gia_pha.const import (
    CONF_FATHER_ID,
    CONF_FULL_NAME,
    CONF_GENDER,
    CONF_PERSON_ID,
)
from custom_components.cay_gia_pha.storage import FamilyTreeStore


class FakeHass:
    def __init__(self, config_dir: Path) -> None:
        self.config = SimpleNamespace(path=lambda *parts: str(config_dir.joinpath(*parts)))

    async def async_add_executor_job(self, function, *args):
        return await asyncio.to_thread(function, *args)


def subentry(person_id: str, **overrides):
    return SimpleNamespace(
        subentry_id=f"sub_{person_id}",
        unique_id=person_id,
        data={
            CONF_PERSON_ID: person_id,
            CONF_FULL_NAME: f"Person {person_id}",
            CONF_GENDER: "male",
            **overrides,
        },
    )


@pytest.mark.asyncio
async def test_create_update_and_delete_increments_revision(tmp_path):
    store = FamilyTreeStore(FakeHass(tmp_path))
    await store.async_initialize()
    assert (await store.async_snapshot())["revision"] == 0

    father = subentry("p1")
    child = subentry("p2", **{CONF_FATHER_ID: "p1", CONF_GENDER: "female"})
    assert await store.async_sync_subentries([father, child]) == []
    snapshot = await store.async_snapshot()
    assert snapshot["stats"]["total"] == 2
    assert snapshot["revision"] == 1
    assert next(p for p in snapshot["people"] if p["person_id"] == "p2")["father_id"] == "p1"

    # Starting again with identical config should not increment revision.
    await store.async_sync_subentries([father, child])
    assert (await store.async_snapshot())["revision"] == 1
    await store.async_sync_subentries([father])
    assert (await store.async_snapshot())["revision"] == 2
    assert (await store.async_snapshot())["stats"]["total"] == 1


@pytest.mark.asyncio
async def test_preserve_legacy_data_only_on_initial_setup(tmp_path):
    store = FamilyTreeStore(FakeHass(tmp_path))
    await store.async_initialize()
    await store.async_sync_subentries([subentry("ancestor")])
    await store.async_sync_subentries([], preserve_existing_if_empty=True)
    snapshot = await store.async_snapshot()
    assert snapshot["stats"]["total"] == 1
    assert snapshot["revision"] == 1

    # Explicit deletion must continue to work.
    await store.async_sync_subentries([])
    snapshot = await store.async_snapshot()
    assert snapshot["stats"]["total"] == 0
    assert snapshot["revision"] == 2


def test_corrupt_database_is_not_treated_as_empty(tmp_path):
    store = FamilyTreeStore(FakeHass(tmp_path))
    store.data_dir.mkdir()
    store.database_path.write_bytes(b"invalid sqlite header, do not erase")
    with pytest.raises(sqlite3.DatabaseError):
        store._load_existing_people()

@pytest.mark.asyncio
async def test_failed_sync_rolls_back_every_person_change(tmp_path):
    """One invalid subentry must never partially replace persisted people."""
    store = FamilyTreeStore(FakeHass(tmp_path))
    await store.async_initialize()
    await store.async_sync_subentries([subentry("ancestor")])
    first = await store.async_snapshot()
    with pytest.raises((TypeError, ValueError)):
        await store.async_sync_subentries(
            [subentry("ancestor", **{CONF_FULL_NAME: "Edited ancestor"}),
             subentry("invalid", level="not-an-integer")]
        )
    last = await store.async_snapshot()
    assert last == first


@pytest.mark.asyncio
async def test_existing_images_only_removed_when_unreferenced(tmp_path):
    from custom_components.cay_gia_pha.const import CONF_IMAGE_PATH

    store = FamilyTreeStore(FakeHass(tmp_path))
    await store.async_initialize()
    await store.async_sync_subentries([
        subentry("p1", **{CONF_IMAGE_PATH: "shared/portrait.png"}),
        subentry("p2", **{CONF_IMAGE_PATH: "shared/portrait.png"}),
    ])
    assert await store.async_sync_subentries([subentry("p2", **{CONF_IMAGE_PATH: "shared/portrait.png"})]) == []
    assert await store.async_sync_subentries([]) == ["shared/portrait.png"]
