"""
Meetup API интеграция
"""

import asyncio
import datetime as dt

import httpx

from api.oauth_meetup import MeetupOAuth
from config import load_settings
from event_apis import RawEvent
from utils.geo_utils import get_bbox


async def fetch(lat: float, lng: float, radius_km: float = 5.0) -> list[RawEvent]:
    """
    Получает события из Meetup API в заданном радиусе
    """
    settings = load_settings()

    if not settings.meetup_api_key:
        print("⚠️ MEETUP_API_KEY не настроен, возвращаем пустой список")
        return []

    # Вычисляем bounding box для оптимизации запроса
    min_lat, min_lng, max_lat, max_lng = get_bbox(lat, lng, radius_km)

    # Meetup API endpoint
    url = "https://api.meetup.com/find/upcoming_events"

    params = {
        "lat": lat,
        "lon": lng,
        "radius": radius_km,
        "fields": "group_key_photo",
        "page": 50,
    }

    # Используем OAuth если доступен, иначе fallback на API key
    headers = {}
    oauth_mgr = MeetupOAuth()
    if oauth_mgr.headers():
        headers = oauth_mgr.headers()
        print("🔐 Используем OAuth авторизацию для Meetup")
    elif settings.meetup_api_key:
        params["key"] = settings.meetup_api_key
        print("🔑 Используем API key для Meetup")
    else:
        print("⚠️ Ни OAuth токены, ни API key не настроены")
        return []

    # Retry логика с экспоненциальной задержкой
    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

                events = []
                for event_data in data.get("events", []):
                    try:
                        event = _normalize_event(event_data)
                        if event:
                            events.append(event)
                    except Exception as e:
                        print(f"Ошибка нормализации события: {e}")
                        continue

                print(f"📅 Meetup: найдено {len(events)} событий")
                return events

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:  # Rate limit
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    print(f"⚠️ Rate limit, retry {attempt + 1}/{max_retries} через {delay}s")
                    await asyncio.sleep(delay)
                    continue
            elif e.response.status_code >= 500:  # Server error
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    print(f"⚠️ Server error {e.response.status_code}, retry {attempt + 1}/{max_retries} через {delay}s")
                    await asyncio.sleep(delay)
                    continue
            print(f"❌ HTTP ошибка Meetup API: {e}")
            return []

        except Exception as e:
            print(f"❌ Ошибка Meetup API: {e}")
            return []

    print(f"❌ Meetup API: все {max_retries} попытки исчерпаны")
    return []


def _normalize_event(event_data: dict) -> RawEvent | None:
    """
    Нормализует событие из Meetup API в RawEvent
    """
    try:
        # Извлекаем данные события
        title = event_data.get("name", "").strip()
        if not title:
            return None

        # Координаты из venue
        venue = event_data.get("venue", {})
        event_lat = venue.get("lat")
        event_lng = venue.get("lon")

        # Если нет venue, используем координаты группы
        if event_lat is None or event_lng is None:
            group = event_data.get("group", {})
            event_lat = group.get("lat")
            event_lng = group.get("lon")

        if event_lat is None or event_lng is None:
            return None

        # Время события
        starts_at = None
        if event_data.get("local_date") and event_data.get("local_time"):
            try:
                date_str = f"{event_data['local_date']} {event_data['local_time']}"
                # Meetup использует локальное время, но мы сохраняем как есть
                # В реальном приложении нужно конвертировать в UTC
                starts_at = dt.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            except ValueError:
                pass

        # URL события
        url = event_data.get("link")

        # Описание
        description = event_data.get("description", "")
        if description:
            description = description[:500]  # Ограничиваем длину

        return RawEvent(
            title=title,
            lat=float(event_lat),
            lng=float(event_lng),
            starts_at=starts_at,
            source="meetup",
            external_id=str(event_data.get("id")),
            url=url,
            description=description,
        )

    except Exception as e:
        print(f"Ошибка парсинга события Meetup: {e}")
        return None
