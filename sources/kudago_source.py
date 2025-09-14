#!/usr/bin/env python3
"""
Источник событий из KudaGo для России
"""

import asyncio
import logging
import math
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

try:
    import httpx
except ImportError:
    httpx = None

from sources.base import BaseSource

logger = logging.getLogger(__name__)

# ---- ENV (все значения по умолчанию безопасны) -------------------
KUDAGO_ENABLED = os.getenv("KUDAGO_ENABLED", "false").lower() == "true"
KUDAGO_DRY_RUN = os.getenv("KUDAGO_DRY_RUN", "true").lower() == "true"
KUDAGO_PAGE_SIZE = int(os.getenv("KUDAGO_PAGE_SIZE", "100"))
KUDAGO_RPS = float(os.getenv("KUDAGO_RPS", "3"))
KUDAGO_TIMEOUT_S = float(os.getenv("KUDAGO_TIMEOUT_S", "8"))
TODAY_MAX_EVENTS = int(os.getenv("TODAY_MAX_EVENTS", "60"))
TODAY_SHOW_TOP = int(os.getenv("TODAY_SHOW_TOP", "12"))
CACHE_TTL_S = int(os.getenv("CACHE_TTL_S", "300"))

# ---- Метрики ------------------------------------------------------
METRICS = {
    "kudago_requests": 0,
    "kudago_pages": 0,
    "events_received": 0,
    "events_after_geo": 0,
    "events_saved": 0,
    "api_errors": 0,
    "cache_hits": 0,
}

# ---- Лёгкий in-memory кэш результатов на короткое время ----------
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    """Получает данные из кэша"""
    rec = _CACHE.get(key)
    if not rec:
        return None
    ts, data = rec
    if time.time() - ts <= CACHE_TTL_S:
        METRICS["cache_hits"] += 1
        return data
    return None


def _cache_put(key: str, data: list[dict[str, Any]]) -> None:
    """Сохраняет данные в кэш"""
    _CACHE[key] = (time.time(), data)


def today_window_utc(tz: ZoneInfo = ZoneInfo("Europe/Moscow")) -> tuple[datetime, datetime]:
    """Возвращает окно 'сегодня' в UTC с учётом часового пояса"""
    now_tz = datetime.now(tz)
    start = datetime(now_tz.year, now_tz.month, now_tz.day, 0, 0, 0, tzinfo=tz).astimezone(UTC)
    end = (start + timedelta(days=1) - timedelta(seconds=1)).astimezone(UTC)
    return start, end


def _iso(dt: datetime) -> str:
    """Конвертирует datetime в ISO формат для KudaGo"""
    return dt.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


class RateLimiter:
    """Ограничитель скорости запросов"""

    def __init__(self, rps: float):
        self.min_interval = 1.0 / max(rps, 0.1)
        self._last = 0.0

    async def wait(self):
        """Ждет до следующего разрешенного запроса"""
        now = time.time()
        gap = self.min_interval - (now - self._last)
        if gap > 0:
            await asyncio.sleep(gap)
        self._last = time.time()


async def _fetch_json(
    client: httpx.AsyncClient, url: str, params: dict[str, Any], limiter: RateLimiter
) -> dict[str, Any]:
    """Выполняет HTTP запрос с retry и rate limiting"""
    backoff = 0.5
    start_time = time.time()

    for attempt in range(5):
        await limiter.wait()
        try:
            METRICS["kudago_requests"] += 1
            r = await client.get(url, params=params, timeout=KUDAGO_TIMEOUT_S)
            if r.status_code >= 500:
                raise httpx.HTTPStatusError("5xx", request=r.request, response=r)
            r.raise_for_status()

            # Записываем успешный запрос в health-метрики
            latency_ms = (time.time() - start_time) * 1000
            try:
                from web.health import record_kudago_request

                record_kudago_request(success=True, latency_ms=latency_ms)
            except ImportError:
                pass  # Health модуль может быть недоступен

            return r.json()
        except Exception as e:
            METRICS["api_errors"] += 1
            logger.warning(f"KudaGo request error ({attempt+1}/5): {e}")
            logger.warning(f"URL: {url}")
            logger.warning(f"Params: {params}")
            await asyncio.sleep(backoff)
            backoff *= 2

    # Записываем неудачный запрос в health-метрики
    latency_ms = (time.time() - start_time) * 1000
    try:
        from web.health import record_kudago_request

        record_kudago_request(success=False, latency_ms=latency_ms)
    except ImportError:
        pass  # Health модуль может быть недоступен

    raise RuntimeError("KudaGo API failed after retries")


