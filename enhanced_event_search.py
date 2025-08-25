#!/usr/bin/env python3
"""
Улучшенный поиск событий из разных источников
"""

import asyncio
from datetime import datetime
from typing import Any

from ai_utils import fetch_ai_events_nearby
from config import load_settings


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

        print(f"🔍 Ищем события в радиусе {radius_km} км от ({lat}, {lng})")

        # 1. AI генерация событий
        print("🤖 Генерируем AI события...")
        ai_events = await fetch_ai_events_nearby(lat, lng)
        if ai_events:
            print(f"   ✅ AI сгенерировал {len(ai_events)} событий")
            for event in ai_events:
                event["source"] = "ai_generated"
                all_events.append(event)
        else:
            print("   ⚠️ AI не сгенерировал события")

        # 2. Поиск в популярных местах (парки, музеи, театры)
        print("🏛️ Ищем события в популярных местах...")
        popular_events = await self._search_popular_places(lat, lng, radius_km)
        if popular_events:
            print(f"   ✅ Найдено {len(popular_events)} событий в популярных местах")
            all_events.extend(popular_events)

        # 3. Поиск в календарях событий
        print("📅 Ищем в календарях событий...")
        calendar_events = await self._search_event_calendars(lat, lng, radius_km)
        if calendar_events:
            print(f"   ✅ Найдено {len(calendar_events)} событий в календарях")
            all_events.extend(calendar_events)

        # 4. Поиск в социальных сетях (симуляция)
        print("📱 Ищем в социальных сетях...")
        social_events = await self._search_social_media(lat, lng, radius_km)
        if social_events:
            print(f"   ✅ Найдено {len(social_events)} событий в соцсетях")
            all_events.extend(social_events)

        print(f"🎯 Всего найдено: {len(all_events)} событий")
        return all_events

    async def _search_popular_places(
        self, lat: float, lng: float, radius_km: int
    ) -> list[dict[str, Any]]:
        """
        Ищет события в популярных местах (парки, музеи, театры)
        """
        events = []

        # Популярные места в Москве (реальные координаты)
        popular_places = [
            {
                "name": "Парк Горького",
                "lat": 55.7298,
                "lng": 37.6008,
                "type": "park",
                "events": [
                    {
                        "title": "Вечерние концерты в парке",
                        "time": "19:00",
                        "description": "Живая музыка на открытом воздухе",
                    },
                    {
                        "title": "Йога в парке",
                        "time": "08:00",
                        "description": "Бесплатная йога для всех желающих",
                    },
                    {
                        "title": "Фестиваль уличной еды",
                        "time": "12:00",
                        "description": "Лучшие рестораны города представляют свои блюда",
                    },
                ],
            },
            {
                "name": "Третьяковская галерея",
                "lat": 55.7415,
                "lng": 37.6208,
                "type": "museum",
                "events": [
                    {
                        "title": "Выставка современного искусства",
                        "time": "10:00",
                        "description": "Новые работы современных художников",
                    },
                    {
                        "title": "Экскурсия по русскому искусству",
                        "time": "14:00",
                        "description": "Знакомство с шедеврами русской живописи",
                    },
                ],
            },
            {
                "name": "Большой театр",
                "lat": 55.7600,
                "lng": 37.6186,
                "type": "theater",
                "events": [
                    {
                        "title": "Балет 'Лебединое озеро'",
                        "time": "19:00",
                        "description": "Классический балет",
                    },
                    {
                        "title": "Опера 'Евгений Онегин'",
                        "time": "19:00",
                        "description": "Опера П.И. Чайковского",
                    },
                ],
            },
            {
                "name": "Центр современного искусства Винзавод",
                "lat": 55.7412,
                "lng": 37.6543,
                "type": "art_gallery",
                "events": [
                    {
                        "title": "Выставка современного искусства",
                        "time": "12:00",
                        "description": "Работы молодых художников",
                    },
                    {
                        "title": "Мастер-класс по живописи",
                        "time": "15:00",
                        "description": "Учимся рисовать акварелью",
                    },
                ],
            },
            {
                "name": "Московская консерватория",
                "lat": 55.7558,
                "lng": 37.6046,
                "type": "concert_hall",
                "events": [
                    {
                        "title": "Концерт классической музыки",
                        "time": "19:30",
                        "description": "Симфонический оркестр",
                    },
                    {
                        "title": "Вечер камерной музыки",
                        "time": "19:00",
                        "description": "Струнный квартет",
                    },
                ],
            },
            {
                "name": "Театр на Таганке",
                "lat": 55.7415,
                "lng": 37.6543,
                "type": "theater",
                "events": [
                    {
                        "title": "Спектакль 'Ромео и Джульетта'",
                        "time": "19:00",
                        "description": "Современная постановка",
                    },
                    {
                        "title": "Драматический спектакль",
                        "time": "19:30",
                        "description": "Классическая драма",
                    },
                ],
            },
        ]

        for place in popular_places:
            distance = self._haversine_km(lat, lng, place["lat"], place["lng"])
            if distance <= radius_km:
                for event in place["events"]:
                    events.append(
                        {
                            "title": event["title"],
                            "description": event["description"],
                            "time_local": f"{datetime.now().strftime('%Y-%m-%d')} {event['time']}",
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
        Ищет события в календарях событий (симуляция)
        """
        events = []

        # Симуляция поиска в календарях
        calendar_events = [
            {
                "title": "Фестиваль уличной еды",
                "description": "Лучшие рестораны города представляют свои блюда",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 12:00",
                "location_name": "Центральная площадь",
                "lat": lat + 0.001,  # Рядом с пользователем
                "lng": lng + 0.001,
            },
            {
                "title": "Мастер-класс по живописи",
                "description": "Учимся рисовать акварелью с профессиональным художником",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 15:00",
                "location_name": "Художественная студия",
                "lat": lat - 0.002,
                "lng": lng + 0.002,
            },
        ]

        for event in calendar_events:
            distance = self._haversine_km(lat, lng, event["lat"], event["lng"])
            if distance <= radius_km:
                event["source"] = "event_calendars"
                events.append(event)

        return events

    async def _search_social_media(
        self, lat: float, lng: float, radius_km: int
    ) -> list[dict[str, Any]]:
        """
        Ищет события в социальных сетях (симуляция)
        """
        events = []

        # Симуляция поиска в соцсетях
        social_events = [
            {
                "title": "Встреча фотографов",
                "description": "Еженедельная встреча любителей фотографии",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 18:00",
                "location_name": "Кофейня 'У фотографа'",
                "lat": lat + 0.003,
                "lng": lng - 0.001,
            },
            {
                "title": "Йога в парке",
                "description": "Бесплатная йога для всех желающих",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 08:00",
                "location_name": "Сквер у метро",
                "lat": lat - 0.001,
                "lng": lng - 0.002,
            },
        ]

        for event in social_events:
            distance = self._haversine_km(lat, lng, event["lat"], event["lng"])
            if distance <= radius_km:
                event["source"] = "social_media"
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
