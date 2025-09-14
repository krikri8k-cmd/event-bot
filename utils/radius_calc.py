"""
Утилиты для расчета расстояний без PostGIS
"""

import math


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Вычисляет расстояние между двумя точками на Земле по формуле Haversine

    Args:
        lat1, lon1: Координаты первой точки
        lat2, lon2: Координаты второй точки

    Returns:
        Расстояние в километрах
    """
    # Радиус Земли в километрах
    R = 6371.0

    # Конвертируем градусы в радианы
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Разности координат
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Формула Haversine
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    # Расстояние
    distance = R * c

    return distance


def is_within_radius(
    user_lat: float, user_lon: float, event_lat: float | None, event_lon: float | None, radius_km: float
) -> tuple[bool, float | None]:
    """
    Проверяет, находится ли событие в радиусе от пользователя

    Args:
        user_lat, user_lon: Координаты пользователя
        event_lat, event_lon: Координаты события (могут быть None)
        radius_km: Радиус в километрах

    Returns:
        Tuple[is_within, distance_km] - находится ли в радиусе и расстояние
    """
    # Если у события нет координат, считаем что оно в радиусе
    if event_lat is None or event_lon is None:
        return True, None

    # Вычисляем расстояние
    distance = haversine_distance(user_lat, user_lon, event_lat, event_lon)

    # Проверяем радиус
    is_within = distance <= radius_km

    return is_within, distance


def filter_events_by_radius(events: list, user_lat: float, user_lon: float, radius_km: float) -> list:
    """
    Фильтрует события по радиусу

    Args:
        events: Список событий с полями lat, lng
        user_lat, user_lon: Координаты пользователя
        radius_km: Радиус в километрах

    Returns:
        Отфильтрованный список событий
    """
    filtered = []

    for event in events:
        # Предполагаем что событие имеет поля lat, lng
        event_lat = getattr(event, "lat", None)
        event_lon = getattr(event, "lng", None)

        is_within, distance = is_within_radius(user_lat, user_lon, event_lat, event_lon, radius_km)

        if is_within:
            # Добавляем расстояние к событию для сортировки
            event.distance_km = distance
            filtered.append(event)

    # Сортируем по расстоянию
    filtered.sort(key=lambda x: x.distance_km or 0)

    return filtered
