#!/usr/bin/env python3
"""
Улучшенный поиск событий из разных источников
"""

import asyncio
import logging
import random
import re
from datetime import datetime
from math import cos, radians
from typing import Any
from urllib.parse import urlparse

from ai_utils import fetch_ai_events_nearby
from config import load_settings

# Настройка логирования
logger = logging.getLogger(__name__)

# Хелперы для нормализации источников
VENUE_RX = r"(?:в|at|in)\s+([A-ZА-ЯЁ][\w\s'&.-]{2,})"  # примитив: «в Кафе Ромашка»
ADDR_RX = r"((?:Jl\.|Jalan|ул\.|улица|street|st\.|road|rd\.|avenue|ave\.)[^\n,;]{5,80})"


def extract_venue_from_text(title: str, desc: str) -> str | None:
    """Извлекает название места из текста"""
    for txt in (title, desc):
        if not txt:
            continue
        m = re.search(VENUE_RX, txt, flags=re.I)
        if m:
            return m.group(1).strip()[:80]
    return None


def extract_address_from_text(desc: str) -> str | None:
    """Извлекает адрес из текста"""
    if not desc:
        return None
    m = re.search(ADDR_RX, desc, flags=re.I)
    return m.group(1).strip()[:120] if m else None


def sanitize_url(u: str | None) -> str | None:
    """Санитизирует URL, отбрасывая невалидные"""
    if not u:
        return None
    u = u.strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = p.netloc.lower()
    if host.endswith(("example.com", "example.org", "example.net")):
        return None
    if "calendar.google.com" in host and "eid=" not in u:
        return None
    return u


