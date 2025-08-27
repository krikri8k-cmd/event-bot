import os
from datetime import datetime, timedelta

import pytest

# В лёгком CI все тесты файла скипаем целиком
if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping API tests in light CI", allow_module_level=True)

# Доп. защита: если кто-то запустил full без пакетов
pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed")

from sqlalchemy import text

# В лёгком CI все тесты файла скипаем целиком
if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping API tests in light CI", allow_module_level=True)

# Доп. защита: если кто-то запустил full без пакетов
pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed")


pytestmark = pytest.mark.api  # удобно фильтровать в CI


def seed(api_engine, title, lat, lng, starts_at=None):
    with api_engine.begin() as c:
        c.execute(
            text("INSERT INTO events (title, lat, lng, starts_at) VALUES (:t, :lat, :lng, :ts)"),
            {
                "t": title,
                "lat": float(lat),
                "lng": float(lng),
                "ts": starts_at or (datetime.now(datetime.UTC) + timedelta(hours=2)),
            },
        )


def test_nearby_returns_seeded_event(api_client, api_engine):
    # Пример: Бали; подстрой координаты при необходимости
    seed(api_engine, "Sunset Meetup", -8.6500, 115.2167)

    r = api_client.get(
        "/events/nearby",
        params={"lat": -8.6501, "lng": 115.2166, "radius_km": 5},
    )
    assert r.status_code == 200
    titles = [e.get("title") for e in r.json()]
    assert "Sunset Meetup" in titles


def test_nearby_filters_by_radius(api_client, api_engine):
    seed(api_engine, "Far Event", -8.7000, 115.3000)  # далеко за 5км

    r = api_client.get(
        "/events/nearby",
        params={"lat": -8.6501, "lng": 115.2166, "radius_km": 3},
    )
    assert r.status_code == 200
    assert all(e.get("title") != "Far Event" for e in r.json())


def test_nearby_returns_distance_km(api_client, api_engine):
    """Проверяем, что в ответе есть distance_km и он ≤ radius_km"""
    seed(api_engine, "Near Event", -8.6500, 115.2167)

    r = api_client.get(
        "/events/nearby",
        params={"lat": -8.6501, "lng": 115.2166, "radius_km": 5},
    )
    assert r.status_code == 200
    events = r.json()
    assert len(events) > 0

    for event in events:
        assert "distance_km" in event
        assert isinstance(event["distance_km"], int | float)
        assert event["distance_km"] <= 5  # radius_km
        assert event["distance_km"] >= 0


def test_nearby_pagination(api_client, api_engine):
    """Тестируем пагинацию: засеиваем 4 события, проверяем limit=2, offset=0 и offset=2"""
    # Засеиваем 4 события рядом
    events_data = [
        ("Event 1", -8.6500, 115.2167),
        ("Event 2", -8.6501, 115.2168),
        ("Event 3", -8.6502, 115.2169),
        ("Event 4", -8.6503, 115.2170),
    ]

    for title, lat, lng in events_data:
        seed(api_engine, title, lat, lng)

    # Первая страница: limit=2, offset=0
    r1 = api_client.get(
        "/events/nearby",
        params={"lat": -8.6501, "lng": 115.2166, "radius_km": 5, "limit": 2, "offset": 0},
    )
    assert r1.status_code == 200
    events1 = r1.json()
    assert len(events1) == 2

    # Вторая страница: limit=2, offset=2
    r2 = api_client.get(
        "/events/nearby",
        params={"lat": -8.6501, "lng": 115.2166, "radius_km": 5, "limit": 2, "offset": 2},
    )
    assert r2.status_code == 200
    events2 = r2.json()
    assert len(events2) == 2

    # Проверяем, что события разные
    titles1 = {e["title"] for e in events1}
    titles2 = {e["title"] for e in events2}
    assert titles1.isdisjoint(titles2), "Страницы не должны пересекаться"

    # Проверяем сортировку по distance_km
    for events in [events1, events2]:
        distances = [e["distance_km"] for e in events]
        assert distances == sorted(distances), "События должны быть отсортированы по расстоянию"