def _normalize_event(raw: dict[str, Any], city_slug: str) -> dict[str, Any]:
    """Нормализует событие из KudaGo в стандартный формат"""
    logger.info(f"Нормализация события: '{raw.get('title', 'Без названия')}'")
    # Даты: берём первую ближайшую
    start_ts = None
    end_ts = None
    dates = raw.get("dates", [])

    if dates:
        # Сортируем по времени начала
        valid_dates = [d for d in dates if d.get("start")]
        if valid_dates:
            first = sorted(valid_dates, key=lambda d: d.get("start") or 0)[0]
            start_ts = int(first.get("start") or 0)
            end_ts = int(first.get("end") or 0) or None
        else:
            logger.info(f"Событие '{raw.get('title', 'Без названия')}' без валидных дат")
    else:
        logger.info(f"Событие '{raw.get('title', 'Без названия')}' без поля dates")

    lat = lon = None
    place = raw.get("place") or {}
    coords = place.get("coords") or {}
    if "lat" in coords and "lon" in coords:
        lat = float(coords["lat"])
        lon = float(coords["lon"])

    return {
        "source": "kudago",
        "source_id": raw.get("id"),
        "country_code": "RU",
        "city": "moscow" if city_slug == "msk" else "spb" if city_slug == "spb" else city_slug,
        "title": (raw.get("title") or "").strip(),
        "description": (raw.get("description") or "").strip(),  # Добавляем описание
        "start_ts": start_ts,
        "end_ts": end_ts,
        "lat": lat,
        "lon": lon,
        "venue_name": (place.get("title") or "").strip(),
        "address": (place.get("address") or "").strip(),
        "source_url": raw.get("site_url") or raw.get("url") or "",
        "raw": {"kudago_city": city_slug},
    }