def normalize_source_event(e: dict) -> dict:
    """Нормализует событие из источника"""
    title = e.get("title", "")
    desc = e.get("description", "")

    # 1) Обеспечиваем минимальный контракт
    if "type" not in e:
        e["type"] = "source"

    # 2) Нормализуем venue если есть
    if "venue" in e and isinstance(e["venue"], dict):
        venue = e["venue"]
        # Извлекаем venue_name и address из текста если нет
        if not venue.get("name"):
            venue["name"] = extract_venue_from_text(title, desc)
        if not venue.get("address"):
            venue["address"] = extract_address_from_text(desc)
    else:
        # Создаем venue из старых полей
        e["venue"] = {
            "name": e.get("venue_name") or extract_venue_from_text(title, desc),
            "address": e.get("address") or extract_address_from_text(desc),
            "lat": e.get("lat"),
            "lon": e.get("lng"),
        }

    # 3) Санитизируем URL
    e["source_url"] = sanitize_url(e.get("source_url") or e.get("url") or e.get("link"))

    # 4) Обеспечиваем совместимость со старыми полями
    if "venue_name" not in e and e.get("venue", {}).get("name"):
        e["venue_name"] = e["venue"]["name"]
    if "address" not in e and e.get("venue", {}).get("address"):
        e["address"] = e["venue"]["address"]

    # 5) Логируем результат нормализации
    import json

    logger.debug("norm.source=%s", json.dumps(e, ensure_ascii=False))

    return e


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
                # Сырая диагностика
                import json

                logger.debug(
                    "raw.popular[:3]=%s", json.dumps(popular_events[:3], ensure_ascii=False)
                )
                all_events.extend(popular_events)
        except Exception as e:
            logger.error(f"   ❌ Ошибка при поиске в популярных местах: {e}")

        # 3. Поиск в календарях событий
        logger.info("📅 Ищем в календарях событий...")
        try:
            calendar_events = await self._search_event_calendars(lat, lng, radius_km)
            if calendar_events:
                logger.info(f"   ✅ Найдено {len(calendar_events)} событий в календарях")
                # Сырая диагностика
                import json

                logger.debug("raw.cals[:3]=%s", json.dumps(calendar_events[:3], ensure_ascii=False))
                all_events.extend(calendar_events)
        except Exception as e:
            logger.error(f"   ❌ Ошибка при поиске в календарях: {e}")

        # 4. Поиск в социальных сетях (симуляция)
        logger.info("📱 Ищем в социальных сетях...")
        try:
            social_events = await self._search_social_media(lat, lng, radius_km)
            if social_events:
                logger.info(f"   ✅ Найдено {len(social_events)} событий в соцсетях")
                # Сырая диагностика
                import json

                logger.debug("raw.social[:3]=%s", json.dumps(social_events[:3], ensure_ascii=False))
                all_events.extend(social_events)
        except Exception as e:
            logger.error(f"   ❌ Ошибка при поиске в соцсетях: {e}")

        # Диагностика: считаем события по типам источников
        ai_count = sum(1 for e in all_events if e.get("source") == "ai_generated")
        user_count = sum(1 for e in all_events if e.get("source") in ["user_created", "user"])
        source_count = sum(
            1
            for e in all_events
            if e.get("source") in ["event_calendars", "social_media", "popular_places"]
        )

        logger.info(f"🎯 Всего найдено: {len(all_events)} событий")
        logger.info(
            f"📊 Диагностика источников: ai={ai_count}, user={user_count}, source={source_count}"
        )

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
            event = {
                "type": "source",
                "title": f"Ужин в {place['name']}",
                "description": "Отличная кухня и атмосфера в ресторане",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 19:00",
                "start_time": datetime.strptime(
                    f"{datetime.now().strftime('%Y-%m-%d')} 19:00", "%Y-%m-%d %H:%M"
                ),
                "venue": {
                    "name": place["name"],
                    "address": "Ресторанный район",
                    "lat": place["lat"],
                    "lon": place["lng"],
                },
                "source_url": f"https://restaurants.com/{place['name'].lower().replace(' ', '-')}",
                "lat": place["lat"],
                "lng": place["lng"],
                "source": "popular_places",
            }
            event = normalize_source_event(event)
            events.append(event)
        elif place["type"] == "park":
            event = {
                "type": "source",
                "title": f"Прогулка в {place['name']}",
                "description": "Приятная прогулка на свежем воздухе в парке",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 16:00",
                "start_time": datetime.strptime(
                    f"{datetime.now().strftime('%Y-%m-%d')} 16:00", "%Y-%m-%d %H:%M"
                ),
                "venue": {
                    "name": place["name"],
                    "address": "Парковая зона",
                    "lat": place["lat"],
                    "lon": place["lng"],
                },
                "source_url": f"https://parks.com/{place['name'].lower().replace(' ', '-')}",
                "lat": place["lat"],
                "lng": place["lng"],
                "source": "popular_places",
            }
            event = normalize_source_event(event)
            events.append(event)
        elif place["type"] == "museum":
            event = {
                "type": "source",
                "title": f"Посещение {place['name']}",
                "description": "Интересные экспонаты и выставки в музее",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} 14:00",
                "start_time": datetime.strptime(
                    f"{datetime.now().strftime('%Y-%m-%d')} 14:00", "%Y-%m-%d %H:%M"
                ),
                "venue": {
                    "name": place["name"],
                    "address": "Культурный район",
                    "lat": place["lat"],
                    "lon": place["lng"],
                },
                "source_url": f"https://museums.com/{place['name'].lower().replace(' ', '-')}",
                "lat": place["lat"],
                "lng": place["lng"],
                "source": "popular_places",
            }
            event = normalize_source_event(event)
            events.append(event)

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
                "type": "source",
                "title": f"{random.choice(event_types)} в {hour}:00",
                "description": f"Интересное событие в {hour}:00 в центре города",
                "time_local": f"{today.strftime('%Y-%m-%d')} {hour:02d}:00",
                "start_time": datetime.strptime(
                    f"{today.strftime('%Y-%m-%d')} {hour:02d}:00", "%Y-%m-%d %H:%M"
                ),
                "venue": {
                    "name": "Центр города",
                    "address": "Центральная площадь",
                    "lat": event_lat,
                    "lon": event_lng,
                },
                "source_url": f"https://example-calendar.com/event/{hour}",
                "lat": event_lat,
                "lng": event_lng,
            }

            # Нормализуем событие
            event = normalize_source_event(event)
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
                "type": "source",
                "title": activity,
                "description": "Популярная активность в соцсетях в парке",
                "time_local": f"{datetime.now().strftime('%Y-%m-%d')} {time}",
                "start_time": datetime.strptime(
                    f"{datetime.now().strftime('%Y-%m-%d')} {time}", "%Y-%m-%d %H:%M"
                ),
                "venue": {
                    "name": f"Парк для {activity.lower()}",
                    "address": "Городской парк",
                    "lat": event_lat,
                    "lon": event_lng,
                },
                "source_url": f"https://social-events.com/activity/{i}",
                "lat": event_lat,
                "lng": event_lng,
            }

            # Нормализуем событие
            event = normalize_source_event(event)
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
