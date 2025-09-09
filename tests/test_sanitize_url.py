"""
Тесты для функции sanitize_url
"""

import os
import sys

import pytest

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_enhanced_v3 import sanitize_url


class TestSanitizeUrl:
    """Тесты для функции sanitize_url"""

    @pytest.mark.parametrize(
        "input_url,expected",
        [
            # Мусорные домены
            ("https://example.com/foo", None),
            ("http://example.org/x", None),
            ("https://www.example.net/abc", None),
            ("https://subdomain.example.com/path", None),
            # Google Calendar без параметров события
            ("https://calendar.google.com/calendar/u/0/r", None),
            ("https://calendar.google.com/calendar", None),
            ("https://calendar.google.com/calendar/embed", None),
            # Google Calendar с параметрами события
            (
                "https://calendar.google.com/calendar/event?eid=abc",
                "https://calendar.google.com/calendar/event?eid=abc",
            ),
            (
                "https://calendar.google.com/calendar/event?event=123",
                "https://calendar.google.com/calendar/event?event=123",
            ),
            (
                "https://calendar.google.com/calendar/event?cid=xyz",
                "https://calendar.google.com/calendar/event?cid=xyz",
            ),
            (
                "https://calendar.google.com/calendar/event?eid=abc&other=param",
                "https://calendar.google.com/calendar/event?eid=abc&other=param",
            ),
            # Валидные URL
            ("https://t.me/some_channel/123", "https://t.me/some_channel/123"),
            ("https://site.com?utm_source=x", "https://site.com?utm_source=x"),
            ("https://good.io/path", "https://good.io/path"),
            ("http://localhost:8080/test", "http://localhost:8080/test"),
            # Некорректные URL
            ("not a url", None),
            ("", None),
            (None, None),
            ("ftp://example.com", None),
            ("javascript:alert(1)", None),
            # Регистр
            ("HTTPS://GOOD.IO/PATH", "HTTPS://GOOD.IO/PATH"),
            ("HTTP://EXAMPLE.COM", None),
        ],
    )
    def test_sanitize_url(self, input_url, expected):
        """Тестирует sanitize_url с различными входными данными"""
        result = sanitize_url(input_url)
        assert result == expected, f"Для URL '{input_url}' ожидался '{expected}', получен '{result}'"

    def test_blacklist_domains_comprehensive(self):
        """Дополнительные тесты для blacklist доменов"""
        test_cases = [
            ("https://example.com", None),
            ("https://www.example.com", None),
            ("https://sub.example.com", None),
            ("https://example.org", None),
            ("https://example.net", None),
            ("https://test.example.com/path", None),
            ("https://valid-site.com", "https://valid-site.com"),
            ("https://example.co", "https://example.co"),  # не в blacklist
        ]

        for url, expected in test_cases:
            result = sanitize_url(url)
            assert result == expected, f"URL '{url}' должен давать '{expected}', получен '{result}'"
