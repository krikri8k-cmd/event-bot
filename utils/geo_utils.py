from __future__ import annotations

import math
import re
from datetime import datetime
from html import unescape
from urllib.parse import parse_qs, unquote, urljoin, urlparse
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


async def geocode_address(
    address: str, region_bias: str = "bali", language: str | None = None
) -> tuple[float, float] | None:
    settings = load_settings()
    if not settings.google_maps_api_key:
        return None

    # Простой геокодинг без сложной логики привязки к регионам
    # language: язык ответа (en, ru) — названия мест вернутся на выбранном языке
    params = {
        "address": address,
        "key": settings.google_maps_api_key,
    }
    if language:
        params["language"] = language

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


def _is_address(name: str) -> bool:
    """
    Проверяет, является ли строка адресом, а не названием заведения
    """
    if not name:
        return True

    name_lower = name.lower().strip()

    # Plus Codes (формат XXXX+XXX) - точно адрес
    if len(name) <= 10 and "+" in name and name.replace("+", "").replace(" ", "").isalnum():
        return True

    # Адреса начинаются с улиц (строгая проверка)
    address_prefixes = [
        "jl. ",
        "jalan ",
        "gg. ",
        "gang ",
        "ул. ",
        "улица ",
        "street ",
        "st. ",
        "avenue ",
        "ave. ",
        "проспект ",
        "просп. ",
        "бульвар ",
        "бул. ",
        "переулок ",
        "пер. ",
    ]

    for prefix in address_prefixes:
        if name_lower.startswith(prefix):
            return True

    # Адреса содержат номера домов (строгая проверка)
    if any(pattern in name_lower for pattern in [" no.", " no ", " номер ", " #", " number "]):
        return True

    # Слишком короткие
    if len(name) < 3:
        return True

    # Слишком длинные (вероятно полный адрес)
    if len(name) > 80:
        return True

    return False


