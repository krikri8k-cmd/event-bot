"""PR2: telegram ingest LLM validation, time_mode, geo helpers."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from utils.telegram_event_extractor import (
    compute_time_mode,
    validate_extracted_event,
)
from utils.telegram_geo_resolver import _find_maps_url, _geocode_queries, _is_maps_url, _normalize_place_name

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
    assert _normalize_place_name("@ Savaya Bali") == "Savaya Bali"


def test_geocode_queries_bali():
    queries = _geocode_queries("Savaya Bali", "bali")
    assert "Savaya Bali, Bali, Indonesia" in queries


def test_find_maps_url_in_text():
    text = "Party @ https://maps.app.goo.gl/B8LGdDhiAcesEUxi6\n12 июня"
    assert _find_maps_url(text) == "https://maps.app.goo.gl/B8LGdDhiAcesEUxi6"
    assert _is_maps_url("https://maps.app.goo.gl/abc")


def test_build_moderation_card():
    from utils.telegram_moderation_service import build_moderation_card_text

    card = build_moderation_card_text(
        {
            "id": 42,
            "title": "Test Party",
            "title_en": "Test Party",
            "description": "Desc one. Desc two.",
            "description_en": "En one. En two.",
            "starts_at": None,
            "ends_at": None,
            "location_name": "Savaya",
            "lat": -8.84,
            "lng": 115.14,
            "community_name": "Ingest test",
            "url": None,
        },
        source_chat_id=-5179811176,
        message_id=99,
    )
    assert "Test Party" in card
    assert "42" in card
    assert "🇷🇺" in card
    assert "🇬🇧" in card
