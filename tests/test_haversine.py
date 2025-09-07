"""
Тесты для функции haversine_km
"""

import os
import sys

import pytest

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.geo_utils import haversine_km


class TestHaversine:
    """Тесты для функции haversine_km"""

    def test_zero_distance(self):
        """Тест: нулевое расстояние - точка к себе = 0 км"""
        p = (-8.65, 115.22)  # Бали, пример координат
        assert haversine_km(p[0], p[1], p[0], p[1]) == pytest.approx(0.0, rel=1e-6)

    def test_known_distance_small(self):
        """Тест: малое расстояние - две точки в Убуде (примерно 2.5 км друг от друга)"""
        # Две точки в Убуде (примерно 2.5 км друг от друга)
        p1 = (-8.509, 115.262)
        p2 = (-8.521, 115.282)
        d = haversine_km(p1[0], p1[1], p2[0], p2[1])
        assert d == pytest.approx(2.57, rel=0.1)  # 2.57 ±10%

    def test_known_distance_medium(self):
        """Тест: среднее расстояние - Кута (Бали) → Убуд ≈ 27 км"""
        # Кута (Бали) → Убуд ≈ 27 км
        kuta = (-8.717, 115.168)
        ubud = (-8.507, 115.263)
        d = haversine_km(kuta[0], kuta[1], ubud[0], ubud[1])
        assert d == pytest.approx(27.0, rel=0.2)

    def test_known_distance_large(self):
        """Тест: большое расстояние - Джакарта → Бали ≈ 960 км"""
        # Джакарта → Бали ≈ 960 км
        jakarta = (-6.2088, 106.8456)
        bali = (-8.65, 115.22)
        d = haversine_km(jakarta[0], jakarta[1], bali[0], bali[1])
        assert d == pytest.approx(960.0, rel=0.1)

    def test_symmetry(self):
        """Тест: симметричность - расстояние A→B = B→A"""
        p1 = (-8.67, 115.25)
        p2 = (-8.60, 115.20)
        d1 = haversine_km(p1[0], p1[1], p2[0], p2[1])
        d2 = haversine_km(p2[0], p2[1], p1[0], p1[1])
        assert d1 == pytest.approx(d2, rel=1e-6)

    def test_edge_cases(self):
        """Тест: граничные случаи"""
        # Одинаковые координаты
        assert haversine_km(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0, rel=1e-6)

        # Противоположные точки на экваторе
        d = haversine_km(0.0, 0.0, 0.0, 180.0)
        assert d == pytest.approx(20015.0, rel=0.1)  # половина окружности Земли

        # Северный и южный полюс
        d = haversine_km(90.0, 0.0, -90.0, 0.0)
        assert d == pytest.approx(20015.0, rel=0.1)  # половина окружности Земли
