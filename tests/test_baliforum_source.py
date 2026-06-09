# tests/test_baliforum_source.py
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup

from event_apis import RawEvent
from sources.baliforum import (
    _determine_time_mode,
    _extract_latlng_from_maps,
    _extract_venue_from_soup,
    _parse_time,
    _ru_date_to_dt,
    merge_tomorrow_baliforum_events,
)


def test_parse_time():
    """Тест парсинга времени"""
    assert _parse_time("09:00") == (9, 0)
    assert _parse_time("21:30") == (21, 30)
    assert _parse_time("invalid") is None


def test_extract_latlng_from_maps():
    """Тест извлечения координат из Google Maps URL"""
    # Формат /@lat,lng
    lat, lng, place_name, maps_url = _extract_latlng_from_maps("https://maps.google.com/@-8.70,115.22,15z")
    assert lat == -8.70
    assert lng == 115.22
    assert place_name is None  # В этом формате нет названия места
    assert maps_url == "https://maps.google.com/@-8.70,115.22,15z"

    # Формат query=lat%2Clng
    lat, lng, place_name, maps_url = _extract_latlng_from_maps("https://maps.google.com/maps?query=-8.70%2C115.22")
    assert lat == -8.70
    assert lng == 115.22
    assert place_name is None  # В этом формате нет названия места
    assert maps_url == "https://maps.google.com/maps?query=-8.70%2C115.22"

    # Формат /place/name/@lat,lng (с названием места)
    lat, lng, place_name, maps_url = _extract_latlng_from_maps(
        "https://www.google.com/maps/place/Canggu+Beach/@-8.70,115.22,15z"
    )
    assert lat == -8.70
    assert lng == 115.22
    assert place_name == "Canggu Beach"  # Название места извлечено
    assert "Canggu+Beach" in maps_url or "Canggu Beach" in maps_url

    # Невалидный URL
    lat, lng, place_name, maps_url = _extract_latlng_from_maps("https://example.com")
    assert lat is None
    assert lng is None
    assert place_name is None
    assert maps_url is None


def test_ru_date_to_dt():
    """Тест парсинга русских дат"""
    tz = ZoneInfo("Asia/Makassar")
    now = datetime(2025, 9, 8, 10, 0, tzinfo=tz)

    # Сегодня с временем
    start, end = _ru_date_to_dt("Сегодня с 09:00 до 21:00", now, tz)
    assert start is not None
    assert end is not None
    assert start.hour == 9
    assert end.hour == 21

    # Завтра
    start, end = _ru_date_to_dt("Завтра с 18:00", now, tz)
    assert start is not None
    assert start.day == 9  # завтра

    # Весь день: жёсткое окно 09:00–21:00 по Бали
    start, end = _ru_date_to_dt("Сегодня весь день", now, tz)
    assert start is not None
    assert end is not None
    assert start.hour == 9
    assert start.minute == 0
    assert end.hour == 21
    assert end.minute == 0

    # Весь день с явной датой ("10 июля весь день")
    start, end = _ru_date_to_dt("10 июля весь день", now, tz)
    assert start is not None and end is not None
    assert start.hour == 9 and end.hour == 21
    assert start.month == 7 and start.day == 10

    # Невалидная дата
    start, end = _ru_date_to_dt("invalid date", now, tz)
    assert start is None
    assert end is None


