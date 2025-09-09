from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from config import load_settings


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Точная дистанция по сфере между двумя точками в километрах."""
    R = 6371.0088  # Более точное значение радиуса Земли
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


async def geocode_address(address: str) -> tuple[float, float] | None:
    settings = load_settings()
    if not settings.google_maps_api_key:
        return None
    params = {
        "address": address,
        "key": settings.google_maps_api_key,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return float(loc["lat"]), float(loc["lng"])
    return None


async def get_timezone(lat: float, lng: float, timestamp: int | None = None) -> str | None:
    settings = load_settings()
    if not settings.google_maps_api_key:
        return None
    if timestamp is None:
        timestamp = int(datetime.utcnow().timestamp())
    params = {
        "location": f"{lat:.6f},{lng:.6f}",
        "timestamp": timestamp,
        "key": settings.google_maps_api_key,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://maps.googleapis.com/maps/api/timezone/json", params=params)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == "OK":
            return data.get("timeZoneId")
    return None


def to_google_maps_link(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lng:.6f}"


def static_map_url(
    user_lat: float,
    user_lng: float,
    points: list[tuple[str, float, float]],
    zoom: int = 15,
    size: str = "800x600",
) -> str | None:
    settings = load_settings()
    if not settings.google_maps_api_key:
        return None
    key = settings.google_maps_api_key

    # Автоматически рассчитываем оптимальный зум на основе количества событий
    if len(points) > 12:
        zoom = max(11, zoom - 3)  # Уменьшаем зум для большого количества событий
    elif len(points) > 8:
        zoom = max(12, zoom - 2)  # Уменьшаем зум для большего количества событий
    elif len(points) > 4:
        zoom = max(13, zoom - 1)  # Немного уменьшаем зум

    # Пользователь (синяя метка с U)
    markers = [f"markers=color:blue%7Clabel:U%7C{user_lat:.6f},{user_lng:.6f}"]

    # События (красные метки с номерами)
    for label, lat, lng in points:
        # Проверяем что координаты валидные
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            safe_label = str(label) if label else "?"
            markers.append(f"markers=color:red%7Clabel:{safe_label}%7C{lat:.6f},{lng:.6f}")

    markers_str = "&".join(markers)
    return f"https://maps.googleapis.com/maps/api/staticmap?size={size}&zoom={zoom}&{markers_str}&key={key}"


def local_to_utc(time_local_str: str, tz_name: str) -> datetime | None:
    """Convert 'YYYY-MM-DD HH:MM' in tz_name to UTC-aware datetime."""
    try:
        naive = datetime.strptime(time_local_str, "%Y-%m-%d %H:%M")
        tz = ZoneInfo(tz_name)
        local_dt = naive.replace(tzinfo=tz)
        return local_dt.astimezone(ZoneInfo("UTC"))
    except Exception:
        return None


async def search_nearby_places(
    lat: float, lng: float, radius_meters: int = 5000, types: str = "establishment"
) -> list[dict]:
    """
    Ищет места поблизости через Google Places API
    """
    settings = load_settings()
    if not settings.google_maps_api_key:
        return []

    params = {
        "location": f"{lat:.6f},{lng:.6f}",
        "radius": radius_meters,
        "type": types,
        "key": settings.google_maps_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json", params=params
            )
            r.raise_for_status()
            data = r.json()

            if data.get("status") == "OK":
                places = []
                for place in data.get("results", []):
                    places.append(
                        {
                            "name": place.get("name", ""),
                            "lat": place.get("geometry", {}).get("location", {}).get("lat"),
                            "lng": place.get("geometry", {}).get("location", {}).get("lng"),
                            "types": place.get("types", []),
                            "rating": place.get("rating"),
                            "vicinity": place.get("vicinity", ""),
                            "place_id": place.get("place_id", ""),
                        }
                    )
                return places
    except Exception as e:
        print(f"Ошибка при поиске мест: {e}")

    return []


def get_bbox(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    """
    Вычисляет bounding box для заданных координат и радиуса в километрах.
    Возвращает (min_lat, min_lng, max_lat, max_lng).
    """
    # Приблизительно: 1 градус широты ≈ 111 км
    # 1 градус долготы ≈ 111 * cos(lat) км
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / (111.0 * math.cos(math.radians(lat)))

    min_lat = lat - lat_delta
    max_lat = lat + lat_delta
    min_lng = lng - lng_delta
    max_lng = lng + lng_delta

    return min_lat, min_lng, max_lat, max_lng


async def search_events_places(lat: float, lng: float, radius_km: int = 5) -> list[dict]:
    """
    Ищет места, где могут проходить события
    """
    event_types = [
        "museum",
        "art_gallery",
        "movie_theater",
        "stadium",
        "amusement_park",
        "park",
        "restaurant",
        "bar",
        "cafe",
    ]

    all_places = []
    for place_type in event_types:
        places = await search_nearby_places(lat, lng, radius_km * 1000, place_type)
        all_places.extend(places)

    return all_places


def bbox_around(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Грубая рамка вокруг точки для первичного отбора (ускоряет запрос)."""
    lat_delta = radius_km / 110.574  # км в градусах широты
    lon_delta = radius_km / (111.320 * math.cos(math.radians(lat)) or 1e-9)
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)


def inside_bbox(lat: float, lon: float, bbox: dict[str, float]) -> bool:
    """Проверяет, находится ли точка внутри bounding box."""
    return (bbox["min_lat"] <= lat <= bbox["max_lat"]) and (
        bbox["min_lon"] <= lon <= bbox["max_lon"]
    )


def find_user_region(lat: float, lon: float, geo_bboxes: dict[str, dict[str, float]]) -> str:
    """Определяет регион пользователя по координатам."""
    for name, bb in geo_bboxes.items():
        if inside_bbox(lat, lon, bb):
            return name
    return "unknown"


def validate_coordinates(lat: float, lon: float) -> bool:
    """Проверяет корректность координат."""
    return -90 <= lat <= 90 and -180 <= lon <= 180
