"""
Тесты для функции get_source_url
"""

import os
import sys

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_enhanced_v3 import get_source_url


class TestGetSourceUrl:
    """Тесты для функции get_source_url"""

    def test_source_type_with_valid_url(self):
        """Тест для типа 'source' с валидным URL"""
        event = {"type": "source", "source_url": "https://valid.site/event", "title": "Test Event"}
        result = get_source_url(event)
        assert result == "https://valid.site/event"

    def test_source_type_with_blacklisted_url(self):
        """Тест для типа 'source' с заблокированным URL"""
        event = {"type": "source", "source_url": "https://example.com/event", "title": "Test Event"}
        result = get_source_url(event)
        assert result is None

    def test_source_type_fallback_to_url_field(self):
        """Тест для типа 'source' с fallback на поле 'url'"""
        event = {
            "type": "source",
            "source_url": "https://example.com/event",  # заблокирован
            "url": "https://valid.site/event",  # валидный
            "title": "Test Event",
        }
        result = get_source_url(event)
        assert result == "https://valid.site/event"

    def test_source_type_fallback_to_link_field(self):
        """Тест для типа 'source' с fallback на поле 'link'"""
        event = {
            "type": "source",
            "source_url": "https://example.com/event",  # заблокирован
            "url": "https://example.org/event",  # заблокирован
            "link": "https://valid.site/event",  # валидный
            "title": "Test Event",
        }
        result = get_source_url(event)
        assert result == "https://valid.site/event"

    def test_user_type_with_author_url(self):
        """Тест для типа 'user' с author_url"""
        event = {
            "type": "user",
            "author_url": "https://t.me/user/123",
            "chat_url": "https://example.com/chat",  # заблокирован
            "title": "User Event",
        }
        result = get_source_url(event)
        assert result == "https://t.me/user/123"

    def test_user_type_fallback_to_chat_url(self):
        """Тест для типа 'user' с fallback на chat_url"""
        event = {
            "type": "user",
            "author_url": "https://example.com/user",  # заблокирован
            "chat_url": "https://t.me/chat/456",
            "title": "User Event",
        }
        result = get_source_url(event)
        assert result == "https://t.me/chat/456"

    def test_ai_generated_type_with_valid_location_url(self):
        """Тест для типа 'ai_generated' с валидным location_url"""
        event = {
            "type": "ai_generated",
            "location_url": "https://goo.gl/maps/xyz",
            "title": "AI Event",
        }
        result = get_source_url(event)
        assert result == "https://goo.gl/maps/xyz"

    def test_ai_generated_type_with_blacklisted_location_url(self):
        """Тест для типа 'ai_generated' с заблокированным location_url"""
        event = {
            "type": "ai_generated",
            "location_url": "https://example.org/foo",
            "title": "AI Event",
        }
        result = get_source_url(event)
        assert result is None

    def test_ai_type_with_valid_location_url(self):
        """Тест для типа 'ai' с валидным location_url"""
        event = {"type": "ai", "location_url": "https://maps.google.com/place", "title": "AI Event"}
        result = get_source_url(event)
        assert result == "https://maps.google.com/place"

    def test_moment_type_with_valid_location_url(self):
        """Тест для типа 'moment' с валидным location_url"""
        event = {
            "type": "moment",
            "location_url": "https://t.me/moment/789",
            "title": "Moment Event",
        }
        result = get_source_url(event)
        assert result == "https://t.me/moment/789"

    def test_unknown_type_fallback_behavior(self):
        """Тест для неизвестного типа с fallback поведением"""
        event = {
            "type": "unknown",
            "source_url": "https://valid.site/event",
            "url": "https://example.com/event",  # заблокирован
            "link": "https://another.site/event",
            "title": "Unknown Event",
        }
        result = get_source_url(event)
        assert result == "https://valid.site/event"

    def test_no_type_fallback_behavior(self):
        """Тест для события без типа с fallback поведением"""
        event = {
            "source_url": "https://example.com/event",  # заблокирован
            "url": "https://valid.site/event",
            "title": "No Type Event",
        }
        result = get_source_url(event)
        assert result == "https://valid.site/event"

    def test_all_urls_blacklisted(self):
        """Тест когда все URL заблокированы"""
        event = {
            "type": "source",
            "source_url": "https://example.com/event",
            "url": "https://example.org/event",
            "link": "https://example.net/event",
            "title": "All Blacklisted Event",
        }
        result = get_source_url(event)
        assert result is None

    def test_all_urls_none_or_empty(self):
        """Тест когда все URL поля пустые"""
        event = {
            "type": "source",
            "source_url": None,
            "url": "",
            "link": None,
            "title": "No URLs Event",
        }
        result = get_source_url(event)
        assert result is None

    def test_google_calendar_with_event_params(self):
        """Тест Google Calendar URL с параметрами события"""
        event = {
            "type": "source",
            "source_url": "https://calendar.google.com/calendar/event?eid=abc123",
            "title": "Calendar Event",
        }
        result = get_source_url(event)
        assert result == "https://calendar.google.com/calendar/event?eid=abc123"

    def test_google_calendar_without_event_params(self):
        """Тест Google Calendar URL без параметров события"""
        event = {
            "type": "source",
            "source_url": "https://calendar.google.com/calendar/u/0/r",
            "title": "Empty Calendar Event",
        }
        result = get_source_url(event)
        assert result is None