@pytest.mark.no_db
def test_merge_tomorrow_baliforum_events():
    """Слияние завтра: новые события + без затирания «сегодня»."""
    tz = ZoneInfo("Asia/Makassar")
    now = datetime(2026, 6, 9, 10, 0, tzinfo=tz)
    today_start = datetime(2026, 6, 9, 13, 0, tzinfo=tz)
    tomorrow_start = datetime(2026, 6, 10, 11, 0, tzinfo=tz)

    today_event = RawEvent(
        title="Today event",
        lat=-8.5,
        lng=115.2,
        starts_at=today_start,
        source="baliforum",
        external_id="today-id",
        url="https://baliforum.ru/events/today",
    )
    wrong_date_event = RawEvent(
        title="Wrong date",
        lat=-8.5,
        lng=115.2,
        starts_at=datetime(2026, 6, 12, 11, 0, tzinfo=tz),
        source="baliforum",
        external_id="fix-id",
        url="https://baliforum.ru/events/fix",
    )
    raw_events = [today_event, wrong_date_event]

    tomorrow_events = [
        {
            "title": "Today event",
            "lat": -8.5,
            "lng": 115.2,
            "start_time": tomorrow_start,
            "url": "https://baliforum.ru/events/today",
            "external_id": "today-id",
            "venue": "Should not apply",
            "raw": {"date_text": "Завтра с 11:00"},
        },
        {
            "title": "Wrong date",
            "lat": -8.5,
            "lng": 115.2,
            "start_time": tomorrow_start,
            "end_time": datetime(2026, 6, 10, 13, 0, tzinfo=tz),
            "time_mode": "range",
            "url": "https://baliforum.ru/events/fix",
            "external_id": "fix-id",
            "venue": "Plant Bistro",
            "raw": {"date_text": "10 июня с 11:00 до 13:00"},
        },
        {
            "title": "Only tomorrow page",
            "lat": -8.6,
            "lng": 115.1,
            "start_time": tomorrow_start,
            "url": "https://baliforum.ru/events/new",
            "external_id": "new-id",
            "venue": "New venue",
            "raw": {"date_text": "Завтра с 11:00"},
        },
        {
            "title": "Multi-day festival",
            "lat": -8.55,
            "lng": 115.15,
            "start_time": tomorrow_start,
            "end_time": datetime(2026, 6, 10, 22, 30, tzinfo=tz),
            "time_mode": "range",
            "url": "https://baliforum.ru/events/festival",
            "external_id": "festival-id",
            "venue": "Labyrinth Dome",
            "raw": {"date_text": "10 июнь, с 10:30 до 22:30"},
        },
    ]

    today_festival = RawEvent(
        title="Multi-day festival",
        lat=-8.55,
        lng=115.15,
        starts_at=today_start,
        source="baliforum",
        external_id="festival-id",
        url="https://baliforum.ru/events/festival",
    )
    raw_events.append(today_festival)

    merged, added, skipped, updated = merge_tomorrow_baliforum_events(raw_events, tomorrow_events, now=now)
    assert len(merged) == 5
    assert added == 2
    assert skipped == 1
    assert updated == 1
    assert today_event.starts_at == today_start
    assert wrong_date_event.starts_at == tomorrow_start
    assert wrong_date_event._raw_data["venue"] == "Plant Bistro"  # type: ignore[attr-defined]
    tomorrow_occurrence = next(e for e in merged if e.external_id == "festival-id#2026-06-10")
    assert tomorrow_occurrence.starts_at == tomorrow_start


@pytest.mark.no_db
def test_extract_venue_from_soup():
    """Название места с детальной страницы BaliForum (dd.event__place)."""
    html = """
    <dl>
      <dt>Место</dt>
      <dd class="event__place">Чангу • <a href="/places/milu">Milu by Nook</a></dd>
    </dl>
    """
    venue = _extract_venue_from_soup(BeautifulSoup(html, "html.parser"))
    assert venue == "Milu by Nook"

    html_plain = '<dd class="event__place">Убуд • Pison Ubud</dd>'
    assert _extract_venue_from_soup(BeautifulSoup(html_plain, "html.parser")) == "Pison Ubud"


def test_determine_time_mode():
    """Режим времени: all_day / range / start."""
    assert _determine_time_mode("Сегодня весь день", has_end=False) == "all_day"
    assert _determine_time_mode("10 июля весь день", has_end=True) == "all_day"
    assert _determine_time_mode("Сегодня с 09:00 до 19:00", has_end=True) == "range"
    assert _determine_time_mode("Сегодня в 13:00", has_end=False) == "start"
    assert _determine_time_mode("", has_end=False) == "start"
    assert _determine_time_mode(None, has_end=False) == "start"
