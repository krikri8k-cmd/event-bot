from __future__ import annotations

import math
import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin
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


async def geocode_address(address: str, region_bias: str = "bali") -> tuple[float, float] | None:
    settings = load_settings()
    if not settings.google_maps_api_key:
        return None

    # Простой геокодинг без сложной логики привязки к регионам
    # Google Maps API сам определит правильные координаты
    params = {
        "address": address,
        "key": settings.google_maps_api_key,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
        r.raise_for_status()
        data = r.json()

        print(
            f"🌍 Google Geocoding API ответ: status={data.get('status')}, results_count={len(data.get('results', []))}"
        )

        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            lat, lng = float(loc["lat"]), float(loc["lng"])
            print(f"✅ Геокодирование успешно: {lat}, {lng}")
            return lat, lng
        else:
            print(f"❌ Геокодирование не удалось: {data.get('status')}, {data.get('error_message', '')}")

    return None


async def reverse_geocode(lat: float, lng: float) -> str | None:
    """
    Выполняет reverse geocoding для получения названия места по координатам

    Args:
        lat: Широта
        lng: Долгота

    Returns:
        Название места (establishment name) или None если не найдено
    """
    settings = load_settings()
    if not settings.google_maps_api_key:
        return None

    params = {
        "latlng": f"{lat:.6f},{lng:.6f}",
        "key": settings.google_maps_api_key,
        "result_type": "establishment|premise|point_of_interest",  # Приоритет на заведения
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
            r.raise_for_status()
            data = r.json()

            if data.get("status") == "OK" and data.get("results"):
                # Ищем название заведения (establishment)
                for result in data.get("results", []):
                    # Проверяем типы результатов
                    types = result.get("types", [])
                    # Ищем establishment, premise, point_of_interest
                    if any(t in types for t in ["establishment", "premise", "point_of_interest"]):
                        # Сначала пробуем найти название в address_components (более точное)
                        name = None
                        for component in result.get("address_components", []):
                            if "establishment" in component.get("types", []):
                                name = component.get("long_name", "")
                                break

                        # Если не нашли в address_components, используем formatted_address
                        # Но берем только первую часть (до запятой), чтобы убрать адрес
                        if not name:
                            formatted_address = result.get("formatted_address", "")
                            if formatted_address:
                                # Берем первую часть до запятой (обычно это название места)
                                name = formatted_address.split(",")[0].strip()

                        if name:
                            return name

                # Если не нашли establishment, берем первое место
                # И берем только первую часть адреса (название места)
                first_result = data.get("results", [{}])[0]
                formatted_address = first_result.get("formatted_address", "")
                if formatted_address:
                    # Берем первую часть до запятой
                    name = formatted_address.split(",")[0].strip()
                    return name

    except Exception as e:
        print(f"❌ Ошибка reverse geocoding: {e}")

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
            r = await client.get("https://maps.googleapis.com/maps/api/place/nearbysearch/json", params=params)
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
    return (bbox["min_lat"] <= lat <= bbox["max_lat"]) and (bbox["min_lon"] <= lon <= bbox["max_lon"])


def find_user_region(lat: float, lon: float, geo_bboxes: dict[str, dict[str, float]]) -> str:
    """Определяет регион пользователя по координатам."""
    for name, bb in geo_bboxes.items():
        if inside_bbox(lat, lon, bb):
            return name
    return "unknown"


def validate_coordinates(lat: float, lon: float) -> bool:
    """Проверяет корректность координат."""
    return -90 <= lat <= 90 and -180 <= lon <= 180


async def parse_google_maps_link(link: str) -> dict | None:
    """
    Парсит Google Maps ссылку и извлекает координаты и название места.

    Поддерживает форматы:
    - https://maps.google.com/maps?q=lat,lng
    - https://www.google.com/maps/place/name/@lat,lng,zoom
    - https://maps.google.com/?q=lat,lng
    - https://goo.gl/maps/...
    - https://maps.app.goo.gl/...

    Returns:
        dict с ключами: lat, lng, name, raw_link или None если не удалось распарсить
    """
    if not link or not isinstance(link, str):
        return None

    # Очищаем ссылку
    link = link.strip()
    # Удаляем все пробельные символы внутри ссылки (часто встречаются при вставке из мобильных приложений)
    link = re.sub(r"\s+", "", link)

    try:
        # Сначала проверяем, не короткая ли это ссылка
        if "goo.gl/maps" in link or "maps.app.goo.gl" in link:
            # Для коротких ссылок пытаемся получить полную ссылку
            expanded_link = await expand_short_url(link)
            if expanded_link:
                print(f"🔗 Расширили короткую ссылку: {link} -> {expanded_link}")
                link = expanded_link
            else:
                print(f"⚠️ Не удалось расширить короткую ссылку: {link}")
                # Для коротких ссылок без координат возвращаем ссылку для геокодирования
                return {"lat": None, "lng": None, "name": "Место на карте", "raw_link": link}

        # Паттерн 1: @lat,lng,zoom (самый частый)
        pattern1 = r"@(-?\d+\.?\d*),(-?\d+\.?\d*),\d+"
        match1 = re.search(pattern1, link)
        if match1:
            lat = float(match1.group(1))
            lng = float(match1.group(2))

            # Пытаемся извлечь название из URL
            name = extract_place_name_from_url(link)

            return {"lat": lat, "lng": lng, "name": name, "raw_link": link}

        # Паттерн 2: q=lat,lng
        pattern2 = r"[?&]q=(-?\d+\.?\d*),(-?\d+\.?\d*)"
        match2 = re.search(pattern2, link)
        if match2:
            lat = float(match2.group(1))
            lng = float(match2.group(2))

            name = extract_place_name_from_url(link)

            return {"lat": lat, "lng": lng, "name": name, "raw_link": link}

        # Паттерн 3: ll=lat,lng
        pattern3 = r"[?&]ll=(-?\d+\.?\d*),(-?\d+\.?\d*)"
        match3 = re.search(pattern3, link)
        if match3:
            lat = float(match3.group(1))
            lng = float(match3.group(2))

            name = extract_place_name_from_url(link)

            return {"lat": lat, "lng": lng, "name": name, "raw_link": link}

        # Паттерн 4: center=lat,lng
        pattern4 = r"[?&]center=(-?\d+\.?\d*),(-?\d+\.?\d*)"
        match4 = re.search(pattern4, link)
        if match4:
            lat = float(match4.group(1))
            lng = float(match4.group(2))

            name = extract_place_name_from_url(link)

            return {"lat": lat, "lng": lng, "name": name, "raw_link": link}

        # Паттерн 5: 3d=lat&4d=lng (новый формат Google Maps)
        pattern5 = r"3d=(-?\d+\.?\d*).*?4d=(-?\d+\.?\d*)"
        match5 = re.search(pattern5, link)
        if match5:
            lat = float(match5.group(1))
            lng = float(match5.group(2))
            print(f"🎯 Найдены координаты в формате 3d/4d: {lat}, {lng}")

            name = extract_place_name_from_url(link)

            return {"lat": lat, "lng": lng, "name": name, "raw_link": link}

        # Паттерн 6: ссылка на конкретное место (без координат в URL)
        if "/place/" in link:
            name = extract_place_name_from_url(link)
            if name:
                # Для мест без координат в URL возвращаем только название
                # Координаты можно будет получить позже через геокодирование
                return {"lat": None, "lng": None, "name": name, "raw_link": link}

        # Паттерн 7: короткие ссылки без координат - пытаемся извлечь название
        if "goo.gl/maps" in link or "maps.app.goo.gl" in link:
            # Для коротких ссылок без координат возвращаем ссылку для геокодирования
            return {"lat": None, "lng": None, "name": None, "raw_link": link}

        return None

    except (ValueError, AttributeError):
        return None


async def expand_short_url(short_url: str) -> str | None:
    """Расширяет короткую ссылку Google Maps до полной."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        )
    }

    try:
        # Делаем HEAD запрос, чтобы получить редирект (если сервис это поддерживает)
        async with httpx.AsyncClient(follow_redirects=False, timeout=10, headers=headers) as client:
            response = await client.head(short_url)

        if response.status_code in [301, 302, 303, 307, 308]:
            location = response.headers.get("location")
            if location:
                return urljoin(short_url, location)
    except Exception:
        # Переходим к fallback ниже
        pass

    try:
        # Некоторые короткие ссылки (особенно maps.app.goo.gl) требуют полноценного GET
        async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers=headers) as client:
            response = await client.get(short_url)

        final_url = str(response.url)
        if final_url and final_url != short_url:
            return final_url

        # Если редиректа не произошло, пытаемся извлечь ссылку из HTML/JS ответа
        if response.text:
            html = unescape(response.text)
            candidate_patterns = [
                r'window\.location(?:\.href|\.assign)?\s*=\s*"([^"]+)"',
                r"window\.location(?:\.href|\.assign)?\s*=\s*'([^']+)'",
                r'<meta[^>]+content="0;url=([^"]+)"',
                r'<a[^>]+href="([^"]+)"',
                r'data-href="([^"]+)"',
            ]

            for pattern in candidate_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    if candidate.startswith("//"):
                        candidate = f"https:{candidate}"
                    if candidate.startswith("/"):
                        candidate = urljoin(short_url, candidate)
                    if "google." in candidate and "maps" in candidate:
                        return candidate

            # Последняя попытка: ищем любой Google Maps URL в тексте
            generic_match = re.search(r"https://www\.google\.[^\"'<>]*maps[^\"'<>]*", html)
            if generic_match:
                return generic_match.group(0)

        return None
    except Exception:
        return None


def geocode_place_name(place_name: str) -> dict | None:
    """Геокодирует название места в координаты."""
    try:
        import asyncio

        from utils.geo_utils import geocode_address

        # Запускаем асинхронную функцию
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(geocode_address(place_name))
            if result and "lat" in result and "lng" in result:
                return {"lat": result["lat"], "lng": result["lng"]}
        finally:
            loop.close()
        return None
    except Exception:
        return None


def extract_place_name_from_url(url: str) -> str | None:
    """Извлекает название места из Google Maps URL."""
    try:
        import urllib.parse

        # Паттерн для /place/name/
        place_pattern = r"/place/([^/@]+)"
        match = re.search(place_pattern, url)
        if match:
            name = match.group(1)
            # Декодируем URL-кодированные символы
            name = urllib.parse.unquote(name)
            return name

        return None
    except Exception:
        return None