async def reverse_geocode(lat: float, lng: float, language: str | None = None) -> str | None:
    """
    Выполняет reverse geocoding для получения названия места по координатам.

    Args:
        lat: Широта
        lng: Долгота
        language: Язык ответа API (en, ru) — названия мест вернутся на выбранном языке

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
    if language:
        params["language"] = language

    try:
        # Сначала пробуем Places API для получения названия заведения
        try:
            places_params = {
                "location": f"{lat:.6f},{lng:.6f}",
                "radius": "100",  # 100 метров
                "key": settings.google_maps_api_key,
                "type": "establishment|point_of_interest",
            }
            if language:
                places_params["language"] = language
            async with httpx.AsyncClient(timeout=15) as client:
                places_r = await client.get(
                    "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                    params=places_params,
                )
                places_r.raise_for_status()
                places_data = places_r.json()

                if places_data.get("status") == "OK" and places_data.get("results"):
                    # Берем ближайшее заведение
                    for place in places_data.get("results", [])[:3]:  # Проверяем первые 3
                        name = place.get("name", "").strip()
                        if name and not _is_address(name):
                            return name
        except Exception:
            # Если Places API не сработал, продолжаем с Geocoding API
            pass

        # Используем Geocoding API как fallback
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://maps.googleapis.com/maps/api/geocode/json", params=params)
            r.raise_for_status()
            data = r.json()

            if data.get("status") == "OK" and data.get("results"):
                candidates = []

                # Ищем название заведения (establishment)
                for result in data.get("results", []):
                    # Проверяем типы результатов
                    types = result.get("types", [])
                    # Ищем establishment, premise, point_of_interest
                    if any(t in types for t in ["establishment", "premise", "point_of_interest"]):
                        # 1. Пробуем найти название в address_components (более точное)
                        for component in result.get("address_components", []):
                            if "establishment" in component.get("types", []):
                                name = component.get("long_name", "").strip()
                                if name and not _is_address(name):
                                    candidates.append((name, 3))  # Высокий приоритет
                                break

                        # 2. Используем name из result (если есть)
                        if "name" in result:
                            name = result.get("name", "").strip()
                            if name and not _is_address(name):
                                candidates.append((name, 2))  # Средний приоритет

                            # 3. Используем formatted_address (но фильтруем адреса)
                            formatted_address = result.get("formatted_address", "")
                            if formatted_address:
                                # Берем первую часть до запятой
                                name = formatted_address.split(",")[0].strip()
                            if name and not _is_address(name):
                                candidates.append((name, 1))  # Низкий приоритет

                # Если нашли кандидатов, возвращаем лучший (с наивысшим приоритетом)
                if candidates:
                    # Сортируем по приоритету (от большего к меньшему)
                    candidates.sort(key=lambda x: x[1], reverse=True)
                    return candidates[0][0]

                # Если не нашли establishment, пробуем все результаты
                # Но фильтруем только явные адреса
                for result in data.get("results", []):
                    # Пробуем name из result
                    if "name" in result:
                        name = result.get("name", "").strip()
                        if name and not _is_address(name):
                            return name

                    # Пробуем formatted_address (но только если не похоже на адрес)
                    formatted_address = result.get("formatted_address", "")
                if formatted_address:
                    name = formatted_address.split(",")[0].strip()
                    # Более мягкая проверка - принимаем, если не явный адрес и не слишком длинный
                    if name and len(name) > 5 and len(name) < 50 and not _is_address(name):
                        return name
                    # Если это короткий адрес без "No.", принимаем его (лучше чем координаты)
                    elif name and len(name) > 5 and len(name) < 40:
                        # Проверяем, что это не Plus Code и не содержит номер дома
                        if not (len(name) <= 10 and "+" in name) and " no." not in name.lower():
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


def to_google_maps_link(lat: float, lng: float, place_id: str | None = None) -> str:
    """
    Создает ссылку на Google Maps.
    Если есть place_id, использует ссылку на конкретное место.
    Иначе использует координаты.
    """
    if place_id:
        # Используем ссылку на конкретное место с place_id
        return f"https://www.google.com/maps/place/?q=place_id:{place_id}"
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


async def get_coordinates_from_place_id(place_id: str) -> tuple[float, float] | None:
    """
    Получает координаты места по place_id через Google Places API Details.
    Если place_id является ftid (начинается с 0x), возвращает None (ftid не поддерживается Places API).
    """
    # Проверяем, является ли это ftid (формат 0x...:0x...)
    if place_id.startswith("0x") and ":" in place_id:
        # ftid не поддерживается Places API Details напрямую
        return None

    settings = load_settings()
    if not settings.google_maps_api_key:
        return None

    params = {
        "place_id": place_id,
        "fields": "geometry,name",
        "key": settings.google_maps_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://maps.googleapis.com/maps/api/place/details/json", params=params)
            r.raise_for_status()
            data = r.json()

            if data.get("status") == "OK" and data.get("result"):
                geometry = data["result"].get("geometry", {})
                location = geometry.get("location", {})
                if location.get("lat") and location.get("lng"):
                    lat = float(location["lat"])
                    lng = float(location["lng"])
                    return lat, lng
    except Exception as e:
        print(f"Ошибка при получении координат по place_id: {e}")

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


def _cleanup_link(link: str) -> str:
    """Удаляет пробелы и нормализует ссылку."""
    link = link.strip()
    return re.sub(r"\s+", "", link)


def _extract_place_id(url: str) -> str | None:
    """Ищет place_id/cid/ftid внутри URL."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    # Ищем в query параметрах (включая query_place_id для нового формата)
    for key in ("place_id", "placeid", "ftid", "query_place_id"):
        values = query.get(key)
        if values:
            return values[0]

    cid_values = query.get("cid")
    if cid_values:
        return cid_values[0]

    # Ищем в параметре data (новый формат Google Maps)
    data_values = query.get("data")
    if data_values:
        data_param = data_values[0]
        # Ищем !1s... в параметре data
        data_match = re.search(r"!1s([^!]+)", data_param)
        if data_match:
            candidate = data_match.group(1)
            if candidate and candidate not in {"0", "1"}:
                return candidate

    # Ищем !1s... напрямую в URL
    data_matches = re.findall(r"!1s([^!]+)", url)
    for candidate in data_matches:
        if candidate and candidate not in {"0", "1"}:
            return candidate

    return None


def _extract_place_name_from_data(url: str) -> str | None:
    """Пытается вытащить название места из последовательностей вида !3m5!1s..."""
    match = re.search(r"!3m5!1s([^!]+)", url)
    if not match:
        return None

    candidate = match.group(1)

    try:
        import urllib.parse

        decoded = urllib.parse.unquote(candidate)
        return decoded.replace("+", " ")
    except Exception:
        return candidate


