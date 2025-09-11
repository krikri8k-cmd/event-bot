# tests/test_baliforum_source.py
from datetime import datetime
from zoneinfo import ZoneInfo

from sources.baliforum import _extract_latlng_from_maps, _parse_time, _ru_date_to_dt


def test_parse_time():
    """Тест парсинга времени"""
    assert _parse_time("09:00") == (9, 0)
    assert _parse_time("21:30") == (21, 30)
    assert _parse_time("invalid") is None


def test_extract_latlng_from_maps():
    """Тест извлечения координат из Google Maps URL"""
    # Формат /@lat,lng
    lat, lng = _extract_latlng_from_maps("https://maps.google.com/@-8.70,115.22,15z")
    assert lat == -8.70
    assert lng == 115.22

    # Формат query=lat%2Clng
    lat, lng = _extract_latlng_from_maps("https://maps.google.com/maps?query=-8.70%2C115.22")
    assert lat == -8.70
    assert lng == 115.22

    # Невалидный URL
    lat, lng = _extract_latlng_from_maps("https://example.com")
    assert lat is None
    assert lng is None


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

    # Весь день
    start, end = _ru_date_to_dt("Сегодня весь день", now, tz)
    assert start is not None
    assert end is not None

    # Невалидная дата
    start, end = _ru_date_to_dt("invalid date", now, tz)
    assert start is None
    assert end is None
