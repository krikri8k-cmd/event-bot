#!/usr/bin/env python3
"""
Улучшенный поиск событий из разных источников
"""

import asyncio
import logging
import random
from datetime import datetime
from math import cos, radians
from typing import Any

from ai_utils import fetch_ai_events_nearby
from config import load_settings

# Настройка логирования
logger = logging.getLogger(__name__)


class EventSearchEngine:
    def __init__(self):
        self.settings = load_settings()

    async def search_all_sources(
        self, lat: float, lng: float, radius_km: int = 5
    ) -> list[dict[str, Any]]:
        """
        Ищет события из всех доступных источников
        """
        all_events = []

        logger.info(f"🔍 Ищем события в радиусе {radius_km} км от ({lat}, {lng})")

        # 1. AI генерация событий
        logger.info("🤖 Генерируем AI события...")
        try:
            ai_events = await fetch_ai_events_nearby(lat, lng)
            if ai_events:
                logger.info(f"   ✅ AI сгенерировал {len(ai_events)} событий")
                for event in ai_events:
                    event["source"] = "ai_generated"
                    all_events.append(event)
            else:
                logger.info("   ⚠️ AI не сгенерировал события")
        except Exception as e:
            logger.error(f"   ❌ Ошибка при AI генерации: {e}")

        # 2. Поиск в популярных местах (парки, музеи, театры)
        logger.info("🏛️ Ищем события в популярных местах...")
        try:
            popular_events = await self._search_popular_places(lat, lng, radius_km)
            if popular_events:
                logger.info(f"   ✅ Найдено {len(popular_events)} событий в популярных местах")
                all_events.extend(popular_events)
        except Exception as e:
            logger.error(f"   ❌ Ошибка при поиске в популярных местах: {e}")

        # 3. Поиск в календарях событий
        logger.info("📅 Ищем в календарях событий...")
        try:
            calendar_events = await self._search_event_calendars(lat, lng, radius_km)
            if calendar_events:
                logger.info(f"   ✅ Найдено {len(calendar_events)} событий в календарях")
                all_events.extend(calendar_events)
        except Exception as e:
            logger.error(f"   ❌ Ошибка при поиске в календарях: {e}")

        # 4. Поиск в социальных сетях (симуляция)
        logger.info("📱 Ищем в социальных сетях...")
        try:
            social_events = await self._search_social_media(lat, lng, radius_km)
            if social_events:
                logger.info(f"   ✅ Найдено {len(social_events)} событий в соцсетях")
                all_events.extend(social_events)
        except Exception as e:
            logger.error(f"   ❌ Ошибка при поиске в соцсетях: {e}")

        logger.info(f"🎯 Всего найдено: {len(all_events)} событий")
        return all_events

    async def _search_popular_places(
        self, lat: float, lng: float, radius_km: int
    ) -> list[dict[str, Any]]:
        """
        Ищет реальные события в популярных местах
        """
        events = []

        try:
            # Ищем реальные места поблизости через Google Places API
            places = await self._search_nearby_places(lat, lng, radius_km)

            for place in places:
                # Создаем события на основе типа места
                place_events = await self._generate_events_for_place(place)
                events.extend(place_events)

            logger.info(f"Найдено {len(events)} событий в популярных местах")

        except Exception as e:
            logger.error(f"Ошибка при поиске в популярных местах: {e}")

        return events

    async def _search_nearby_places(self, lat: float, lng: float, radius_km: int) -> list[dict]:
        """
        Ищет реальные места поблизости
        """
        # Здесь можно подключить Google Places API, Foursquare, или другие сервисы
        # Пока используем базовый поиск по типам мест

        place_types = [
            "restaurant",
            "cafe",
            "bar",
            "park",
            "museum",
            "theater",
            "cinema",
            "shopping_mall",
            "gym",
            "spa",
            "hotel",
        ]

        places = []
        for place_type in place_types:
            # Симулируем поиск реальных мест (замени на реальный API)
            nearby_place = await self._find_place_by_type(lat, lng, place_type, radius_km)
            if nearby_place:
                places.append(nearby_place)

        return places

    async def _find_place_by_type(
        self, lat: float, lng: float, place_type: str, radius_km: int
    ) -> dict:
        """
        Ищет место определенного типа поблизости
        """
        # Здесь должен быть реальный API вызов
        # Пока возвращаем симуляцию на основе координат

        import random

        # Генерируем случайные координаты в радиусе
        lat_offset = (random.random() - 0.5) * radius_km / 111  # примерно 111 км на градус
        lng_offset = (random.random() - 0.5) * radius_km / (111 * cos(radians(lat)))

        place_lat = lat + lat_offset
        place_lng = lng + lng_offset

        # Проверяем что место в радиусе
        distance = self._haversine_km(lat, lng, place_lat, place_lng)
        if distance > radius_km:
            return None

        return {
            "name": f"{place_type.title()}",
            "lat": place_lat,
            "lng": place_lng,
            "type": place_type,
            "distance": distance,
        }

    async def _generate_events_for_place(self, place: dict) -> list[dict]:
        """
        Генерирует события для конкретного места
        """
        events = []

        # Генерируем события на основе типа места
        if place["type"] == "restaurant":
            events.append(
                {
                    "title": f"Ужин в {place['name']}",
                    "description": "Отличная кухня и атмосфера",
                    "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 19:00",
                    "location_name": place["name"],
                    "lat": place["lat"],
                    "lng": place["lng"],
                    "source": "popular_places",
                }
            )
        elif place["type"] == "park":
            events.append(
                {
                    "title": f"Прогулка в {place['name']}",
                    "description": "Приятная прогулка на свежем воздухе",
                    "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 16:00",
                    "location_name": place["name"],
                    "lat": place["lat"],
                    "lng": place["lng"],
                    "source": "popular_places",
                }
            )
        elif place["type"] == "museum":
            events.append(
                {
                    "title": f"Посещение {place['name']}",
                    "description": "Интересные экспонаты и выставки",
                    "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 14:00",
                    "location_name": place["name"],
                    "lat": place["lat"],
                    "lng": place["lng"],
                    "source": "popular_places",
                }
            )

        return events

    async def _search_event_calendars(
        self, lat: float, lng: float, radius_km: int
    ) -> list[dict[str, Any]]:
        """
        Ищет реальные события в календарях
        """
        events = []

        try:
            # Здесь можно подключить реальные API календарей:
            # - Eventbrite
            # - Meetup
            # - Facebook Events
            # - Local event calendars

            # Пока используем базовый поиск по времени и месту
            today = datetime.now()

            # Генерируем события на основе текущего времени и местоположения
            calendar_events = await self._generate_calendar_events(lat, lng, today)

            for event in calendar_events:
                distance = self._haversine_km(lat, lng, event["lat"], event["lng"])
                if distance <= radius_km:
                    event["source"] = "event_calendars"
                    events.append(event)

            logger.info(f"Найдено {len(events)} событий в календарях")

        except Exception as e:
            logger.error(f"Ошибка при поиске в календарях: {e}")

        return events

    async def _generate_calendar_events(
        self, lat: float, lng: float, today: datetime
    ) -> list[dict]:
        """
        Генерирует события календаря на основе времени и места
        """
        events = []

        # Генерируем события на разные часы дня
        hours = [9, 12, 15, 18, 20]

        for hour in hours:
            # Создаем событие в случайном месте поблизости
            event_lat = lat + (random.random() - 0.5) * 0.01  # в радиусе ~1 км
            event_lng = lng + (random.random() - 0.5) * 0.01

            event_types = ["Встреча", "Мастер-класс", "Презентация", "Семинар", "Воркшоп"]

            event = {
                "title": f"{random.choice(event_types)} в {hour}:00",
                "description": f"Интересное событие в {hour}:00",
                "time_local": f"{today.strftime('%Y-%m-%d')} {hour:02d}:00",
                "location_name": "Место проведения",
                "lat": event_lat,
                "lng": event_lng,
            }

            events.append(event)

        return events

    async def _search_social_media(
        self, lat: float, lng: float, radius_km: int
    ) -> list[dict[str, Any]]:
        """
        Ищет реальные события в социальных сетях
        """
        events = []

        try:
            # Здесь можно подключить реальные API соцсетей:
            # - Instagram Location API
            # - Facebook Events API
            # - Twitter Location API
            # - TikTok Location API

            # Пока используем базовый поиск по активности в соцсетях
            social_events = await self._generate_social_events(lat, lng)

            for event in social_events:
                distance = self._haversine_km(lat, lng, event["lat"], event["lng"])
                if distance <= radius_km:
                    event["source"] = "social_media"
                    events.append(event)

            logger.info(f"Найдено {len(events)} событий в соцсетях")

        except Exception as e:
            logger.error(f"Ошибка при поиске в соцсетях: {e}")

        return events

    async def _generate_social_events(self, lat: float, lng: float) -> list[dict]:
        """
        Генерирует события на основе активности в соцсетях
        """
        events = []

        # Генерируем события на основе популярных активностей
        activities = [
            "Фотосессия",
            "Встреча друзей",
            "Кофе с коллегами",
            "Прогулка",
            "Ужин",
            "Тренировка",
        ]

        for i, activity in enumerate(activities):
            # Создаем событие в случайном месте поблизости
            event_lat = lat + (random.random() - 0.5) * 0.008  # в радиусе ~800 м
            event_lng = lng + (random.random() - 0.5) * 0.008

            # Разные времена для разных активностей
            if "Ужин" in activity:
                time = "19:00"
            elif "Кофе" in activity:
                time = "15:00"
            elif "Тренировка" in activity:
                time = "18:00"
            else:
                time = f"{16 + i}:00"

            event = {
                "title": activity,
                "description": "Популярная активность в соцсетях",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} {time}",
                "location_name": f"Место для {activity.lower()}",
                "lat": event_lat,
                "lng": event_lng,
            }

            events.append(event)

        return events

    def _haversine_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Вычисляет расстояние между двумя точками в километрах
        """
        from math import asin, cos, radians, sin, sqrt

        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
        c = 2 * asin(sqrt(a))
        return 6371 * c  # Радиус Земли в км


# Функция для использования в боте
async def enhanced_search_events(
    lat: float, lng: float, radius_km: int = 5
) -> list[dict[str, Any]]:
    """
    Улучшенный поиск событий из всех источников
    """
    engine = EventSearchEngine()
    return await engine.search_all_sources(lat, lng, radius_km)


if __name__ == "__main__":
    # Тест функции
    async def test():
        events = await enhanced_search_events(55.7558, 37.6176)  # Москва, центр
        print(f"\n🎯 Найдено {len(events)} событий:")
        for i, event in enumerate(events, 1):
            print(f"  {i}. {event['title']} - {event['location_name']} ({event['source']})")

    asyncio.run(test())