def _extract_maps_url_from_html(html: str, base_url: str) -> str | None:
    """Пытается найти полноценную Google Maps ссылку внутри HTML."""
    if not html:
        return None

    html_unescaped = unescape(html)

    direct_match = re.search(r"https://www\.google\.[^\"'<>]*maps[^\"'<>]*", html_unescaped)
    if direct_match:
        return direct_match.group(0)

    es5_match = re.search(r"window\.ES5DGURL\s*=\s*['\"]([^'\"]+)['\"]", html)
    if es5_match:
        raw_candidate = es5_match.group(1)
        try:
            decoded = raw_candidate.encode("utf-8").decode("unicode_escape")
        except Exception:
            decoded = raw_candidate
        candidate = unescape(decoded)
        try:
            import urllib.parse

            candidate = urllib.parse.unquote(candidate)
        except Exception:
            pass
        if candidate.startswith("//"):
            candidate = f"https:{candidate}"
        if candidate.startswith("/"):
            candidate = urljoin(base_url, candidate)
        if "google." in candidate and "maps" in candidate:
            return candidate

    return None


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

    # Очищаем ссылку от пробелов и скрытых символов
    link_cleaned = _cleanup_link(link)
    link = unquote(link_cleaned)

    try:
        # Сначала проверяем паттерн query=lat,lng (после декодирования)
        # Это нужно делать ДО проверки коротких ссылок, так как короткие ссылки могут расширяться
        pattern_query_decoded = r"[?&]query=(-?\d+\.?\d*),(-?\d+\.?\d*)"
        match_query = re.search(pattern_query_decoded, link)
        if match_query:
            lat = float(match_query.group(1))
            lng = float(match_query.group(2))
            # Пытаемся извлечь place_id из ссылки для получения названия
            place_id = _extract_place_id(link) or _extract_place_id(link_cleaned)
            name = extract_place_name_from_url(link)

            # Если есть place_id, но нет названия, получаем название через PlaceResolver
            if place_id and not name:
                try:
                    from database import get_engine
                    from utils.place_resolver import PlaceResolver

                    engine = get_engine()
                    resolver = PlaceResolver(engine=engine)
                    place_data = await resolver.get_place_details(place_id)
                    if place_data and place_data.get("name"):
                        name = place_data["name"]
                except Exception:
                    # Если PlaceResolver не доступен, продолжаем без названия
                    pass

            result = {"lat": lat, "lng": lng, "name": name, "raw_link": link}
            if place_id:
                result["place_id"] = place_id
            return result

        # Также проверяем паттерн query=lat%2Clng (до декодирования, если еще не декодировано)
        pattern_query_encoded = r"[?&]query=(-?\d+\.?\d*)%2C(-?\d+\.?\d*)"
        match_query_encoded = re.search(pattern_query_encoded, link_cleaned)
        if match_query_encoded:
            lat = float(match_query_encoded.group(1))
            lng = float(match_query_encoded.group(2))
            # Пытаемся извлечь place_id из ссылки для получения названия
            place_id = _extract_place_id(link) or _extract_place_id(link_cleaned)
            name = extract_place_name_from_url(link)

            # Если есть place_id, но нет названия, получаем название через PlaceResolver
            if place_id and not name:
                try:
                    from database import get_engine
                    from utils.place_resolver import PlaceResolver

                    engine = get_engine()
                    resolver = PlaceResolver(engine=engine)
                    place_data = await resolver.get_place_details(place_id)
                    if place_data and place_data.get("name"):
                        name = place_data["name"]
                except Exception:
                    # Если PlaceResolver не доступен, продолжаем без названия
                    pass

            result = {"lat": lat, "lng": lng, "name": name, "raw_link": link}
            if place_id:
                result["place_id"] = place_id
            return result

        # Сначала проверяем, не короткая ли это ссылка
        if "goo.gl/maps" in link or "maps.app.goo.gl" in link:
            # Для коротких ссылок пытаемся получить полную ссылку
            expanded_link = await expand_short_url(link)
            if expanded_link:
                print(f"🔗 Расширили короткую ссылку: {link} -> {expanded_link}")
                link = unquote(expanded_link)
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

        # Паттерн 2: q=lat,lng или q=адрес
        pattern2 = r"[?&]q=(-?\d+\.?\d*),(-?\d+\.?\d*)"
        match2 = re.search(pattern2, link)
        if match2:
            lat = float(match2.group(1))
            lng = float(match2.group(2))

            name = extract_place_name_from_url(link)

            return {"lat": lat, "lng": lng, "name": name, "raw_link": link}

        # Паттерн 2a: query=lat%2Clng (URL-encoded запятая) - новый формат Google Maps
        pattern2a = r"[?&]query=(-?\d+\.?\d*)%2C(-?\d+\.?\d*)"
        match2a = re.search(pattern2a, link)
        if match2a:
            lat = float(match2a.group(1))
            lng = float(match2a.group(2))

            name = extract_place_name_from_url(link)

            return {"lat": lat, "lng": lng, "name": name, "raw_link": link}

        # Паттерн 2b: q=адрес (не координаты) - извлекаем адрес для геокодирования
        pattern2b = r"[?&]q=([^&]+)"
        match2b = re.search(pattern2b, link)
        if match2b:
            query = unquote(match2b.group(1))
            # Проверяем, что это не координаты (должно быть что-то вроде адреса)
            if not re.match(r"^-?\d+\.?\d*,-?\d+\.?\d*$", query):
                # Это адрес, нужно геокодировать
                coords = await geocode_address(query)
                if coords:
                    lat, lng = coords
                    # Извлекаем название из адреса (первая часть до запятой)
                    name = query.split(",")[0].strip() if "," in query else query
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
            name = extract_place_name_from_url(link) or _extract_place_name_from_data(link)
            place_id = _extract_place_id(link)

            # Проверяем, является ли place_id ftid (формат 0x...:0x...)
            is_ftid = place_id and place_id.startswith("0x") and ":" in place_id

            # Если это не ftid, пытаемся получить координаты через Places API
            if place_id and not is_ftid:
                coords = await get_coordinates_from_place_id(place_id)
                if coords:
                    lat, lng = coords
                    return {
                        "lat": lat,
                        "lng": lng,
                        "name": name or "Место на карте",
                        "raw_link": link,
                        "place_id": place_id,
                    }

            # Если ftid или не удалось получить координаты по place_id, пробуем геокодировать по названию
            if name:
                # Декодируем название и пробуем геокодировать
                decoded_name = unquote(name.replace("+", " "))
                # Убираем лишние части из названия (например, адрес после названия места)
                # Берем только первую часть до запятой или до первого числа
                clean_name = decoded_name.split(",")[0].strip()
                if not clean_name:
                    clean_name = decoded_name

                coords = await geocode_address(clean_name)
                if coords:
                    lat, lng = coords
                    return {
                        "lat": lat,
                        "lng": lng,
                        "name": clean_name,
                        "raw_link": link,
                    }

                # Если геокодирование не сработало, возвращаем без координат
                result = {"lat": None, "lng": None, "name": clean_name, "raw_link": link}
                if place_id:
                    result["place_id"] = place_id
                return result

        # Паттерн 7: если нашли place_id или ftid, пытаемся получить координаты через Places API
        place_id = _extract_place_id(link)
        if place_id:
            # Если есть place_id, пытаемся получить координаты через Places API
            coords = await get_coordinates_from_place_id(place_id)
            if coords:
                lat, lng = coords
                name = _extract_place_name_from_data(link) or extract_place_name_from_url(link)
                return {
                    "lat": lat,
                    "lng": lng,
                    "name": name or "Место на карте",
                    "raw_link": link,
                    "place_id": place_id,
                }
            # Если не удалось получить координаты, возвращаем place_id для дальнейшей обработки
            return {
                "lat": None,
                "lng": None,
                "name": _extract_place_name_from_data(link),
                "raw_link": link,
                "place_id": place_id,
            }

        return None

    except (ValueError, AttributeError):
        return None


