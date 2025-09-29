"""
Тесты для синхронизации Meetup событий
"""

import pytest

pytestmark = pytest.mark.api

# Отключаем Meetup тесты - используем только BaliForum + KudaGo + пользовательские события
pytest.skip("Meetup integration disabled - using simplified architecture", allow_module_level=True)


def test_sync_meetup_smoke(api_client, api_engine, db_clean):
    """Smoke тест: вызываем /events/sources/meetup/sync и проверяем ответ"""

    # Тестовые координаты (Бали, Индонезия)
    lat, lng = -8.6501, 115.2166

    # Вызываем синк
    response = api_client.post("/events/sources/meetup/sync", params={"lat": lat, "lng": lng, "radius_km": 5.0})

    # Проверяем статус и структуру ответа
    assert response.status_code == 200
    data = response.json()

    # Должен быть ключ "inserted"
    assert "inserted" in data
    assert isinstance(data["inserted"], int)
    assert data["inserted"] >= 0

    # Если есть ошибка, она должна быть в ключе "error"
    if "error" in data:
        assert isinstance(data["error"], str)


def test_sync_meetup_then_nearby(api_client, api_engine, db_clean):
    """Тест: синкаем Meetup события, затем проверяем /events/nearby"""

    # Тестовые координаты
    lat, lng = -8.6501, 115.2166

    # Сначала синкаем события
    sync_response = api_client.post("/events/sources/meetup/sync", params={"lat": lat, "lng": lng, "radius_km": 5.0})
    assert sync_response.status_code == 200

    # Затем ищем события поблизости
    nearby_response = api_client.get("/events/nearby", params={"lat": lat, "lng": lng, "radius_km": 5.0})
    assert nearby_response.status_code == 200

    data = nearby_response.json()
    events = data["items"]

    # Проверяем структуру событий
    if events:  # Если есть события
        for event in events:
            assert "id" in event
            assert "title" in event
            assert "lat" in event
            assert "lng" in event
            assert "distance_km" in event
            assert isinstance(event["distance_km"], int | float)
            assert event["distance_km"] <= 5.0  # В пределах радиуса


def test_sync_meetup_boundary_5km(api_client, api_engine, db_clean):
    """Пограничный тест: проверяем что события ровно на 5 км включаются"""

    # Тестовые координаты
    lat, lng = -8.6501, 115.2166

    # Синкаем события с радиусом 5 км
    sync_response = api_client.post("/events/sources/meetup/sync", params={"lat": lat, "lng": lng, "radius_km": 5.0})
    assert sync_response.status_code == 200

    # Ищем события с радиусом 5 км
    nearby_response = api_client.get("/events/nearby", params={"lat": lat, "lng": lng, "radius_km": 5.0})
    assert nearby_response.status_code == 200

    data = nearby_response.json()
    events = data["items"]

    # Проверяем что все события в пределах 5 км
    for event in events:
        distance = event["distance_km"]
        assert distance <= 5.0, f"Событие {event['title']} на расстоянии {distance} км превышает радиус 5 км"

    # Проверяем сортировку по расстоянию
    distances = [event["distance_km"] for event in events]
    assert distances == sorted(distances), "События должны быть отсортированы по расстоянию"
