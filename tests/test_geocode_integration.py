# tests/test_geocode_integration.py
import pytest

# Мокаем наш модуль geocode (без внешнего HTTP)
import geocode as geo


@pytest.fixture(autouse=True)
def mock_gmaps(monkeypatch):
    # Подделываем клиента и ответы .geocode/.reverse_geocode
    class FakeGMaps:
        def __init__(self):
            pass

        def geocode(self, q):
            if "Cafe Moka" in q:
                return [{"geometry": {"location": {"lat": -8.6701, "lng": 115.2579}}}]
            if "улица Пушкина" in q:
                return [{"geometry": {"location": {"lat": 55.7539, "lng": 37.6208}}}]
            return []

        def reverse_geocode(self, latlng):
            (lat, lon) = latlng
            if (lat, lon) == (-8.6701, 115.2579):
                return [{"formatted_address": "Cafe Moka, Sanur"}]
            return []

    # Включаем флаги геокодера и подменяем клиент
    monkeypatch.setenv("GEOCODE_ENABLE", "1")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-key")
    # сбросить приватные синглтоны
    geo._gmaps = FakeGMaps()
    monkeypatch.setattr(geo, "_client", lambda: geo._gmaps, raising=True)
    # обнулим кэш
    geo._cache.clear()


def test_geocode_by_venue_then_cache():
    latlng = geo.geocode_best_effort("Cafe Moka", None)
    assert latlng == (-8.6701, 115.2579)

    # повтор должен идти из кэша, без вызова API
    latlng2 = geo.geocode_best_effort("Cafe Moka", None)
    assert latlng2 == (-8.6701, 115.2579)


def test_geocode_by_address():
    latlng = geo.geocode_best_effort(None, "улица Пушкина, дом 10")
    assert latlng == (55.7539, 37.6208)


def test_reverse_geocode_best_effort():
    addr = geo.reverse_geocode_best_effort(-8.6701, 115.2579)
    assert addr == "Cafe Moka, Sanur"
