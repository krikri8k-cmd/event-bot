"""PR2: telegram ingest LLM validation, time_mode, geo helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from utils.telegram_event_extractor import (
    compute_time_mode,
    validate_extracted_event,
)
from utils.telegram_geo_resolver import _normalize_place_name

pytestmark = pytest.mark.no_db

TZ = "Asia/Makassar"


def _base_payload(**overrides):
    data = {
        "is_event": True,
        "confidence": 0.95,
        "title": "Sunset Party",
        "description": "Первая строка про вечеринку. Вторая строка с деталями.",
        "title_en": "Sunset Party",
        "description_en": "First sentence about the party. Second sentence with details.",
        "starts_at": "2026-06-20T19:00:00+08:00",
        "ends_at": None,
        "location_name": "Savaya Bali",
        "categories": ["Вечеринка"],
        "external_registration_url": None,
        "extracted_contact": "@host",
        "is_all_day": False,
    }
    data.update(overrides)
    return data


def test_validate_rejects_not_event():
    result = validate_extracted_event(_base_payload(is_event=False), timezone=TZ)
    assert not result.ok
    assert result.reject_reason == "not_an_event"


def test_validate_rejects_low_confidence():
    result = validate_extracted_event(_base_payload(confidence=0.5), timezone=TZ)
    assert not result.ok
    assert result.reject_reason == "low_confidence"


def test_validate_rejects_old_starts_at():
    now = datetime(2026, 6, 12, 12, 0, tzinfo=ZoneInfo(TZ))
    result = validate_extracted_event(
        _base_payload(starts_at="2026-06-01T19:00:00+08:00"),
        timezone=TZ,
        now=now,
    )
    assert not result.ok
    assert result.reject_reason == "starts_at_too_old"


def test_validate_all_day_sets_bali_window():
    now = datetime(2026, 6, 12, 12, 0, tzinfo=ZoneInfo(TZ))
    result = validate_extracted_event(
        _base_payload(is_all_day=True, starts_at="2026-06-20T12:00:00+08:00"),
        timezone=TZ,
        now=now,
        raw_text="Фестиваль, весь день на пляже",
    )
    assert result.ok
    assert result.data["starts_at_dt"].hour == 9
    assert result.data["ends_at_dt"].hour == 21


def test_compute_time_mode():
    tz = ZoneInfo(TZ)
    start = datetime(2026, 6, 20, 19, 0, tzinfo=tz)
    end = datetime(2026, 6, 20, 23, 0, tzinfo=tz)
    assert compute_time_mode(start, end, False) == "range"
    assert compute_time_mode(start, None, False) == "start"
    assert compute_time_mode(start, end, True) == "all_day"


def test_normalize_place_name():
    assert _normalize_place_name("  Savaya   Bali  ") == "Savaya Bali"
