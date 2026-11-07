"""Date validation must preserve incomplete dates without inventing missing parts."""

from datetime import date

import pytest

from custom_components.cay_gia_pha.date_utils import (
    PartialDateError,
    birth_definitely_after_death,
    calculate_age,
    normalize_partial_date,
    partial_date_to_string,
)


@pytest.mark.parametrize(
    ("parts", "text"),
    [
        ((None, None, None), None),
        ((1900, None, None), "1900"),
        ((1982, 3, None), "1982-03"),
        ((None, 10, 15), "--10-15"),
        ((2024, 2, 29), "2024-02-29"),
        ((None, None, 31), "---31"),
    ],
)
def test_incomplete_date_roundtrip(parts, text):
    assert partial_date_to_string(*parts) == text
    assert normalize_partial_date(None, None, None, fallback=text) == parts


def test_reject_invalid_leap_day():
    with pytest.raises(PartialDateError):
        normalize_partial_date(2025, 2, 29)


def test_age_uses_known_day_and_respects_unknowns():
    assert calculate_age(birth=(2000, 9, 23), deceased=False, death=(None, None, None), today=date(2026, 9, 22)) == 25
    assert calculate_age(birth=(2000, 9, 23), deceased=False, death=(None, None, None), today=date(2026, 9, 23)) == 26
    assert calculate_age(birth=(None, None, 11), deceased=False, death=(None, None, None), today=date(2026, 9, 23)) is None
    assert not birth_definitely_after_death((2000, None, None), (2000, 4, 2))
    assert birth_definitely_after_death((2001, None, None), (2000, 4, 2))
