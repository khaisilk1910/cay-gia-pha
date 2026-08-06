"""Helpers for incomplete birth and death dates."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
import re
from typing import Any, Mapping

from .const import (
    CONF_BIRTH_DATE,
    CONF_BIRTH_DAY,
    CONF_BIRTH_MONTH,
    CONF_BIRTH_YEAR,
    CONF_DEATH_DATE,
    CONF_DEATH_DAY,
    CONF_DEATH_MONTH,
    CONF_DEATH_YEAR,
)


class PartialDateError(ValueError):
    """Raised when an incomplete date contains invalid components."""


def optional_int(value: Any) -> int | None:
    """Convert a selector value to an optional integer."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        number = int(value)
    except (TypeError, ValueError) as err:
        raise PartialDateError("not_a_number") from err
    return number


def normalize_partial_date(
    year: Any,
    month: Any,
    day: Any,
    *,
    fallback: Any = None,
) -> tuple[int | None, int | None, int | None]:
    """Normalize and validate optional year, month and day components."""
    normalized = (optional_int(year), optional_int(month), optional_int(day))
    if normalized == (None, None, None) and fallback not in (None, ""):
        normalized = parse_partial_date(fallback)

    normalized_year, normalized_month, normalized_day = normalized
    if normalized_year is not None and not 1 <= normalized_year <= 9999:
        raise PartialDateError("invalid_year")
    if normalized_month is not None and not 1 <= normalized_month <= 12:
        raise PartialDateError("invalid_month")
    if normalized_day is not None and not 1 <= normalized_day <= 31:
        raise PartialDateError("invalid_day")

    if normalized_month is not None and normalized_day is not None:
        validation_year = normalized_year or 2000
        if normalized_day > monthrange(validation_year, normalized_month)[1]:
            raise PartialDateError("invalid_day_for_month")

    return normalized_year, normalized_month, normalized_day


def parse_partial_date(value: Any) -> tuple[int | None, int | None, int | None]:
    """Parse legacy and canonical partial-date strings."""
    if isinstance(value, date):
        return value.year, value.month, value.day
    text = str(value or "").strip()
    if not text:
        return None, None, None

    patterns: tuple[
        tuple[str, tuple[int | None, int | None, int | None]], ...
    ] = (
        (r"^(\d{1,4})-(\d{1,2})-(\d{1,2})$", (1, 2, 3)),
        (r"^(\d{1,4})-(\d{1,2})$", (1, 2, None)),
        (r"^(\d{1,4})---(\d{1,2})$", (1, None, 2)),
        (r"^(\d{1,4})$", (1, None, None)),
        (r"^--(\d{1,2})-(\d{1,2})$", (None, 1, 2)),
        (r"^--(\d{1,2})$", (None, 1, None)),
        (r"^---(\d{1,2})$", (None, None, 1)),
    )
    for pattern, groups in patterns:
        match = re.fullmatch(pattern, text)
        if match is None:
            continue
        values = tuple(
            match.group(group) if group is not None else None for group in groups
        )
        return normalize_partial_date(*values)
    raise PartialDateError("invalid_format")


def partial_date_to_string(
    year: int | None, month: int | None, day: int | None
) -> str | None:
    """Return a deterministic string while retaining incomplete components."""
    if year is None and month is None and day is None:
        return None
    if year is not None and month is not None and day is not None:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if year is not None and month is not None:
        return f"{year:04d}-{month:02d}"
    if year is not None and day is not None:
        return f"{year:04d}---{day:02d}"
    if year is not None:
        return f"{year:04d}"
    if month is not None and day is not None:
        return f"--{month:02d}-{day:02d}"
    if month is not None:
        return f"--{month:02d}"
    return f"---{day:02d}"


def date_components_from_mapping(
    data: Mapping[str, Any], *, birth: bool
) -> tuple[int | None, int | None, int | None]:
    """Read normalized partial-date components from person data."""
    if birth:
        keys = (CONF_BIRTH_YEAR, CONF_BIRTH_MONTH, CONF_BIRTH_DAY)
        fallback_key = CONF_BIRTH_DATE
    else:
        keys = (CONF_DEATH_YEAR, CONF_DEATH_MONTH, CONF_DEATH_DAY)
        fallback_key = CONF_DEATH_DATE
    return normalize_partial_date(
        data.get(keys[0]),
        data.get(keys[1]),
        data.get(keys[2]),
        fallback=data.get(fallback_key),
    )


def birth_definitely_after_death(
    birth: tuple[int | None, int | None, int | None],
    death: tuple[int | None, int | None, int | None],
) -> bool:
    """Return true only when the known components prove the order is invalid."""
    birth_year, birth_month, birth_day = birth
    death_year, death_month, death_day = death
    if birth_year is None or death_year is None:
        return False
    if birth_year != death_year:
        return birth_year > death_year
    if birth_month is None or death_month is None:
        return False
    if birth_month != death_month:
        return birth_month > death_month
    if birth_day is None or death_day is None:
        return False
    return birth_day > death_day


def is_future_partial_date(
    value: tuple[int | None, int | None, int | None],
    *,
    today: date | None = None,
) -> bool:
    """Return true when known components prove a date is in the future."""
    today = today or date.today()
    year, month, day = value
    if year is None:
        return False
    if year != today.year:
        return year > today.year
    if month is None:
        return False
    if month != today.month:
        return month > today.month
    return day is not None and day > today.day


def calculate_age(
    *,
    birth: tuple[int | None, int | None, int | None],
    deceased: bool,
    death: tuple[int | None, int | None, int | None],
    today: date | None = None,
) -> int | None:
    """Calculate age using known years and exact months/days when available."""
    birth_year, birth_month, birth_day = birth
    if birth_year is None:
        return None

    if deceased:
        reference_year, reference_month, reference_day = death
        if reference_year is None:
            return None
    else:
        current = today or date.today()
        reference_year, reference_month, reference_day = (
            current.year,
            current.month,
            current.day,
        )

    age = reference_year - birth_year
    if age < 0:
        return None
    if (
        birth_month is not None
        and birth_day is not None
        and reference_month is not None
        and reference_day is not None
        and (reference_month, reference_day) < (birth_month, birth_day)
    ):
        age -= 1
    return age if age >= 0 else None
