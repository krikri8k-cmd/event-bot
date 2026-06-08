# tests/test_baliforum_source.py
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from sources.baliforum import (
    _determine_time_mode,
    _extract_latlng_from_maps,
    _extract_venue_from_soup,
    _parse_time,
    _ru_date_to_dt,
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
