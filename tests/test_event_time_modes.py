"""Три сценария времени события: рендер строки времени и i18n «Весь день»."""

from datetime import UTC, datetime

import pytest

from bot_enhanced_v3 import format_event_when
from utils.i18n import t

pytestmark = pytest.mark.no_db


def _bali_event(starts_utc=None, ends_utc=None, time_mode=None):
    """Событие на Бали (city='bali' -> tz Asia/Makassar = UTC+8)."""
    return {
        "city": "bali",
        "lat": -8.65,
        "lng": 115.13,
        "starts_at": starts_utc,
        "ends_at": ends_utc,
        "time_mode": time_mode,
    }


def test_all_day_renders_label():
    """Сценарий 3: 'весь день' -> локализованная метка, цифры не показываем."""
    # 09:00 Бали = 01:00 UTC, 21:00 Бали = 13:00 UTC
    ev = _bali_event(
        starts_utc=datetime(2026, 7, 10, 1, 0, tzinfo=UTC),
        ends_utc=datetime(2026, 7, 10, 13, 0, tzinfo=UTC),
        time_mode="all_day",
    )
    assert format_event_when(ev, user_id=None) == "Весь день"


def test_range_renders_start_end():
    """Сценарий 1: диапазон -> 'HH:MM–HH:MM' в локальном времени Бали."""
    # 09:00 Бали = 01:00 UTC, 19:00 Бали = 11:00 UTC
    ev = _bali_event(
        starts_utc=datetime(2026, 6, 8, 1, 0, tzinfo=UTC),
        ends_utc=datetime(2026, 6, 8, 11, 0, tzinfo=UTC),
        time_mode="range",
    )
    assert format_event_when(ev, user_id=None) == "09:00–19:00"


def test_start_only_renders_start():
    """Сценарий 2: только начало -> 'HH:MM', без конца."""
    # 13:00 Бали = 05:00 UTC
    ev = _bali_event(
        starts_utc=datetime(2026, 6, 8, 5, 0, tzinfo=UTC),
        ends_utc=None,
        time_mode="start",
    )
    assert format_event_when(ev, user_id=None) == "13:00"


def test_range_without_explicit_mode_uses_end():
    """Без time_mode, но с ends_at -> трактуем как диапазон (обратная совместимость)."""
    ev = _bali_event(
        starts_utc=datetime(2026, 6, 8, 1, 0, tzinfo=UTC),
        ends_utc=datetime(2026, 6, 8, 11, 0, tzinfo=UTC),
        time_mode=None,
    )
    assert format_event_when(ev, user_id=None) == "09:00–19:00"


def test_no_start_returns_empty():
    """Нет времени начала -> пустая строка."""
    ev = _bali_event(starts_utc=None)
    assert format_event_when(ev, user_id=None) == ""


def test_all_day_i18n_keys():
    """Метка 'весь день' локализована для RU и EN."""
    assert t("event.all_day", "ru") == "Весь день"
    assert t("event.all_day", "en") == "All day"
