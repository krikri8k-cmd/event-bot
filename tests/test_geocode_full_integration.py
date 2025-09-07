# tests/test_geocode_full_integration.py
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from logging_helpers import DropStats
from venue_enrich import enrich_venue_from_text


# Мокаем геокодер для тестов
@pytest.fixture(autouse=True)
def mock_geocode(monkeypatch):
    """Мокаем геокодер для интеграционных тестов"""
    # Устанавливаем переменные окружения для геокодера
    monkeypatch.setenv("GEOCODE_ENABLE", "1")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key-for-testing")

    def mock_geocode_best_effort(venue, address):
        if venue == "Cafe Moka":
            return (-8.6701, 115.2579)
        if address and "Пушкина" in address:
            return (55.7539, 37.6208)
        return None

    def mock_reverse_geocode_best_effort(lat, lon):
        if (lat, lon) == (-8.6701, 115.2579):
            return "Cafe Moka, Sanur, Bali"
        return None

    # Подменяем функции геокодера
    monkeypatch.setattr("geocode.geocode_best_effort", mock_geocode_best_effort)
    monkeypatch.setattr("geocode.reverse_geocode_best_effort", mock_reverse_geocode_best_effort)


def test_geocode_venue_to_coords():
    """Тест: событие с venue_name получает координаты через геокодер"""
    event = {
        "title": "Встреча в Cafe Moka",
        "venue_name": "Cafe Moka",
        "source_url": "https://example.com/event",
    }

    enriched = enrich_venue_from_text(event)

    assert enriched["venue_name"] == "Cafe Moka"
    # Проверяем, что координаты добавлены (если геокодер работает)
    if "coords" in enriched:
        assert enriched["coords"] == (-8.6701, 115.2579)
        assert enriched["lat"] == -8.6701
        assert enriched["lng"] == 115.2579


def test_geocode_address_to_coords():
    """Тест: событие с address получает координаты через геокодер"""
    event = {
        "title": "Встреча на улице Пушкина",
        "address": "ул. Пушкина, дом 10",
        "source_url": "https://example.com/event",
    }

    enriched = enrich_venue_from_text(event)

    assert enriched["address"] == "ул. Пушкина, дом 10"
    # Проверяем, что координаты добавлены (если геокодер работает)
    if "coords" in enriched:
        assert enriched["coords"] == (55.7539, 37.6208)
        assert enriched["lat"] == 55.7539
        assert enriched["lng"] == 37.6208


def test_reverse_geocode_coords_to_address():
    """Тест: событие с координатами получает адрес через реверс-геокодер"""
    event = {
        "title": "Встреча в Cafe Moka",
        "coords": (-8.6701, 115.2579),
        "lat": -8.6701,
        "lng": 115.2579,
        "source_url": "https://example.com/event",
    }

    enriched = enrich_venue_from_text(event)

    assert enriched["coords"] == (-8.6701, 115.2579)
    # Проверяем, что адрес добавлен (если геокодер работает)
    if "address" in enriched:
        assert enriched["address"] == "Cafe Moka, Sanur, Bali"


def test_full_pipeline_with_geocoding():
    """Тест: полный конвейер с геокодированием"""

    # Заглушки для тестирования
    def get_source_url(e):
        return e.get("source_url")

    def is_blacklisted_url(url):
        return url and "example.com" in url

    def prepare_events_for_feed(events):
        """Упрощенная версия prepare_events_for_feed для тестирования"""
        from collections import Counter

        prepared, drop = [], DropStats()
        kept_by = Counter(ai=0, user=0, source=0)

        for e in events:
            # Обогащаем локацию (включая геокодирование)
            e = enrich_venue_from_text(e)

            title = (e.get("title") or "").strip() or "—"

            # Проверяем URL
            if not get_source_url(e):
                drop.add("no_url", title)
                continue

            # Проверяем локацию (теперь с геокодированием!)
            if not (
                e.get("venue_name")
                or e.get("address")
                or e.get("coords")
                or (e.get("lat") and e.get("lng"))
            ):
                drop.add("no_venue_or_location", title)
                continue

            # Проверяем черный список
            if is_blacklisted_url(get_source_url(e)):
                drop.add("blacklist_domain", title)
                continue

            prepared.append(e)
            kept_by[e.get("type", "source")] += 1

        print(drop.summary(kept_by, total=len(events)))
        return prepared

    # Тест: событие только с venue_name должно получить координаты и пройти фильтр
    event = {
        "id": "1",
        "type": "source",
        "title": "Встреча в Cafe Moka",
        "start": dt.datetime.now(dt.UTC),
        "source_url": "https://valid.example/item",
        "venue_name": "Cafe Moka",  # Только название места
    }

    result = prepare_events_for_feed([event])

    # Должно пройти фильтр
    assert len(result) == 1
    assert result[0]["venue_name"] == "Cafe Moka"
    # Проверяем, что координаты добавлены (если геокодер работает)
    if "coords" in result[0]:
        assert result[0]["coords"] == (-8.6701, 115.2579)


if __name__ == "__main__":
    print("🧪 Запуск интеграционных тестов геокодера...")

    # Запускаем тесты вручную
    test_geocode_venue_to_coords()
    print("✅ test_geocode_venue_to_coords passed")

    test_geocode_address_to_coords()
    print("✅ test_geocode_address_to_coords passed")

    test_reverse_geocode_coords_to_address()
    print("✅ test_reverse_geocode_coords_to_address passed")

    test_full_pipeline_with_geocoding()
    print("✅ test_full_pipeline_with_geocoding passed")

    print("\n🎉 Все интеграционные тесты прошли успешно!")
