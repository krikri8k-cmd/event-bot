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
