"""
Интеграционные тесты для рендера карточки события: локация-как-ссылка и категории
"""

import datetime as dt
import os
import sys

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_enhanced_v3 import (
    _build_event_categories_line,
    _build_event_info_line,
    _build_event_location_line,
    _normalize_event_description_for_display,
    build_maps_url,
    render_event_html,
)


class TestRenderEventCardRoute:
    """Тесты для рендера карточки события с кликабельной локацией (бывш. Маршрут)"""

    def base_event(self, **kwargs):
        """Создает базовое событие с дефолтными значениями"""
        event = {
            "id": "1",
            "type": "source",
            "title": "Test Event",
            "start": dt.datetime.now(dt.UTC),
            "when_str": "сегодня в 15:00",
            "distance_km": 2.5,
            "source_url": "https://valid.site/event",
        }
        event.update(kwargs)
        return event

    def test_route_with_venue_name(self):
        """Тест A: Есть venue (название места) — ссылка ведёт на maps с venue"""
        event = self.base_event(venue_name="Museum Bali", address=None, coords=None)

        html = render_event_html(event, 1)

        assert "🚗" not in html
        assert "Маршрут" not in html
        assert "📍 <a href=" in html
        assert "Museum Bali</a>" in html
        assert "Museum+Bali" in html or "Museum%2BBali" in html
        assert "https://www.google.com/maps/search/?api=1&query=" in html

    def test_route_with_address(self):
        """Тест B: Нет venue, но есть address"""
        event = self.base_event(venue_name=None, address="Jl. Danau Tamblingan 80, Sanur", coords=None)

        html = render_event_html(event, 1)

        assert "📍 <a href=" in html
        assert "Jl. Danau Tamblingan 80, Sanur</a>" in html
        assert "Jl.+Danau+Tamblingan+80" in html or "Jl.%2BDanau%2BTamblingan%2B80" in html

    def test_route_with_coords(self):
        """Тест C: Есть только coords"""
        event = self.base_event(venue_name=None, address=None, lat=-8.67, lng=115.25)

        html = render_event_html(event, 1)

        assert "📍 <a href=" in html
        assert "координаты (-8.6700, 115.2500)</a>" in html
        assert "-8.670000,115.250000" in html

    def test_route_with_no_location(self):
        """Тест D: Нет venue/address/coords"""
        event = self.base_event(venue_name=None, address=None, coords=None)

        html = render_event_html(event, 1)

        assert "Локация</a>" in html
        assert "📍 <a href=" in html
        assert "https://www.google.com/maps" in html

    def test_route_priority_venue_over_address(self):
        """Тест приоритета: venue_name > address"""
        event = self.base_event(venue_name="Cafe Moka", address="Jl. Danau Tamblingan 80, Sanur", coords=None)

        html = render_event_html(event, 1)

        assert "Cafe+Moka" in html or "Cafe%2BMoka" in html
        assert "Jl.+Danau+Tamblingan" not in html

    def test_route_priority_address_over_coords(self):
        """Тест приоритета: address > coords"""
        event = self.base_event(venue_name=None, address="Jl. Danau Tamblingan 80, Sanur", lat=-8.67, lng=115.25)

        html = render_event_html(event, 1)

        assert "Jl.+Danau+Tamblingan" in html or "Jl.%2BDanau%2BTamblingan" in html
        assert "-8.67,115.25" not in html

    def test_route_priority_venue_over_all(self):
        """Тест приоритета: venue_name > address > coords"""
        event = self.base_event(
            venue_name="Museum Bali",
            address="Jl. Danau Tamblingan 80, Sanur",
            lat=-8.67,
            lng=115.25,
        )

        html = render_event_html(event, 1)

        assert "Museum+Bali" in html or "Museum%2BBali" in html
        assert "Jl.+Danau+Tamblingan" not in html
        assert "-8.67,115.25" not in html

    def test_venue_display_priority(self):
        """Тест отображения venue в карточке (как текст ссылки)"""
        event = self.base_event(venue_name="Cafe Moka")
        html = render_event_html(event, 1)
        assert "Cafe Moka</a>" in html

        event = self.base_event(venue_name=None, address="Jl. Danau Tamblingan 80")
        html = render_event_html(event, 1)
        assert "Jl. Danau Tamblingan 80</a>" in html

        event = self.base_event(venue_name=None, address=None, lat=-8.67, lng=115.25)
        html = render_event_html(event, 1)
        assert "координаты (-8.6700, 115.2500)</a>" in html

        event = self.base_event(venue_name=None, address=None, coords=None)
        html = render_event_html(event, 1)
        assert "Локация</a>" in html

    def test_build_maps_url_directly(self):
        """Тест функции build_maps_url напрямую"""
        event = {"venue_name": "Museum Bali"}
        url = build_maps_url(event)
        assert "Museum+Bali" in url or "Museum%2BBali" in url
        assert "https://www.google.com/maps/search/?api=1&query=" in url

        event = {"address": "Jl. Danau Tamblingan 80, Sanur"}
        url = build_maps_url(event)
        assert "Jl.+Danau+Tamblingan" in url or "Jl.%2BDanau%2BTamblingan" in url

        event = {"lat": -8.67, "lng": 115.25}
        url = build_maps_url(event)
        assert "-8.670000,115.250000" in url

        event = {}
        url = build_maps_url(event)
        assert url == "https://www.google.com/maps"

    def test_new_venue_structure(self):
        """Тест новой структуры venue (venue.name, venue.address)"""
        event = self.base_event(
            venue={"name": "New Venue", "address": "New Address"},
            venue_name="Old Venue",
            address="Old Address",
        )

        html = render_event_html(event, 1)

        assert "New Venue</a>" in html
        assert "Old Venue" not in html
        assert "New+Venue" in html or "New%2BVenue" in html

    def test_source_url_in_card(self):
        """Тест отображения источника в карточке"""
        event = self.base_event(source_url="https://valid.site/event")
        html = render_event_html(event, 1)
        assert "🔗" in html
        assert "Подробнее" in html
        assert "https://valid.site/event" in html

        event = self.base_event(source_url="https://example.com/event")
        html = render_event_html(event, 1)
        assert "ℹ️ Источник не указан" in html
        assert "https://example.com/event" not in html

    def test_card_structure_complete(self):
        """Тест полной структуры карточки"""
        event = self.base_event(venue_name="Test Venue", source_url="https://valid.site/event")

        html = render_event_html(event, 1)

        assert "1) <b>Test Event</b>" in html
        assert "сегодня в 15:00" in html
        assert "(2.5 км)" in html
        assert "📍 <a href=" in html
        assert "Test Venue</a>" in html
        assert '🔗 <a href="https://valid.site/event">Подробнее</a>' in html
        assert "🚗" not in html
        assert "Маршрут" not in html

    def test_source_tags_in_info_line(self):
        """Теги источника отображаются отдельной строкой после локации."""
        event = self.base_event(
            source="baliforum",
            venue_name="GWK Cultural Park",
            tags=["Фестиваль", "Музыка"],
            categories=["Выставка"],
        )
        html = render_event_html(event, 1)
        assert "📍 <a href=" in html
        assert "GWK Cultural Park</a>" in html
        assert "\n🎭 Фестиваль / Музыка\n" in html
        assert "Выставка" not in html

    def test_raw_category_fallback_for_display_tags(self):
        event = self.base_event(
            venue_name="Savaya",
            raw_category="Вечеринка, Музыка",
            categories=["Вечеринка"],
        )
        html = render_event_html(event, 1)
        assert "\n🎭 Вечеринка / Музыка\n" in html

    def test_empty_tags_no_theater_emoji(self):
        """Без тегов источника — только 📍 с ссылкой"""
        event = self.base_event(venue_name="Cafe", categories=["Еда"])
        html = render_event_html(event, 1)
        assert "🎭" not in html
        assert "📍 <a href=" in html
        assert "Cafe</a>" in html

    def test_build_event_info_line_directly(self):
        event = self.base_event(
            source="baliforum",
            venue_name="Venue X",
            tags=["Фестиваль", "Музыка"],
            categories=["Выставка"],
        )
        line = _build_event_info_line(event, "Venue X", user_id=None, lang="ru")
        assert line.startswith("📍 <a href=")
        assert "Venue X</a>" in line
        assert "\n🎭 Фестиваль / Музыка" in line

    def test_build_event_location_and_categories_lines(self):
        event = self.base_event(
            source="baliforum",
            venue_name="Venue X",
            tags=["Фестиваль", "Музыка"],
        )
        location_line = _build_event_location_line(event, "Venue X", user_id=None, lang="ru")
        categories_line = _build_event_categories_line(event, lang="ru")
        assert location_line.startswith("📍 <a href=")
        assert "Venue X</a>" in location_line
        assert categories_line == "🎭 Фестиваль / Музыка"

    def test_distance_km_suffix_en(self):
        event = self.base_event(venue_name="Test Venue", source_url="https://valid.site/event")
        html = render_event_html(event, 1, user_id=999)
        # user_id без языка в БД → ru по умолчанию
        assert "(2.5 км)" in html

        from unittest.mock import patch

        with patch("bot_enhanced_v3.get_user_language_or_default", return_value="en"):
            html_en = render_event_html(event, 1, user_id=999)
        assert "(2.5 km)" in html_en
        assert " км)" not in html_en

    def test_source_tags_en_in_info_line(self):
        """EN: теги BaliForum через статический словарь."""
        event = self.base_event(
            source="baliforum",
            venue_name="GWK Cultural Park",
            tags=["Фестиваль", "Музыка"],
        )
        categories_line = _build_event_categories_line(event, lang="en")
        assert categories_line == "🎭 Festival / Music"
        assert "Фестиваль" not in categories_line

    def test_hide_description_when_only_location_duplicate(self):
        """Если в description только адрес — строка 📝 не показываем."""
        event = self.base_event(
            venue_name="Flow Place Berawa",
            description="📍 Место: Flow Place Berawa",
            source="baliforum",
            tags=["Танцы", "Медитация"],
        )
        html = render_event_html(event, 1)
        assert "📝" not in html
        assert "Flow Place Berawa</a>" in html

    def test_show_description_when_real_text_present(self):
        event = self.base_event(
            venue_name="Flow Place Berawa",
            description="Женский круг для глубокой практики.\n📍 Место: Flow Place Berawa",
        )
        html = render_event_html(event, 1)
        assert "📝 Женский круг для глубокой практики." in html
        assert "📍 Место:" not in html

    def test_normalize_event_description_for_display(self):
        event = {"venue_name": "Flow Place Berawa", "location_name": "Flow Place Berawa"}
        assert _normalize_event_description_for_display("📍 Место: Flow Place Berawa", event) == ""
        assert (
            _normalize_event_description_for_display(
                "Текст события\n📍 Место: Flow Place Berawa",
                event,
            )
            == "Текст события"
        )

    def test_location_display_replaces_plus_with_spaces(self):
        """Google Maps URL-encoding в location_name не должен попадать в текст ссылки."""
        event = self.base_event(
            type="user",
            venue_name="Mie+Gacoan+Canggu",
            location_name="Mie+Gacoan+Canggu",
            lat=-8.65,
            lng=115.14,
            organizer_id=123,
            organizer_username="Fincontro",
        )
        html = render_event_html(event, 4)
        assert "Mie Gacoan Canggu</a>" in html
        assert "Mie+Gacoan" not in html
        assert build_maps_url(event).startswith("https://www.google.com/maps")
