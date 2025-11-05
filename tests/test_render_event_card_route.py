"""
Интеграционные тесты для рендера карточки события с кнопкой "Маршрут"
"""

import datetime as dt
import os
import sys

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot_enhanced_v3 import build_maps_url, render_event_html


class TestRenderEventCardRoute:
    """Тесты для рендера карточки события с кнопкой Маршрут"""

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
        """Тест A: Есть venue (название места)"""
        event = self.base_event(venue_name="Museum Bali", address=None, coords=None)

        html = render_event_html(event, 1)

        # Проверяем что в HTML есть кнопка Маршрут с venue
        assert "🚗" in html
        assert "Маршрут" in html
        assert "Museum+Bali" in html or "Museum%2BBali" in html
        assert "https://www.google.com/maps/search/?api=1&query=" in html

    def test_route_with_address(self):
        """Тест B: Нет venue, но есть address"""
        event = self.base_event(venue_name=None, address="Jl. Danau Tamblingan 80, Sanur", coords=None)

        html = render_event_html(event, 1)

        # Проверяем что в HTML есть кнопка Маршрут с адресом
        assert "🚗" in html
        assert "Маршрут" in html
        assert "Jl.+Danau+Tamblingan+80" in html or "Jl.%2BDanau%2BTamblingan%2B80" in html
        assert "https://www.google.com/maps/search/?api=1&query=" in html

    def test_route_with_coords(self):
        """Тест C: Есть только coords"""
        event = self.base_event(venue_name=None, address=None, lat=-8.67, lng=115.25)

        html = render_event_html(event, 1)

        # Проверяем что в HTML есть кнопка Маршрут с координатами
        assert "🚗" in html
        assert "Маршрут" in html
        assert "-8.67,115.25" in html
        assert "https://www.google.com/maps/search/?api=1&query=" in html

    def test_route_with_no_location(self):
        """Тест D: Нет venue/address/coords"""
        event = self.base_event(venue_name=None, address=None, coords=None)

        html = render_event_html(event, 1)

        # Проверяем что есть нейтральная фраза и кнопка Маршрут все равно есть
        assert "Локация" in html
        assert "🚗" in html
        assert "Маршрут" in html
        # Должна быть дефолтная ссылка на Google Maps
        assert "https://www.google.com/maps" in html

    def test_route_priority_venue_over_address(self):
        """Тест приоритета: venue_name > address"""
        event = self.base_event(venue_name="Cafe Moka", address="Jl. Danau Tamblingan 80, Sanur", coords=None)

        html = render_event_html(event, 1)

        # Должен использоваться venue_name, а не address
        assert "Cafe+Moka" in html or "Cafe%2BMoka" in html
        assert "Jl.+Danau+Tamblingan" not in html

    def test_route_priority_address_over_coords(self):
        """Тест приоритета: address > coords"""
        event = self.base_event(venue_name=None, address="Jl. Danau Tamblingan 80, Sanur", lat=-8.67, lng=115.25)

        html = render_event_html(event, 1)

        # Должен использоваться address, а не coords
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

        # Должен использоваться venue_name
        assert "Museum+Bali" in html or "Museum%2BBali" in html
        assert "Jl.+Danau+Tamblingan" not in html
        assert "-8.67,115.25" not in html

    def test_venue_display_priority(self):
        """Тест отображения venue в карточке"""
        # С venue_name
        event = self.base_event(venue_name="Cafe Moka")
        html = render_event_html(event, 1)
        assert "Cafe Moka" in html

        # С address (без venue_name)
        event = self.base_event(venue_name=None, address="Jl. Danau Tamblingan 80")
        html = render_event_html(event, 1)
        assert "Jl. Danau Tamblingan 80" in html

        # С coords (без venue_name и address)
        event = self.base_event(venue_name=None, address=None, lat=-8.67, lng=115.25)
        html = render_event_html(event, 1)
        assert "координаты (-8.6700, 115.2500)" in html

        # Без ничего
        event = self.base_event(venue_name=None, address=None, coords=None)
        html = render_event_html(event, 1)
        assert "Локация" in html

    def test_build_maps_url_directly(self):
        """Тест функции build_maps_url напрямую"""
        # С venue_name
        event = {"venue_name": "Museum Bali"}
        url = build_maps_url(event)
        assert "Museum+Bali" in url or "Museum%2BBali" in url
        assert "https://www.google.com/maps/search/?api=1&query=" in url

        # С address
        event = {"address": "Jl. Danau Tamblingan 80, Sanur"}
        url = build_maps_url(event)
        assert "Jl.+Danau+Tamblingan" in url or "Jl.%2BDanau%2BTamblingan" in url

        # С coords
        event = {"lat": -8.67, "lng": 115.25}
        url = build_maps_url(event)
        assert "-8.67,115.25" in url

        # Без ничего
        event = {}
        url = build_maps_url(event)
        assert url == "https://www.google.com/maps"

    def test_new_venue_structure(self):
        """Тест новой структуры venue (venue.name, venue.address)"""
        event = self.base_event(
            venue={"name": "New Venue", "address": "New Address"},
            venue_name="Old Venue",  # должен игнорироваться
            address="Old Address",  # должен игнорироваться
        )

        html = render_event_html(event, 1)

        # Должна использоваться новая структура
        assert "New Venue" in html
        assert "Old Venue" not in html
        assert "New+Venue" in html or "New%2BVenue" in html

    def test_source_url_in_card(self):
        """Тест отображения источника в карточке"""
        # С валидным источником
        event = self.base_event(source_url="https://valid.site/event")
        html = render_event_html(event, 1)
        assert "🔗" in html
        assert "Источник" in html
        assert "https://valid.site/event" in html

        # С заблокированным источником
        event = self.base_event(source_url="https://example.com/event")
        html = render_event_html(event, 1)
        assert "ℹ️ Источник не указан" in html
        assert "https://example.com/event" not in html

    def test_card_structure_complete(self):
        """Тест полной структуры карточки"""
        event = self.base_event(venue_name="Test Venue", source_url="https://valid.site/event")

        html = render_event_html(event, 1)

        # Проверяем основные элементы карточки
        assert "1) <b>Test Event</b>" in html
        assert "сегодня в 15:00" in html
        assert "(2.5 км)" in html  # расстояние
        assert "📍 Test Venue" in html
        assert '🔗 <a href="https://valid.site/event">Источник</a>' in html
        assert "🚗 <a href=" in html
        assert "Маршрут</a>" in html
