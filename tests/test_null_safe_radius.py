#!/usr/bin/env python3
"""
Unit-тесты для проверки null-safe радиуса в SQL запросах
"""

import unittest
from unittest.mock import Mock

from utils.unified_events_service import UnifiedEventsService


class TestNullSafeRadius(unittest.TestCase):
    """Тесты для null-safe радиуса"""

    def setUp(self):
        """Настройка тестов"""
        # Используем тестовую БД или мокаем
        self.engine = Mock()
        self.service = UnifiedEventsService(self.engine)

        # Настраиваем мок для context manager
        self.mock_conn = Mock()
        self.mock_result = Mock()
        self.mock_result.__iter__ = Mock(return_value=iter([]))
        self.mock_conn.execute.return_value = self.mock_result

        self.engine.connect.return_value.__enter__ = Mock(return_value=self.mock_conn)
        self.engine.connect.return_value.__exit__ = Mock(return_value=None)

    def test_null_coordinates_excluded(self):
        """Тест: события с NULL координатами исключаются из результата"""
        # Вызываем поиск
        self.service.search_events_today(city="bali", user_lat=-8.673445, user_lng=115.244452, radius_km=10)

        # Проверяем, что был вызван правильный SQL запрос
        self.mock_conn.execute.assert_called_once()
        sql_query = self.mock_conn.execute.call_args[0][0].text

        # Проверяем, что в SQL есть проверка на NOT NULL
        self.assertIn("lat IS NOT NULL", sql_query)
        self.assertIn("lng IS NOT NULL", sql_query)

        # Проверяем, что нет старой логики с OR NULL
        self.assertNotIn("lat IS NULL OR", sql_query)
        self.assertNotIn("lng IS NULL OR", sql_query)

    def test_haversine_formula_with_null_safety(self):
        """Тест: формула Haversine работает только с валидными координатами"""
        # Вызываем поиск
        self.service.search_events_today(city="bali", user_lat=-8.673445, user_lng=115.244452, radius_km=10)

        # Проверяем SQL запрос
        sql_query = self.mock_conn.execute.call_args[0][0].text

        # Проверяем порядок условий: сначала NOT NULL, потом Haversine
        lat_not_null_pos = sql_query.find("lat IS NOT NULL")
        lng_not_null_pos = sql_query.find("lng IS NOT NULL")
        haversine_pos = sql_query.find("6371 * acos")

        self.assertLess(lat_not_null_pos, haversine_pos)
        self.assertLess(lng_not_null_pos, haversine_pos)

    def test_radius_parameter_handling(self):
        """Тест: параметр radius корректно обрабатывается"""
        # Тестируем с разными значениями радиуса
        test_radii = [5, 10, 15, 25, 50]

        for radius in test_radii:
            self.service.search_events_today(city="bali", user_lat=-8.673445, user_lng=115.244452, radius_km=radius)

            # Проверяем, что radius передается в SQL
            call_args = self.mock_conn.execute.call_args
            sql_params = call_args[0][1]

            self.assertEqual(sql_params["radius_km"], radius)

    def test_no_coordinates_search(self):
        """Тест: поиск без координат не использует Haversine"""
        # Вызываем поиск без координат
        self.service.search_events_today(city="bali")

        # Проверяем SQL запрос
        sql_query = self.mock_conn.execute.call_args[0][0].text

        # Проверяем, что нет Haversine формулы
        self.assertNotIn("6371 * acos", sql_query)
        self.assertNotIn("lat IS NOT NULL", sql_query)
        self.assertNotIn("lng IS NOT NULL", sql_query)


if __name__ == "__main__":
    unittest.main()
