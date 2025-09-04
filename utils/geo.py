#!/usr/bin/env python3
"""
Гео-утилиты для точных расчетов расстояний и фильтрации
"""

from math import atan2, cos, radians, sin, sqrt

EARTH_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Точная дистанция по сфере."""
    rlat1, rlon1, rlat2, rlon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return EARTH_KM * c


def bbox_around(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Грубая рамка вокруг точки для первичного отбора (ускоряет запрос)."""
    lat_delta = radius_km / 110.574  # км в градусах широты
    lon_delta = radius_km / (111.320 * cos(radians(lat)) or 1e-9)
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)


def inside_bbox(lat: float, lon: float, bbox: dict[str, float]) -> bool:
    """Проверяет, находится ли точка внутри bounding box."""
    return (bbox["min_lat"] <= lat <= bbox["max_lat"]) and (
        bbox["min_lon"] <= lon <= bbox["max_lon"]
    )


def find_user_region(lat: float, lon: float, geo_bboxes: dict[str, dict[str, float]]) -> str:
    """Определяет регион пользователя по координатам."""
    for name, bb in geo_bboxes.items():
        if inside_bbox(lat, lon, bb):
            return name
    return "unknown"


def validate_coordinates(lat: float, lon: float) -> bool:
    """Проверяет корректность координат."""
    return -90 <= lat <= 90 and -180 <= lon <= 180
