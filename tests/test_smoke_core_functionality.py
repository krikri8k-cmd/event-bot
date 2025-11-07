#!/usr/bin/env python3
"""Smoke tests для ключевой функциональности бота"""

from datetime import datetime

import pytest
import pytz


# Smoke test 1: Поиск событий
def test_search_events_today():
    """Тест поиска событий на сегодня"""
    from config import load_settings
    from database import get_engine, init_engine
    from utils.unified_events_service import UnifiedEventsService

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()
    service = UnifiedEventsService(engine)

    # Тестируем поиск для Бали
    events = service.search_events_today(city="bali", user_lat=-8.674763, user_lng=115.230137, radius_km=15)

    # Проверяем что результат корректный
    assert isinstance(events, list)

    # Если есть события, проверяем структуру
    if events:
        event = events[0]
        assert "title" in event
        assert "starts_at" in event
        assert "lat" in event
        assert "lng" in event
        assert "city" in event


# Smoke test 2: Форматирование времени
def test_time_formatting():
    """Тест форматирования времени в карточках"""
    from bot_enhanced_v3 import human_when

    # Тест с валидным временем
    event_with_time = {"starts_at": datetime(2025, 9, 18, 10, 30, tzinfo=pytz.UTC), "city": "bali"}

    result = human_when(event_with_time, "bali")
    assert result == "18:30"  # 10:30 UTC = 18:30 Bali

    # Тест без времени
    event_no_time = {"starts_at": None, "city": "bali"}

    result = human_when(event_no_time, "bali")
    assert result == ""


# Smoke test 3: Расчет расстояния
def test_distance_calculation():
    """Тест расчета расстояния между координатами"""
    from utils.geo_utils import haversine_km

    # Тест с известными координатами
    lat1, lng1 = -8.674763, 115.230137  # Пользователь
    lat2, lng2 = -8.6796117, 115.2304151  # Событие

    distance = haversine_km(lat1, lng1, lat2, lng2)

    # Расстояние должно быть около 0.5 км
    assert 0.4 <= distance <= 0.6


# Smoke test 4: Парсинг времени BaliForum
def test_baliforum_time_parsing():
    """Тест парсинга времени из BaliForum"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sources.baliforum import _ru_date_to_dt

    tz = ZoneInfo("Asia/Makassar")
    now = datetime.now(tz)

    # Тест различных форматов
    test_cases = [
        ("Сегодня в 19:00", True),
        ("Завтра в 19:00", True),  # проверяем что "завтра" тоже парсится
        ("19.09 в 14:00", True),
        ("19 сентября в 20:00", True),
        ("10:00", False),  # только время без даты - НЕ должно парситься (может быть завтра)
        ("", False),  # пустая строка
    ]

    for time_str, should_parse in test_cases:
        start, end = _ru_date_to_dt(time_str, now, tz)

        if should_parse:
            assert start is not None, f"Не удалось распарсить: '{time_str}'"
            assert isinstance(start, datetime)
        else:
            assert start is None, f"Не должно парситься: '{time_str}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
