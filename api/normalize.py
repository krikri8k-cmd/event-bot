#!/usr/bin/env python3
"""Нормализация и геокодинг событий"""

import os
from functools import lru_cache

import requests
from dateutil import parser as dateparser
from dateutil import tz

DEFAULT_TZ = tz.gettz(os.getenv("DEFAULT_TZ", "Asia/Makassar"))
GEOCODE_URL = os.getenv("GEOCODE_URL", "https://nominatim.openstreetmap.org/search")
GEOCODE_EMAIL = os.getenv("GEOCODE_EMAIL", "dev@local")


@lru_cache(maxsize=1000)
def reverse_geocode(lat: float, lon: float) -> dict[str, str | None]:
    """
    Возвращает {'city': 'Ubud', 'country': 'ID'} или пустой словарь.
    """
    try:
        email = os.getenv("GEOCODE_EMAIL") or "noreply@example.com"
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lon},
            headers={"User-Agent": f"event-bot/1 ({email})"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        addr = data.get("address", {})
        city = (
            addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality")
        )
        country = addr.get("country_code")  # двухбуквенный код
        return {"city": city, "country": country.upper() if country else None}
    except Exception:
        return {}


def to_utc_iso(value: str | None) -> str | None:
    """Превращает строку даты/времени в ISO Z (UTC). Возвращает None, если не распарсили."""
    if not value:
        return None
    try:
        dt_local = dateparser.parse(value)
        if not dt_local.tzinfo:
            dt_local = dt_local.replace(tzinfo=DEFAULT_TZ)
        return dt_local.astimezone(tz.UTC).isoformat()
    except Exception:
        return None


def geocode_one(
    query: str,
    lat: float | None = None,
    lon: float | None = None,
    email: str | None = None,
    timeout: int = 10,
) -> tuple[float | None, float | None]:
    """
    Лёгкий геокодинг через Nominatim (OSM).
    Возвращает tuple (lat, lon) или (None, None).
    """
    if not query:
        return (None, None)

    email = email or os.getenv("GEOCODE_EMAIL")
    ua = f"event-bot/1.0 ({email})" if email else "event-bot/1.0"
    headers = {"User-Agent": ua}

    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon

    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return (None, None)

        item = data[0]
        return float(item["lat"]), float(item["lon"])
    except Exception:
        return (None, None)


def normalize_event(event: dict) -> dict:
    """
    Нормализует событие, добавляя city и country если их нет
    """
    # Если city/country не заданы, пытаемся определить по координатам
    if not event.get("city") or not event.get("country"):
        if event.get("lat") and event.get("lng"):
            geo = reverse_geocode(event["lat"], event["lng"])
            event.setdefault("city", geo.get("city"))
            event.setdefault("country", geo.get("country"))

    # Устанавливаем organizer_url если нет organizer_id
    if not event.get("organizer_id") and event.get("url"):
        event.setdefault("organizer_url", event.get("url"))

    return event
