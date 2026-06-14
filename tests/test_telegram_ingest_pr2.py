"""PR2: telegram ingest LLM validation, time_mode, geo helpers."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from utils.telegram_event_extractor import (
    compute_time_mode,
    validate_extracted_event,
)
from utils.telegram_geo_resolver import (
    _find_maps_url,
    _geocode_queries,
    _is_maps_url,
    _normalize_place_name,
    collect_maps_url_candidates,
    pick_best_maps_url,
)

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


def test_geocode_queries_cinema_variants():
    queries = _geocode_queries("IMAX в ICON", "bali")
    assert "IMAX в ICON cinema, Bali, Indonesia" in queries
    assert "Cinema IMAX ICON, Bali, Indonesia" in queries


def test_pick_best_maps_url_prefers_cinema_entity_link():
    raw = (
        "Балийцы - го в кино!\n"
        "Иду сегодня на 21:15 в IMAX в ICON на Спилберга\n"
        "Кино здесь:\n\n"
        "Перед кино - ужин здесь:\n"
        "Пицца у них - шикарная"
    )
    cinema_url = "https://maps.app.goo.gl/F65wLhwR5CTzKCvd6"
    dinner_url = "https://maps.app.goo.gl/DinnerPlace123"
    candidates = collect_maps_url_candidates(
        location_name="IMAX в ICON",
        raw_text=raw,
        entity_links=[(cinema_url, "Кино здесь"), (dinner_url, "здесь")],
    )
    assert pick_best_maps_url(candidates, raw_text=raw) == cinema_url


def test_pick_best_maps_url_entity_links_before_plain_text():
    raw = "Встречаемся тут"
    entity_url = "https://maps.app.goo.gl/EntityFirst"
    text_url = "https://maps.app.goo.gl/TextSecond"
    raw_with_text = f"{raw} {text_url}"
    candidates = collect_maps_url_candidates(
        location_name=None,
        raw_text=raw_with_text,
        entity_links=[(entity_url, "тут")],
    )
    assert pick_best_maps_url(candidates, raw_text=raw_with_text) == entity_url


def test_export_message_link_channels_import():
    from telethon.tl.functions.channels import ExportMessageLinkRequest

    assert ExportMessageLinkRequest.__name__ == "ExportMessageLinkRequest"


def test_extract_message_entity_links_text_url():
    from utils.telegram_telethon_helpers import extract_message_entity_links

    class FakeEntity:
        def __init__(self, offset, length, url=None):
            self.offset = offset
            self.length = length
            self.url = url

    class FakeMessage:
        message = "Кино здесь: ужин здесь:"
        entities = []

    try:
        from telethon.tl.types import MessageEntityTextUrl
    except ImportError:
        pytest.skip("telethon not installed")

    msg = FakeMessage()
    msg.entities = [
        MessageEntityTextUrl(offset=0, length=11, url="https://maps.app.goo.gl/Cinema"),
        MessageEntityTextUrl(offset=12, length=11, url="https://maps.app.goo.gl/Dinner"),
    ]
    links = extract_message_entity_links(msg)
    assert links == [
        ("https://maps.app.goo.gl/Cinema", "Кино здесь:"),
        ("https://maps.app.goo.gl/Dinner", "ужин здесь:"),
    ]


def test_resolve_organizer_priority():
    from utils.telegram_ingest_pipeline import _resolve_organizer

    username, uid = _resolve_organizer(
        extracted_contact="@from_post",
        poster_username="poster",
        poster_id=123,
    )
    assert username == "from_post"
    assert uid == 123

    username, uid = _resolve_organizer(
        extracted_contact=None,
        poster_username="poster",
        poster_id=456,
    )
    assert username == "poster"
    assert uid == 456

    username, uid = _resolve_organizer(
        extracted_contact=None,
        poster_username=None,
        poster_id=None,
    )
    assert username is None
    assert uid is None


def test_actionable_contact_and_source():
    from utils.telegram_ingest_pipeline import (
        _has_actionable_contact,
        _has_actionable_source,
    )
    from utils.telegram_sources_service import TelegramSource

    assert _has_actionable_contact("host", None) is True
    assert _has_actionable_contact(None, 12345) is True
    assert _has_actionable_contact(None, None) is False

    public_source = TelegramSource(
        id=1,
        chat_id=-1001,
        username="publicchan",
        title="Public",
        is_active=True,
        trust_level="moderated",
        default_city="bali",
        default_country="ID",
        timezone=TZ,
        allow_default_coords=False,
        default_lat=None,
        default_lng=None,
        default_contact=None,
        default_categories=[],
        partner_id=None,
        last_processed_message_id=None,
    )
    private_source = TelegramSource(
        id=2,
        chat_id=-5179811176,
        username=None,
        title="Ingest test",
        is_active=True,
        trust_level="moderated",
        default_city="bali",
        default_country="ID",
        timezone=TZ,
        allow_default_coords=False,
        default_lat=None,
        default_lng=None,
        default_contact=None,
        default_categories=[],
        partner_id=None,
        last_processed_message_id=None,
    )

    assert (
        _has_actionable_source(
            public_source,
            "https://t.me/publicchan/42",
            None,
        )
        is True
    )
    assert (
        _has_actionable_source(
            private_source,
            "https://t.me/c/5179811176/42",
            None,
        )
        is False
    )
    assert (
        _has_actionable_source(
            private_source,
            None,
            "https://example.com/register",
        )
        is True
    )


def test_format_when_shows_utc_and_local():
    from datetime import datetime

    from utils.telegram_moderation_service import _format_when

    when = _format_when(
        {"starts_at": datetime(2026, 6, 12, 11, 0, tzinfo=UTC), "ends_at": None},
        "Asia/Makassar",
    )
    assert "UTC 11:00" in when
    assert "Asia/Makassar 19:00" in when


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