async def expand_short_url(short_url: str) -> str | None:
    """Расширяет короткую ссылку Google Maps до полной."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36"
        )
    }

    try:
        # Некоторые короткие ссылки (особенно maps.app.goo.gl) требуют полноценного GET.
        # Сначала пробуем получить ответ без автоматического перехода по редиректу,
        # чтобы вытащить Location из заголовков.
        async with httpx.AsyncClient(follow_redirects=False, timeout=15, headers=headers) as client:
            response = await client.get(short_url)

        print(f"[expand_short_url] GET (no redirect) {response.status_code} {short_url}")

        if response.status_code in [301, 302, 303, 307, 308]:
            location = response.headers.get("location")
            if location:
                return urljoin(short_url, location)

        candidate = _extract_maps_url_from_html(response.text, short_url)
        if candidate:
            return candidate

        # Если явного редиректа нет, пробуем посмотреть, куда httpx дошел бы с follow_redirects=True
        async with httpx.AsyncClient(follow_redirects=True, timeout=15, headers=headers) as client:
            follow_response = await client.get(short_url)
            final_url = str(follow_response.url)
            print(f"[expand_short_url] GET (follow) final={final_url}")
            if final_url and final_url != short_url:
                return final_url
            candidate = _extract_maps_url_from_html(follow_response.text, short_url)
            if candidate:
                return candidate

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

        # Паттерн для /place/name/ или /place/name/data=...
        # Берем всё до /data= или до следующего /
        place_pattern = r"/place/([^/@]+?)(?:/data=|/|$)"
        match = re.search(place_pattern, url)
        if match:
            name = match.group(1)
            # Декодируем URL-кодированные символы
            name = urllib.parse.unquote(name)
            return name

        return None
    except Exception:
        return None
