#!/usr/bin/env python3
"""
Тесты для гео-фильтрации
"""

import pytest

from utils.geo_utils import bbox_around, haversine_km, inside_bbox


def test_haversine_zero():
    """Тест: расстояние до самой себя равно 0"""
    assert haversine_km(-8.7, 115.2, -8.7, 115.2) < 0.001


def test_haversine_known_distance():
    """Тест: известное расстояние между точками"""
    # Кута и Денпасар (примерно 9.4 км)
    distance = haversine_km(-8.7237, 115.1752, -8.6500, 115.2167)
    assert 9.0 <= distance <= 10.0


def test_bbox_contains_center():
    """Тест: bbox содержит центральную точку"""
    bb = bbox_around(-8.7, 115.2, 5)
    assert bb[0] < -8.7 < bb[1]  # lat в пределах
    assert bb[2] < 115.2 < bb[3]  # lon в пределах


def test_bbox_size():
    """Тест: размер bbox соответствует радиусу"""
    lat, lon = -8.7, 115.2
    radius_km = 10
    bb = bbox_around(lat, lon, radius_km)

    lat_delta = bb[1] - bb[0]
    lon_delta = bb[3] - bb[2]

    # Примерные размеры (грубая проверка)
    assert 0.15 <= lat_delta <= 0.25  # примерно 0.18 градуса для 10 км
    assert 0.15 <= lon_delta <= 0.25


def test_inside_bbox_bali():
    """Тест: точки внутри bounding box Бали"""
    bb = {"min_lat": -8.9, "max_lat": -8.1, "min_lon": 114.4, "max_lon": 115.9}

    # Точки внутри Бали
    assert inside_bbox(-8.7, 115.2, bb)  # Кута
    assert inside_bbox(-8.5, 115.3, bb)  # Денпасар
    assert inside_bbox(-8.3, 115.1, bb)  # Убуд

    # Точки вне Бали
    assert not inside_bbox(-6.2, 106.8, bb)  # Джакарта
    assert not inside_bbox(-7.8, 110.4, bb)  # Джокьякарта
    assert not inside_bbox(1.3, 103.8, bb)  # Сингапур


def test_inside_bbox_edge_cases():
    """Тест: граничные случаи"""
    bb = {"min_lat": -8.9, "max_lat": -8.1, "min_lon": 114.4, "max_lon": 115.9}

    # Граничные точки
    assert inside_bbox(-8.9, 114.4, bb)  # min_lat, min_lon
    assert inside_bbox(-8.1, 115.9, bb)  # max_lat, max_lon

    # Точки за границами
    assert not inside_bbox(-9.0, 114.4, bb)  # ниже min_lat
    assert not inside_bbox(-8.9, 114.3, bb)  # левее min_lon
    assert not inside_bbox(-8.0, 115.9, bb)  # выше max_lat
    assert not inside_bbox(-8.1, 116.0, bb)  # правее max_lon


def test_haversine_symmetry():
    """Тест: симметричность функции расстояния"""
    lat1, lon1 = -8.7, 115.2
    lat2, lon2 = -8.5, 115.3

    d1 = haversine_km(lat1, lon1, lat2, lon2)
    d2 = haversine_km(lat2, lon2, lat1, lon1)

    assert abs(d1 - d2) < 0.001


if __name__ == "__main__":
    pytest.main([__file__])
