#!/usr/bin/env python3
"""
Unit-тесты для проверки TZ логики "сегодня"
"""

import unittest
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from utils.simple_timezone import get_city_timezone, get_today_start_utc, get_tomorrow_start_utc


class TestTimezoneLogic(unittest.TestCase):
    """Тесты для TZ логики"""

    def test_bali_today_window(self):
        """Тест: окно 'сегодня' для Бали (UTC+8)"""
        # Бали: Asia/Makassar (UTC+8)
        bali_tz = ZoneInfo("Asia/Makassar")

        # Получаем реальные окна "сегодня" и "завтра"
        start_utc = get_today_start_utc("bali")
        end_utc = get_tomorrow_start_utc("bali")

        # Проверяем, что окна корректные
        self.assertEqual(start_utc.hour, 16)  # 16:00 UTC = 00:00 в Бали
        self.assertEqual(start_utc.minute, 0)
        self.assertEqual(start_utc.second, 0)

        self.assertEqual(end_utc.hour, 16)  # 16:00 UTC следующего дня
        self.assertEqual(end_utc.minute, 0)
        self.assertEqual(end_utc.second, 0)

        # Проверяем, что разница ровно 24 часа
        diff = end_utc - start_utc
        self.assertEqual(diff.total_seconds(), 24 * 3600)

        # Проверяем, что текущее время в Бали попадает в окно "сегодня"
        now_bali = datetime.now(bali_tz)
        now_utc = now_bali.astimezone(UTC)

        self.assertGreaterEqual(now_utc, start_utc)
        self.assertLess(now_utc, end_utc)

    def test_moscow_today_window(self):
        """Тест: окно 'сегодня' для Москвы (UTC+3)"""
        # Москва: Europe/Moscow (UTC+3)
        moscow_tz = ZoneInfo("Europe/Moscow")

        # Получаем реальные окна "сегодня" и "завтра"
        start_utc = get_today_start_utc("moscow")
        end_utc = get_tomorrow_start_utc("moscow")

        # Проверяем, что окна корректные
        self.assertEqual(start_utc.hour, 21)  # 21:00 UTC = 00:00 в Москве
        self.assertEqual(start_utc.minute, 0)
        self.assertEqual(start_utc.second, 0)

        self.assertEqual(end_utc.hour, 21)  # 21:00 UTC следующего дня
        self.assertEqual(end_utc.minute, 0)
        self.assertEqual(end_utc.second, 0)

        # Проверяем, что разница ровно 24 часа
        diff = end_utc - start_utc
        self.assertEqual(diff.total_seconds(), 24 * 3600)

        # Проверяем, что текущее время в Москве попадает в окно "сегодня"
        now_moscow = datetime.now(moscow_tz)
        now_utc = now_moscow.astimezone(UTC)

        self.assertGreaterEqual(now_utc, start_utc)
        self.assertLess(now_utc, end_utc)

    def test_spb_today_window(self):
        """Тест: окно 'сегодня' для СПб (UTC+3)"""
        # СПб: Europe/Moscow (UTC+3)
        spb_tz = ZoneInfo("Europe/Moscow")

        # Получаем реальные окна "сегодня" и "завтра"
        start_utc = get_today_start_utc("spb")
        end_utc = get_tomorrow_start_utc("spb")

        # Проверяем, что окна корректные
        self.assertEqual(start_utc.hour, 21)  # 21:00 UTC = 00:00 в СПб
        self.assertEqual(start_utc.minute, 0)
        self.assertEqual(start_utc.second, 0)

        self.assertEqual(end_utc.hour, 21)  # 21:00 UTC следующего дня
        self.assertEqual(end_utc.minute, 0)
        self.assertEqual(end_utc.second, 0)

        # Проверяем, что разница ровно 24 часа
        diff = end_utc - start_utc
        self.assertEqual(diff.total_seconds(), 24 * 3600)

        # Проверяем, что текущее время в СПб попадает в окно "сегодня"
        now_spb = datetime.now(spb_tz)
        now_utc = now_spb.astimezone(UTC)

        self.assertGreaterEqual(now_utc, start_utc)
        self.assertLess(now_utc, end_utc)

    def test_cross_midnight_bali(self):
        """Тест: кросс-полночь для Бали"""
        # Тестируем переход через полночь в Бали
        bali_tz = ZoneInfo("Asia/Makassar")

        # Получаем текущие окна
        start_today = get_today_start_utc("bali")
        end_today = get_tomorrow_start_utc("bali")

        # Проверяем, что окна не пересекаются
        self.assertLess(start_today, end_today)

        # Проверяем, что разница ровно 24 часа
        diff = end_today - start_today
        self.assertEqual(diff.total_seconds(), 24 * 3600)

        # Проверяем, что текущее время в Бали попадает в окно "сегодня"
        now_bali = datetime.now(bali_tz)
        now_utc = now_bali.astimezone(UTC)

        self.assertGreaterEqual(now_utc, start_today)
        self.assertLess(now_utc, end_today)

    def test_cross_midnight_moscow(self):
        """Тест: кросс-полночь для Москвы"""
        # Тестируем переход через полночь в Москве
        moscow_tz = ZoneInfo("Europe/Moscow")

        # Получаем текущие окна
        start_today = get_today_start_utc("moscow")
        end_today = get_tomorrow_start_utc("moscow")

        # Проверяем, что окна не пересекаются
        self.assertLess(start_today, end_today)

        # Проверяем, что разница ровно 24 часа
        diff = end_today - start_today
        self.assertEqual(diff.total_seconds(), 24 * 3600)

        # Проверяем, что текущее время в Москве попадает в окно "сегодня"
        now_moscow = datetime.now(moscow_tz)
        now_utc = now_moscow.astimezone(UTC)

        self.assertGreaterEqual(now_utc, start_today)
        self.assertLess(now_utc, end_today)

    def test_timezone_consistency(self):
        """Тест: консистентность временных зон"""
        # Проверяем, что все города используют правильные временные зоны
        self.assertEqual(get_city_timezone("bali"), "Asia/Makassar")
        self.assertEqual(get_city_timezone("moscow"), "Europe/Moscow")
        self.assertEqual(get_city_timezone("spb"), "Europe/Moscow")

        # Проверяем, что окна "сегодня" и "завтра" не пересекаются
        for city in ["bali", "moscow", "spb"]:
            start_today = get_today_start_utc(city)
            end_today = get_tomorrow_start_utc(city)

            # Окно "сегодня" должно быть меньше окна "завтра"
            self.assertLess(start_today, end_today)

            # Разница должна быть ровно 24 часа
            diff = end_today - start_today
            self.assertEqual(diff.total_seconds(), 24 * 3600)

    def test_utc_conversion(self):
        """Тест: конвертация в UTC"""
        # Проверяем, что все времена в UTC
        for city in ["bali", "moscow", "spb"]:
            start_utc = get_today_start_utc(city)
            end_utc = get_tomorrow_start_utc(city)

            # Времена должны быть в UTC
            self.assertEqual(start_utc.tzinfo, UTC)
            self.assertEqual(end_utc.tzinfo, UTC)

            # Времена должны быть корректными (минуты и секунды = 0)
            self.assertEqual(start_utc.minute, 0)
            self.assertEqual(start_utc.second, 0)
            self.assertEqual(start_utc.microsecond, 0)

            self.assertEqual(end_utc.minute, 0)
            self.assertEqual(end_utc.second, 0)
            self.assertEqual(end_utc.microsecond, 0)

            # Часы должны соответствовать часовому поясу города
            if city == "bali":
                self.assertEqual(start_utc.hour, 16)  # UTC+8
                self.assertEqual(end_utc.hour, 16)
            elif city in ["moscow", "spb"]:
                self.assertEqual(start_utc.hour, 21)  # UTC+3
                self.assertEqual(end_utc.hour, 21)


if __name__ == "__main__":
    unittest.main()
