#!/usr/bin/env python3
"""
Интеграция с различными API для поиска реальных событий
"""

import asyncio
from datetime import datetime
from typing import Any

import httpx

from config import load_settings


async def search_eventbrite_events(
    lat: float, lng: float, radius_km: int = 5
) -> list[dict[str, Any]]:
    """
    Ищет события через Eventbrite API
    """
    settings = load_settings()

    if not settings.eventbrite_api_key:
        print("❌ Eventbrite API ключ не найден")
        return []

    # Eventbrite API (бесплатный)
    url = "https://www.eventbriteapi.com/v3/events/search/"

    # Радиус в милях (Eventbrite использует мили)
    radius_miles = int(radius_km * 0.621371)

    params = {
        "location.latitude": lat,
        "location.longitude": lng,
        "location.within": f"{radius_miles}mi",
        "start_date.range_start": datetime.now().isoformat(),
        "expand": "venue",
        "status": "live",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()

            events = []
            for event in data.get("events", []):
                venue = event.get("venue", {})
                events.append(
                    {
                        "title": event.get("name", {}).get("text", ""),
                        "description": event.get("description", {}).get("text", "")[:500],
                        "time_local": event.get("start", {}).get("local", ""),
                        "location_name": venue.get("name", ""),
                        "lat": venue.get("latitude"),
                        "lng": venue.get("longitude"),
                        "url": event.get("url", ""),
                        "source": "eventbrite",
                    }
                )

            return events

    except Exception as e:
        print(f"Ошибка Eventbrite API: {e}")
        return []


# Facebook Events API больше не поддерживает поиск публичных мероприятий
# Удалено из-за ограничений Facebook Graph API v5.0+


async def search_meetup_events(lat: float, lng: float, radius_km: int = 5) -> list[dict[str, Any]]:
    """
    Ищет события через Meetup API
    """
    # Meetup API (бесплатный, но требует API ключ)
    url = "https://api.meetup.com/find/upcoming_events"

    params = {"lat": lat, "lon": lng, "radius": radius_km, "page": 20}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()

            events = []
            for event in data.get("events", []):
                venue = event.get("venue", {})
                events.append(
                    {
                        "title": event.get("name", ""),
                        "description": event.get("description", "")[:500],
                        "time_local": event.get("local_date")
                        + " "
                        + event.get("local_time", "00:00"),
                        "location_name": venue.get("name", ""),
                        "lat": venue.get("lat"),
                        "lng": venue.get("lon"),
                        "url": event.get("link", ""),
                        "source": "meetup",
                    }
                )

            return events

    except Exception as e:
        print(f"Ошибка Meetup API: {e}")
        return []


async def search_all_real_events(
    lat: float, lng: float, radius_km: int = 5
) -> list[dict[str, Any]]:
    """
    Ищет события из всех доступных API
    """
    print("🔍 Ищем реальные события из всех источников...")

    all_events = []

    # Facebook Events API больше не поддерживает поиск публичных мероприятий

    # Eventbrite
    print("📅 Ищем в Eventbrite...")
    eventbrite_events = await search_eventbrite_events(lat, lng, radius_km)
    if eventbrite_events:
        print(f"   ✅ Найдено {len(eventbrite_events)} событий в Eventbrite")
        all_events.extend(eventbrite_events)

    # Meetup
    print("👥 Ищем в Meetup...")
    meetup_events = await search_meetup_events(lat, lng, radius_km)
    if meetup_events:
        print(f"   ✅ Найдено {len(meetup_events)} событий в Meetup")
        all_events.extend(meetup_events)

    print(f"🎯 Всего найдено реальных событий: {len(all_events)}")
    return all_events


if __name__ == "__main__":
    # Тест
    async def test():
        events = await search_all_real_events(55.7558, 37.6176, 5)
        for i, event in enumerate(events[:5], 1):
            print(f"{i}. {event['title']} - {event['source']}")

    asyncio.run(test())