class KudaGoSource(BaseSource):
    """Источник событий из KudaGo"""

    @property
    def name(self) -> str:
        return "kudago"

    @property
    def display_name(self) -> str:
        return "KudaGo"

    @property
    def country_code(self) -> str:
        return "RU"

    def is_enabled(self) -> bool:
        """Проверяет, включен ли источник KudaGo"""
        # Используем настройки из config вместо переменных окружения
        from config import load_settings

        settings = load_settings()
        return settings.kudago_enabled

    async def fetch_events(self, lat: float, lng: float, radius_km: float) -> list[dict[str, Any]]:
        """
        Получает события из KudaGo для Москвы и СПб
        """
        if not self.is_enabled():
            logger.info("KudaGo источник отключен")
            return []

        logger.info(f"🌍 Ищем события в KudaGo для координат ({lat}, {lng}) с радиусом {radius_km} км")

        all_events = []

        # Проверяем, не в Бали ли мы (KudaGo работает только в России)
        if -9.0 <= lat <= -8.0 and 114.0 <= lng <= 116.0:
            logger.info("📍 Координаты в Бали, KudaGo не поддерживается")
            return all_events

        # Определяем, какой город ближе (только для российских координат)
        moscow_lat, moscow_lng = 55.7558, 37.6173
        spb_lat, spb_lng = 59.9343, 30.3351

        moscow_distance = self._haversine_km(lat, lng, moscow_lat, moscow_lng)
        spb_distance = self._haversine_km(lat, lng, spb_lat, spb_lng)

        # Выбираем ближайший город
        if moscow_distance < spb_distance:
            city_slug = "msk"
            city_name = "Москва"
        else:
            city_slug = "spb"
            city_name = "Санкт-Петербург"

        logger.info(f"📍 Выбран город: {city_name} ({city_slug})")

        # Получаем события для выбранного города
        try:
            events = await self._fetch_today_kudago(city_slug, (lat, lng), int(radius_km * 1000))
            all_events.extend(events)
            logger.info(f"✅ Найдено {len(events)} событий в {city_name}")

            # Записываем метрики событий
            try:
                from web.health import record_kudago_request

                record_kudago_request(
                    success=True,
                    latency_ms=0,  # Латентность уже записана в _fetch_json
                    events_count=len(events),
                    events_after_geo=len(events),  # События уже отфильтрованы
                )
            except ImportError:
                pass  # Health модуль может быть недоступен

        except Exception as e:
            logger.error(f"❌ Ошибка при получении событий из {city_name}: {e}")

            # Записываем метрики ошибки
            try:
                from web.health import record_kudago_request

                record_kudago_request(success=False, latency_ms=0)
            except ImportError:
                pass  # Health модуль может быть недоступен

        return all_events

    async def _fetch_today_kudago(
        self, city_slug: str, user_point: tuple[float, float] | None = None, radius_m: int | None = None
    ) -> list[dict[str, Any]]:
        """Получает события на сегодня из KudaGo"""

        start_utc, end_utc = today_window_utc()
        lat_str = f"{round(user_point[0],3)}" if user_point else "na"
        lon_str = f"{round(user_point[1],3)}" if user_point else "na"
        cache_key = f"today:{city_slug}:{lat_str}:{lon_str}:{radius_m or 0}"

        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

        base_url = "https://kudago.com/public-api/v1.4/events/"
        params = {
            "location": city_slug,
            # Временно отключаем фильтр по датам
            # "actual_since": _iso(start_utc),
            # "actual_until": _iso(end_utc),
            "expand": "place,dates,location",
            "fields": "id,title,place,dates,site_url,location",
            "page_size": KUDAGO_PAGE_SIZE,
        }
        if user_point and radius_m:
            params.update({"lat": user_point[0], "lon": user_point[1], "radius": radius_m})

        limiter = RateLimiter(KUDAGO_RPS)
        results: list[dict[str, Any]] = []

        if httpx is None:
            raise RuntimeError("Install httpx or port this code to requests")

        async with httpx.AsyncClient(headers={"User-Agent": "events-bot/1.0 (+ok)"}) as client:
            url = base_url
            while url and len(results) < TODAY_MAX_EVENTS:
                data = await _fetch_json(client, url, params, limiter)
                METRICS["kudago_pages"] += 1
                for item in data.get("results", []):
                    results.append(item)
                    if len(results) >= TODAY_MAX_EVENTS:
                        break
                url = data.get("next")
                params = {}  # next уже содержит querystring

        METRICS["events_received"] += len(results)

        # Нормализация
        normalized: list[dict[str, Any]] = [_normalize_event(r, city_slug) for r in results]

        # Валидация событий
        try:
            from utils.event_validator import validate_events_batch

            validated = validate_events_batch(normalized, city_slug)
            logger.info(f"Валидация {city_slug}: {len(validated)}/{len(normalized)} событий прошли валидацию")
        except Exception as e:
            logger.warning(f"validator unavailable, skip: {e}")
            validated = normalized

        # Гео-фильтр (если подключён)
        try:
            from utils.geo_bounds import is_allowed

            filtered: list[dict[str, Any]] = []
            for ev in validated:
                lat, lon = ev.get("lat"), ev.get("lon")
                if lat is None or lon is None:
                    filtered.append(ev)
                    continue
                if is_allowed(lat, lon, ev.get("country_code")):
                    filtered.append(ev)
            METRICS["events_after_geo"] += len(filtered)
        except Exception as e:
            logger.warning(f"geo filter unavailable, skip: {e}")
            filtered = validated

        # DRY_RUN: не сохраняем, возвращаем наверх
        from config import load_settings

        settings = load_settings()
        if settings.kudago_dry_run:
            logger.info(f"DRY_RUN: fetched={len(results)} normalized={len(normalized)} after_geo={len(filtered)}")
            _cache_put(cache_key, filtered)
            return filtered

        # Сохранение в БД через EventsService
        saved = 0
        try:
            from database import get_engine
            from storage.events_service import EventsService

            engine = get_engine()
            events_service = EventsService(engine)

            for ev in filtered:
                try:
                    # Добавляем информацию о регионе для правильного роутинга
                    if city_slug == "msk":
                        ev["country_code"] = "RU"
                        ev["city"] = "moscow"
                    elif city_slug == "spb":
                        ev["country_code"] = "RU"
                        ev["city"] = "spb"

                    # Сохраняем через сервис
                    success = await events_service.upsert_parser_event(ev)
                    if success:
                        saved += 1
                except Exception as e:
                    logger.warning(f"save failed for event {ev.get('title', 'unknown')}: {e}")
        except ImportError as e:
            logger.warning(f"EventsService not available, skipping save: {e}")
        except Exception as e:
            logger.error(f"Error initializing EventsService: {e}")

        METRICS["events_saved"] += saved

        _cache_put(cache_key, filtered)
        return filtered

    def _haversine_km(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Вычисляет расстояние между двумя точками в километрах"""
        lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        return 6371 * c  # Радиус Земли в км

    def get_metrics(self) -> dict[str, Any]:
        """Возвращает метрики источника"""
        return METRICS.copy()
