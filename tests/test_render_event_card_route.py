"""
Интеграционные тесты для рендера карточки события: локация-как-ссылка и категории
"""

import datetime as dt
import os
import sys

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_enhanced_v3 import _build_event_info_line, build_maps_url, render_event_html


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
        assert "🌐" in html
        assert "Источник" in html
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
        assert '🌐 <a href="https://valid.site/event">Источник</a>' in html
        assert "🚗" not in html
        assert "Маршрут" not in html

    def test_categories_in_info_line(self):
        """Категории отображаются перед локацией"""
        event = self.base_event(
            venue_name="Savaya",
            categories=["Вечеринка", "Выставка"],
        )
        html = render_event_html(event, 1)
        assert "🎭 Вечеринка / Выставка • 📍" in html
        assert "Savaya</a>" in html

    def test_empty_categories_no_theater_emoji(self):
        """Без категорий — только 📍 с ссылкой"""
        event = self.base_event(venue_name="Cafe", categories=[])
        html = render_event_html(event, 1)
        assert "🎭" not in html
        assert "📍 <a href=" in html
        assert "Cafe</a>" in html

    def test_build_event_info_line_directly(self):
        event = self.base_event(venue_name="Venue X", categories=["Еда"])
        line = _build_event_info_line(event, "Venue X", user_id=None)
        assert line.startswith("🎭 Еда • 📍")
        assert "Venue X</a>" in line
