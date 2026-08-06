"""SQLite persistence for Cây Gia Phả."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry

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
    CONF_UPDATED_AT,
    DATABASE_FILENAME,
    DATABASE_SCHEMA_VERSION,
    DATA_DIR_NAME,
    GENDER_FEMALE,
    GENDER_MALE,
    RELATION_ADOPTED_CHILD,
    RELATION_CHILD,
    RELATION_SIBLING,
    RELATION_SPOUSE,
)
from .date_utils import (
    PartialDateError,
    normalize_partial_date,
    partial_date_to_string,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class FamilyTreeStore:
    """Own SQLite persistence outside the custom_components directory."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.data_dir = Path(hass.config.path(DATA_DIR_NAME))
        self.database_path = self.data_dir / DATABASE_FILENAME

    async def async_initialize(self) -> None:
        """Create the data directory and migrate the database schema."""
        await self.hass.async_add_executor_job(self._initialize)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            journal_mode = str(
                connection.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower()
            if journal_mode != "wal":
                connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS persons (
                    person_id TEXT PRIMARY KEY,
                    subentry_id TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    birth_date TEXT,
                    birth_year INTEGER,
                    birth_month INTEGER,
                    birth_day INTEGER,
                    death_date TEXT,
                    death_year INTEGER,
                    death_month INTEGER,
                    death_day INTEGER,
                    is_deceased INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    father_id TEXT,
                    mother_id TEXT,
                    spouse_id TEXT,
                    spouse_ids TEXT NOT NULL DEFAULT '[]',
                    spouse_order INTEGER NOT NULL DEFAULT 1,
                    sibling_ids TEXT NOT NULL DEFAULT '[]',
                    birth_order INTEGER NOT NULL DEFAULT 1,
                    is_adopted INTEGER NOT NULL DEFAULT 0,
                    related_person_id TEXT,
                    relationship TEXT,
                    details TEXT,
                    image_path TEXT,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            schema_row = connection.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            try:
                previous_schema_version = int(schema_row[0]) if schema_row else 0
            except (TypeError, ValueError):
                previous_schema_version = 0

            columns_migrated = self._migrate_person_columns(connection)
            if columns_migrated or previous_schema_version < DATABASE_SCHEMA_VERSION:
                self._normalize_legacy_person_dates(connection)

            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_persons_level
                    ON persons(level, birth_order, birth_year, birth_month, birth_day, sort_order, full_name);
                CREATE INDEX IF NOT EXISTS idx_persons_related
                    ON persons(related_person_id);
                CREATE INDEX IF NOT EXISTS idx_persons_parents
                    ON persons(father_id, mother_id, birth_order);
                CREATE INDEX IF NOT EXISTS idx_persons_spouse
                    ON persons(spouse_id);
                CREATE INDEX IF NOT EXISTS idx_persons_gender
                    ON persons(gender);
                """
            )
            if previous_schema_version != DATABASE_SCHEMA_VERSION:
                connection.execute(
                    """
                    INSERT INTO meta(key, value) VALUES('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(DATABASE_SCHEMA_VERSION),),
                )
            connection.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES('revision', '0')"
            )

    @staticmethod
    def _migrate_person_columns(connection: sqlite3.Connection) -> bool:
        """Add missing columns and report whether the schema changed."""
        existing = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(persons)").fetchall()
        }
        columns = {
            "father_id": "TEXT",
            "mother_id": "TEXT",
            "spouse_id": "TEXT",
            "spouse_ids": "TEXT NOT NULL DEFAULT '[]'",
            "spouse_order": "INTEGER NOT NULL DEFAULT 1",
            "sibling_ids": "TEXT NOT NULL DEFAULT '[]'",
            "birth_order": "INTEGER NOT NULL DEFAULT 1",
            "is_adopted": "INTEGER NOT NULL DEFAULT 0",
            "birth_year": "INTEGER",
            "birth_month": "INTEGER",
            "birth_day": "INTEGER",
            "death_year": "INTEGER",
            "death_month": "INTEGER",
            "death_day": "INTEGER",
        }
        migrated = False
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE persons ADD COLUMN {name} {definition}"
                )
                migrated = True
        if migrated:
            connection.execute("DROP INDEX IF EXISTS idx_persons_level")

        return migrated

    @staticmethod
    def _normalize_legacy_person_dates(connection: sqlite3.Connection) -> None:
        """Normalize legacy date columns only while upgrading the database."""
        rows = connection.execute(
            """
            SELECT person_id, birth_date, death_date, is_deceased,
                birth_year, birth_month, birth_day,
                death_year, death_month, death_day
            FROM persons
            """
        ).fetchall()
        for row in rows:
            birth = _safe_partial_date(
                row["birth_year"], row["birth_month"], row["birth_day"],
                fallback=row["birth_date"],
            )
            death = _safe_partial_date(
                row["death_year"], row["death_month"], row["death_day"],
                fallback=row["death_date"],
            )
            if not bool(row["is_deceased"]):
                death = (None, None, None)
            birth_date = partial_date_to_string(*birth)
            death_date = partial_date_to_string(*death)
            if (
                row["birth_date"] == birth_date
                and row["birth_year"] == birth[0]
                and row["birth_month"] == birth[1]
                and row["birth_day"] == birth[2]
                and row["death_date"] == death_date
                and row["death_year"] == death[0]
                and row["death_month"] == death[1]
                and row["death_day"] == death[2]
            ):
                continue
            connection.execute(
                """
                UPDATE persons SET
                    birth_date = ?, birth_year = ?, birth_month = ?, birth_day = ?,
                    death_date = ?, death_year = ?, death_month = ?, death_day = ?
                WHERE person_id = ?
                """,
                (
                    birth_date, *birth,
                    death_date, *death,
                    row["person_id"],
                ),
            )

    async def async_sync_subentries(
        self, subentries: Iterable[ConfigSubentry]
    ) -> list[str]:
        """Mirror person subentries to SQLite and return orphan image paths."""
        serializable = [
            {
                "subentry_id": subentry.subentry_id,
                "unique_id": subentry.unique_id,
                "data": dict(subentry.data),
            }
            for subentry in subentries
        ]
        return await self.hass.async_add_executor_job(
            self._sync_subentries, serializable
        )

    def _sync_subentries(self, subentries: list[dict[str, Any]]) -> list[str]:
        now = _utc_now()
        removed_image_paths: list[str] = []

        prepared_items: list[dict[str, Any]] = []
        data_by_id: dict[str, dict[str, Any]] = {}
        for item in subentries:
            data = dict(item["data"])
            person_id = str(
                data.get(CONF_PERSON_ID)
                or item.get("unique_id")
                or item["subentry_id"]
            )
            data[CONF_PERSON_ID] = person_id
            prepared = {**item, "data": data, "person_id": person_id}
            prepared_items.append(prepared)
            data_by_id[person_id] = data

        current_ids = {item["person_id"] for item in prepared_items}
        active_image_paths = {
            image_path
            for item in prepared_items
            if (image_path := _nullable_text(item["data"].get(CONF_IMAGE_PATH)))
        }

        with self._connect() as connection:
            existing_rows = {
                row["person_id"]: row
                for row in connection.execute("SELECT * FROM persons").fetchall()
            }

            stale_ids = set(existing_rows) - current_ids
            changed = bool(stale_ids)
            for stale_id in stale_ids:
                stale_image = existing_rows[stale_id]["image_path"]
                if stale_image:
                    removed_image_paths.append(str(stale_image))
                connection.execute(
                    "DELETE FROM persons WHERE person_id = ?", (stale_id,)
                )

            for item in prepared_items:
                data = item["data"]
                person_id = item["person_id"]
                existing = existing_rows.get(person_id)
                created_at = str(
                    data.get(CONF_CREATED_AT)
                    or (existing["created_at"] if existing else now)
                )
                old_image_path = existing["image_path"] if existing else None
                new_image_path = _nullable_text(data.get(CONF_IMAGE_PATH))
                if old_image_path and old_image_path != new_image_path:
                    removed_image_paths.append(str(old_image_path))

                birth_parts = _safe_partial_date(
                    data.get(CONF_BIRTH_YEAR),
                    data.get(CONF_BIRTH_MONTH),
                    data.get(CONF_BIRTH_DAY),
                    fallback=data.get(CONF_BIRTH_DATE),
                )
                death_parts = _safe_partial_date(
                    data.get(CONF_DEATH_YEAR),
                    data.get(CONF_DEATH_MONTH),
                    data.get(CONF_DEATH_DAY),
                    fallback=data.get(CONF_DEATH_DATE),
                )
                is_deceased = bool(data.get(CONF_IS_DECEASED, False))
                if not is_deceased:
                    death_parts = (None, None, None)

                relationships = _normalized_relationship_fields(data, data_by_id)
                sibling_json = json.dumps(
                    relationships[CONF_SIBLING_IDS],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                spouse_json = json.dumps(
                    relationships[CONF_SPOUSE_IDS],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

                desired = {
                    "subentry_id": item["subentry_id"],
                    "full_name": str(data.get(CONF_FULL_NAME, "")).strip(),
                    "gender": str(data.get(CONF_GENDER, "other")),
                    "birth_date": partial_date_to_string(*birth_parts),
                    "birth_year": birth_parts[0],
                    "birth_month": birth_parts[1],
                    "birth_day": birth_parts[2],
                    "death_date": partial_date_to_string(*death_parts),
                    "death_year": death_parts[0],
                    "death_month": death_parts[1],
                    "death_day": death_parts[2],
                    "is_deceased": int(is_deceased),
                    "level": max(1, int(data.get(CONF_LEVEL, 1))),
                    "father_id": relationships[CONF_FATHER_ID],
                    "mother_id": relationships[CONF_MOTHER_ID],
                    "spouse_id": relationships[CONF_SPOUSE_ID],
                    "spouse_ids": spouse_json,
                    "spouse_order": relationships[CONF_SPOUSE_ORDER],
                    "sibling_ids": sibling_json,
                    "birth_order": relationships[CONF_BIRTH_ORDER],
                    "is_adopted": int(relationships[CONF_IS_ADOPTED]),
                    "related_person_id": _nullable_text(
                        data.get(CONF_RELATED_PERSON_ID)
                    ),
                    "relationship": _nullable_text(data.get(CONF_RELATIONSHIP)),
                    "details": _nullable_text(data.get(CONF_DETAILS)),
                    "image_path": new_image_path,
                    "sort_order": int(data.get(CONF_SORT_ORDER, 0)),
                    "created_at": created_at,
                }

                if existing is not None and all(
                    existing[column] == value for column, value in desired.items()
                ):
                    continue

                changed = True

                connection.execute(
                    """
                    INSERT INTO persons (
                        person_id, subentry_id, full_name, gender,
                        birth_date, birth_year, birth_month, birth_day,
                        death_date, death_year, death_month, death_day,
                        is_deceased, level, father_id, mother_id, spouse_id,
                        spouse_ids, spouse_order, sibling_ids, birth_order,
                        is_adopted, related_person_id, relationship, details,
                        image_path, sort_order, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT(person_id) DO UPDATE SET
                        subentry_id = excluded.subentry_id,
                        full_name = excluded.full_name,
                        gender = excluded.gender,
                        birth_date = excluded.birth_date,
                        birth_year = excluded.birth_year,
                        birth_month = excluded.birth_month,
                        birth_day = excluded.birth_day,
                        death_date = excluded.death_date,
                        death_year = excluded.death_year,
                        death_month = excluded.death_month,
                        death_day = excluded.death_day,
                        is_deceased = excluded.is_deceased,
                        level = excluded.level,
                        father_id = excluded.father_id,
                        mother_id = excluded.mother_id,
                        spouse_id = excluded.spouse_id,
                        spouse_ids = excluded.spouse_ids,
                        spouse_order = excluded.spouse_order,
                        sibling_ids = excluded.sibling_ids,
                        birth_order = excluded.birth_order,
                        is_adopted = excluded.is_adopted,
                        related_person_id = excluded.related_person_id,
                        relationship = excluded.relationship,
                        details = excluded.details,
                        image_path = excluded.image_path,
                        sort_order = excluded.sort_order,
                        updated_at = excluded.updated_at
                    """,
                    (
                        person_id,
                        desired["subentry_id"],
                        desired["full_name"],
                        desired["gender"],
                        desired["birth_date"],
                        desired["birth_year"],
                        desired["birth_month"],
                        desired["birth_day"],
                        desired["death_date"],
                        desired["death_year"],
                        desired["death_month"],
                        desired["death_day"],
                        desired["is_deceased"],
                        desired["level"],
                        desired["father_id"],
                        desired["mother_id"],
                        desired["spouse_id"],
                        desired["spouse_ids"],
                        desired["spouse_order"],
                        desired["sibling_ids"],
                        desired["birth_order"],
                        desired["is_adopted"],
                        desired["related_person_id"],
                        desired["relationship"],
                        desired["details"],
                        desired["image_path"],
                        desired["sort_order"],
                        desired["created_at"],
                        now,
                    ),
                )

            if changed:
                revision_row = connection.execute(
                    "SELECT value FROM meta WHERE key = 'revision'"
                ).fetchone()
                revision = int(revision_row[0]) if revision_row else 0
                connection.execute(
                    """
                    INSERT INTO meta(key, value) VALUES('revision', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(revision + 1),),
                )

        return [
            image_path
            for image_path in dict.fromkeys(removed_image_paths)
            if image_path not in active_image_paths
        ]

    async def async_snapshot(self) -> dict[str, Any]:
        """Return all people and aggregate statistics."""
        return await self.hass.async_add_executor_job(self._snapshot)

    def _snapshot(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM persons
                ORDER BY level ASC,
                    birth_order ASC,
                    COALESCE(birth_year, 9999) ASC,
                    COALESCE(birth_month, 13) ASC,
                    COALESCE(birth_day, 32) ASC,
                    sort_order ASC,
                    full_name COLLATE NOCASE ASC
                """
            ).fetchall()
            revision_row = connection.execute(
                "SELECT value FROM meta WHERE key = 'revision'"
            ).fetchone()

        people = _normalize_people_relationships([_row_to_person(row) for row in rows])
        total = len(people)
        male = sum(person[CONF_GENDER] == GENDER_MALE for person in people)
        female = sum(person[CONF_GENDER] == GENDER_FEMALE for person in people)
        deceased = sum(bool(person[CONF_IS_DECEASED]) for person in people)
        adopted = sum(bool(person[CONF_IS_ADOPTED]) for person in people)
        levels = max((int(person[CONF_LEVEL]) for person in people), default=0)
        root = next((person for person in people if person[CONF_LEVEL] == 1), None)

        return {
            "people": people,
            "stats": {
                "total": total,
                "male": male,
                "female": female,
                "other": total - male - female,
                "living": total - deceased,
                "deceased": deceased,
                "adopted": adopted,
                "levels": levels,
                "root_name": root[CONF_FULL_NAME] if root else None,
            },
            "revision": int(revision_row[0]) if revision_row else 0,
        }

    async def async_person(self, person_id: str) -> dict[str, Any] | None:
        """Return one person by ID."""
        return await self.hass.async_add_executor_job(self._person, person_id)

    def _person(self, person_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM persons WHERE person_id = ?", (person_id,)
            ).fetchone()
        return _row_to_person(row) if row else None

    @classmethod
    async def async_load_existing_people(
        cls, hass: HomeAssistant
    ) -> list[dict[str, Any]]:
        """Migrate and load existing DB data before a config entry exists."""
        store = cls(hass)
        return await hass.async_add_executor_job(
            store._initialize_and_load_existing_people
        )

    def _initialize_and_load_existing_people(self) -> list[dict[str, Any]]:
        self._initialize()
        return self._load_existing_people()

    def _load_existing_people(self) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM persons
                    ORDER BY level, birth_order,
                        COALESCE(birth_year, 9999),
                        COALESCE(birth_month, 13),
                        COALESCE(birth_day, 32), sort_order, full_name
                    """
                ).fetchall()
        except sqlite3.Error:
            return []
        return _normalize_people_relationships([_row_to_person(row) for row in rows])

    async def async_export_json(self) -> str:
        """Return a deterministic JSON export for future backup services."""
        snapshot = await self.async_snapshot()
        return json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True)


def _normalize_people_relationships(people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Populate structured fields in memory for legacy 0.1.x rows."""
    by_id = {str(person[CONF_PERSON_ID]): person for person in people}
    for person in people:
        spouse_ids = _string_list(person.get(CONF_SPOUSE_IDS))
        spouse_id = _nullable_text(person.get(CONF_SPOUSE_ID))
        if spouse_id and spouse_id not in spouse_ids:
            spouse_ids.insert(0, spouse_id)
        person[CONF_SPOUSE_IDS] = spouse_ids
        person[CONF_SPOUSE_ID] = spouse_ids[0] if spouse_ids else None
        person[CONF_SPOUSE_ORDER] = max(
            1, int(person.get(CONF_SPOUSE_ORDER, 1) or 1)
        )
        related_id = _nullable_text(person.get(CONF_RELATED_PERSON_ID))
        relationship = _nullable_text(person.get(CONF_RELATIONSHIP))
        if not related_id:
            continue
        related = by_id.get(related_id)
        if relationship in (RELATION_CHILD, RELATION_ADOPTED_CHILD):
            if not person.get(CONF_FATHER_ID) and not person.get(CONF_MOTHER_ID):
                if related and related.get(CONF_GENDER) == GENDER_FEMALE:
                    person[CONF_MOTHER_ID] = related_id
                else:
                    person[CONF_FATHER_ID] = related_id
            if relationship == RELATION_ADOPTED_CHILD:
                person[CONF_IS_ADOPTED] = True
        elif relationship == RELATION_SPOUSE:
            spouse_ids = _string_list(person.get(CONF_SPOUSE_IDS))
            if related_id not in spouse_ids:
                spouse_ids.append(related_id)
            person[CONF_SPOUSE_IDS] = spouse_ids
            person[CONF_SPOUSE_ID] = spouse_ids[0] if spouse_ids else None
        elif relationship == RELATION_SIBLING:
            siblings = _string_list(person.get(CONF_SIBLING_IDS))
            if related_id not in siblings:
                siblings.append(related_id)
            person[CONF_SIBLING_IDS] = siblings
    return people


def _normalized_relationship_fields(
    data: Mapping[str, Any], data_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    person_id = _nullable_text(data.get(CONF_PERSON_ID))
    father_id = _nullable_text(data.get(CONF_FATHER_ID))
    mother_id = _nullable_text(data.get(CONF_MOTHER_ID))
    spouse_ids = _string_list(data.get(CONF_SPOUSE_IDS))
    legacy_spouse_id = _nullable_text(data.get(CONF_SPOUSE_ID))
    if legacy_spouse_id and legacy_spouse_id not in spouse_ids:
        spouse_ids.insert(0, legacy_spouse_id)
    sibling_ids = _string_list(data.get(CONF_SIBLING_IDS))

    if father_id not in data_by_id or father_id == person_id:
        father_id = None
    if mother_id not in data_by_id or mother_id == person_id:
        mother_id = None
    spouse_ids = [
        spouse_id
        for spouse_id in spouse_ids
        if spouse_id in data_by_id and spouse_id != person_id
    ]
    spouse_id = spouse_ids[0] if spouse_ids else None
    sibling_ids = [
        sibling_id
        for sibling_id in sibling_ids
        if sibling_id in data_by_id and sibling_id != person_id
    ]
    is_adopted = bool(data.get(CONF_IS_ADOPTED, False))
    birth_order = max(1, int(data.get(CONF_BIRTH_ORDER, 1) or 1))

    related_id = _nullable_text(data.get(CONF_RELATED_PERSON_ID))
    relationship = _nullable_text(data.get(CONF_RELATIONSHIP))
    related = data_by_id.get(related_id or "")

    if related_id and relationship in (RELATION_CHILD, RELATION_ADOPTED_CHILD):
        if not father_id and not mother_id:
            if related and related.get(CONF_GENDER) == GENDER_FEMALE:
                mother_id = related_id
            else:
                father_id = related_id
        if relationship == RELATION_ADOPTED_CHILD:
            is_adopted = True
    elif related_id and relationship == RELATION_SPOUSE:
        if related_id not in spouse_ids:
            spouse_ids.append(related_id)
        spouse_id = spouse_ids[0] if spouse_ids else None
    elif related_id and relationship == RELATION_SIBLING:
        if related_id not in sibling_ids:
            sibling_ids.append(related_id)

    return {
        CONF_FATHER_ID: father_id,
        CONF_MOTHER_ID: mother_id,
        CONF_SPOUSE_ID: spouse_id,
        CONF_SPOUSE_IDS: spouse_ids,
        CONF_SPOUSE_ORDER: max(1, int(data.get(CONF_SPOUSE_ORDER, 1) or 1)),
        CONF_SIBLING_IDS: sibling_ids,
        CONF_BIRTH_ORDER: birth_order,
        CONF_IS_ADOPTED: is_adopted,
    }


def _safe_partial_date(
    year: Any, month: Any, day: Any, *, fallback: Any = None
) -> tuple[int | None, int | None, int | None]:
    """Return valid components while tolerating corrupt legacy values."""
    try:
        return normalize_partial_date(year, month, day, fallback=fallback)
    except PartialDateError:
        return None, None, None


def _nullable_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed = [value]
        values = parsed if isinstance(parsed, list) else [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        return []

    result: list[str] = []
    for item in values:
        text = _nullable_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _row_to_person(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        CONF_PERSON_ID: row["person_id"],
        "subentry_id": row["subentry_id"],
        CONF_FULL_NAME: row["full_name"],
        CONF_GENDER: row["gender"],
        CONF_BIRTH_DATE: row["birth_date"],
        CONF_BIRTH_YEAR: row["birth_year"],
        CONF_BIRTH_MONTH: row["birth_month"],
        CONF_BIRTH_DAY: row["birth_day"],
        CONF_DEATH_DATE: row["death_date"],
        CONF_DEATH_YEAR: row["death_year"],
        CONF_DEATH_MONTH: row["death_month"],
        CONF_DEATH_DAY: row["death_day"],
        CONF_IS_DECEASED: bool(row["is_deceased"]),
        CONF_LEVEL: int(row["level"]),
        CONF_FATHER_ID: row["father_id"],
        CONF_MOTHER_ID: row["mother_id"],
        CONF_SPOUSE_ID: row["spouse_id"],
        CONF_SPOUSE_IDS: _string_list(row["spouse_ids"]),
        CONF_SPOUSE_ORDER: max(1, int(row["spouse_order"] or 1)),
        CONF_SIBLING_IDS: _string_list(row["sibling_ids"]),
        CONF_BIRTH_ORDER: max(1, int(row["birth_order"] or 1)),
        CONF_IS_ADOPTED: bool(row["is_adopted"]),
        CONF_RELATED_PERSON_ID: row["related_person_id"],
        CONF_RELATIONSHIP: row["relationship"],
        CONF_DETAILS: row["details"],
        CONF_IMAGE_PATH: row["image_path"],
        CONF_SORT_ORDER: int(row["sort_order"]),
        CONF_CREATED_AT: row["created_at"],
        CONF_UPDATED_AT: row["updated_at"],
    }
