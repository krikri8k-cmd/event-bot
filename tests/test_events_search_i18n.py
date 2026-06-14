"""i18n for nearby events search empty states and date filters."""

import pytest

from utils.i18n import format_translation, t

pytestmark = pytest.mark.no_db


def test_not_found_with_radius_english_date():
    text = format_translation(
        "events.not_found_with_radius",
        "en",
        radius=5,
        date_text=t("events.date_for_today", "en"),
    )
    assert "No events within 5 km for today" in text
    assert "на сегодня" not in text


def test_not_found_with_radius_russian_date():
    text = format_translation(
        "events.not_found_with_radius",
        "ru",
        radius=5,
        date_text=t("events.date_for_today", "ru"),
    )
    assert "на сегодня" in text


def test_page_empty_translations():
    assert t("events.page_empty", "en") == "Nothing found nearby yet."
    assert "ничего" in t("events.page_empty", "ru")
