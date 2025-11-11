#!/usr/bin/env python3
"""
Источник событий из KudaGo для России
"""

import asyncio
import logging
import math
import os
import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

try:
    import httpx
except ImportError:
    httpx = None

from config import load_settings
from sources.base import BaseSource

logger = logging.getLogger(__name__)

# ---- Конфигурация -------------------------------------------------
_SETTINGS = load_settings()

KUDAGO_ENABLED = _SETTINGS.kudago_enabled
KUDAGO_DRY_RUN = _SETTINGS.kudago_dry_run
KUDAGO_PAGE_SIZE = _SETTINGS.kudago_page_size
KUDAGO_RPS = float(_SETTINGS.kudago_rps)
KUDAGO_TIMEOUT_S = float(_SETTINGS.kudago_timeout_s)
KUDAGO_SAFE_MODE = _SETTINGS.kudago_safe_mode
SAFE_MODE_TIMEOUT_THRESHOLD = int(os.getenv("KUDAGO_SAFE_TIMEOUT_THRESHOLD", "3"))
SAFE_MODE_PAUSE_S = float(os.getenv("KUDAGO_SAFE_PAUSE_S", "15"))
KUDAGO_STRICT_MODE = _SETTINGS.kudago_strict_mode
KUDAGO_FALLBACK_DELAY_S = float(_SETTINGS.kudago_fallback_delay_s)
KUDAGO_PARTIAL_PAGE_SIZE = _SETTINGS.kudago_partial_page_size
KUDAGO_MAX_INTEGRITY_FAILS = _SETTINGS.kudago_max_integrity_fails
KUDAGO_INTEGRITY_TOLERANCE = float(_SETTINGS.kudago_integrity_tolerance)
TODAY_MAX_EVENTS = _SETTINGS.today_max_events
TODAY_SHOW_TOP = _SETTINGS.today_show_top
CACHE_TTL_S = _SETTINGS.cache_ttl_s
PAGE_RECOVERY_ROUNDS = _SETTINGS.kudago_page_recovery_rounds

DEFAULT_BACKOFF = (1.0, 2.0, 5.0, 10.0, 20.0)


def _unique_positive(sequence: list[int], minimum: int = 1) -> list[int]:
    result: list[int] = []
    for value in sequence:
        if value >= minimum and value not in result:
            result.append(value)
    return result


FIRST_BATCH_PAGE_SIZES = _unique_positive([KUDAGO_PAGE_SIZE, 30, 20, 10], minimum=10)
PARTIAL_PAGE_SIZES = _unique_positive([KUDAGO_PARTIAL_PAGE_SIZE, 10, 5, 2], minimum=2)
FIRST_BATCH_OFFSET_LIMITS = PARTIAL_PAGE_SIZES

FIRST_BATCH_BACKOFF = (1.0, 2.0, 5.0, 10.0)

if httpx:
    FIRST_BATCH_TIMEOUT = httpx.Timeout(connect=15.0, read=35.0, write=15.0, pool=60.0)
else:
    FIRST_BATCH_TIMEOUT = None

# ---- Метрики ------------------------------------------------------
METRICS = {
    "kudago_requests": 0,
    "kudago_pages": 0,
    "events_received": 0,
    "events_after_geo": 0,
    "events_saved": 0,
    "api_errors": 0,
    "cache_hits": 0,
    "timeouts": 0,
    "retries": 0,
    "pages_failed": 0,
    "pages_recovered": 0,
    "recovery_attempts": 0,
    "safe_pauses": 0,
    "fallback_attempts": 0,
    "fallback_success": 0,
    "integrity_failures": 0,
}

INTEGRITY_FAIL_STREAK = 0

# ---- Лёгкий in-memory кэш результатов на короткое время ----------
_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class FetchPageError(RuntimeError):
    """Ошибка получения страницы из KudaGo"""


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


def today_window_utc(
    tz: ZoneInfo = ZoneInfo("Europe/Moscow"),
) -> tuple[datetime, datetime]:
    """Возвращает окно 'сегодня + завтра' в UTC с учётом часового пояса"""
    now_tz = datetime.now(tz)
    start = datetime(now_tz.year, now_tz.month, now_tz.day, 0, 0, 0, tzinfo=tz).astimezone(UTC)
    # Окно на сегодня + завтра (до конца завтрашнего дня)
    end = (start + timedelta(days=2) - timedelta(seconds=1)).astimezone(UTC)
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
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
    limiter: RateLimiter,
    *,
    timeout: float | httpx.Timeout | None = None,
    backoff: tuple[float, ...] | None = None,
    jitter: bool = False,
    label: str | None = None,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Выполняет HTTP запрос с расширенным retry/backoff."""
    timeout_value: httpx.Timeout | float = timeout or KUDAGO_TIMEOUT_S
    backoff_seq = backoff or DEFAULT_BACKOFF
    label = label or url
    start_time = time.time()
    consecutive_timeouts = 0

    for attempt in range(1, len(backoff_seq) + 2):
        await limiter.wait()
        try:
            METRICS["kudago_requests"] += 1
            response = await client.get(url, params=params, timeout=timeout_value)
            if response.status_code >= 500:
                raise httpx.HTTPStatusError("5xx", request=response.request, response=response)
            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    str(response.status_code),
                    request=response.request,
                    response=response,
                )

            latency_ms = (time.time() - start_time) * 1000
            try:
                from web.health import record_kudago_request

                record_kudago_request(success=True, latency_ms=latency_ms)
            except ImportError:
                pass

            if stats is not None:
                stats.setdefault("latencies_ms", []).append(latency_ms)
                stats["consecutive_timeouts"] = 0
                stats["consecutive_timeouts_max"] = max(
                    stats.get("consecutive_timeouts_max", 0),
                    consecutive_timeouts,
                )

            return response.json()
        except httpx.ReadTimeout as exc:
            METRICS["timeouts"] += 1
            consecutive_timeouts += 1
            if stats is not None:
                stats["timeouts"] = stats.get("timeouts", 0) + 1
                stats["consecutive_timeouts"] = consecutive_timeouts
                stats["consecutive_timeouts_max"] = max(
                    stats.get("consecutive_timeouts_max", 0),
                    consecutive_timeouts,
                )
            logger.warning("⏳ Timeout %s (attempt %s): %s", label, attempt, exc)
        except Exception as exc:
            METRICS["api_errors"] += 1
            if stats is not None:
                stats["errors"] = stats.get("errors", 0) + 1
            logger.warning("⚠️ Ошибка запроса %s (attempt %s): %s", label, attempt, exc)
        else:
            break

        # Safe mode pause
        if (
            KUDAGO_SAFE_MODE
            and stats is not None
            and stats.get("consecutive_timeouts", 0) >= SAFE_MODE_TIMEOUT_THRESHOLD
        ):
            logger.warning("🛡️ Safe-mode pause %.1fs for %s", SAFE_MODE_PAUSE_S, label)
            METRICS["safe_pauses"] += 1
            stats["safe_pauses"] = stats.get("safe_pauses", 0) + 1
            stats["consecutive_timeouts"] = 0
            await asyncio.sleep(SAFE_MODE_PAUSE_S)

        if attempt <= len(backoff_seq):
            delay = backoff_seq[attempt - 1]
            if jitter:
                delay = delay * random.uniform(0.7, 1.3)
            logger.info("🔁 Retry %s in %.2fs (attempt %s)", label, delay, attempt + 1)
            await asyncio.sleep(delay)
            METRICS["retries"] += 1
            if stats is not None:
                stats["retries"] = stats.get("retries", 0) + 1
            continue
        break

    latency_ms = (time.time() - start_time) * 1000
    try:
        from web.health import record_kudago_request

        record_kudago_request(success=False, latency_ms=latency_ms)
    except ImportError:
        pass

    raise FetchPageError(f"{label} failed after retries")


def _normalize_event(raw: dict[str, Any], city_slug: str) -> dict[str, Any]:
    """Нормализует событие из KudaGo в стандартный формат"""
    logger.info(f"Нормализация события: '{raw.get('title', 'Без названия')}'")
    # Даты: берём первую ближайшую
    start_ts = None
    end_ts = None
    dates = raw.get("dates", [])

    if dates:
        # Фильтруем валидные даты (исключаем неправильные временные метки)
        now = datetime.now(UTC).timestamp()
        valid_dates = []
        for d in dates:
            start = d.get("start")
            if start and isinstance(start, int | float) and start > 0:
                # Проверяем, что дата не слишком далеко в прошлом или будущем
                if 946684800 <= start <= now + 86400 * 365 * 2:  # 2000-01-01 до +2 года
                    valid_dates.append(d)

        if valid_dates:
            # Определяем часовой пояс для города
            city_tz = ZoneInfo("Europe/Moscow") if city_slug in ["msk", "spb"] else ZoneInfo("UTC")

            # Сортируем по времени начала.
            # Берём первую дату в диапазоне сегодня + завтра (2 дня от начала).
            today_start = datetime.now(city_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_end = today_start + timedelta(days=2)
            window_start_ts = int(today_start.astimezone(UTC).timestamp())
            window_end_ts = int(tomorrow_end.astimezone(UTC).timestamp())

            # Ищем даты в окне сегодня+завтра.
            # Если нет — берём ближайшую.
            dates_in_window = [d for d in valid_dates if window_start_ts <= d.get("start", 0) < window_end_ts]
            if dates_in_window:
                # Берём первую дату в окне (самую раннюю).
                first = sorted(dates_in_window, key=lambda d: d.get("start", 0))[0]
            else:
                # Если нет дат в окне, берём ближайшую к сегодня.
                # Игнорируем прошлые даты.
                future_dates = [d for d in valid_dates if d.get("start", 0) >= now]
                if future_dates:
                    first = sorted(future_dates, key=lambda d: d.get("start", 0))[0]
                else:
                    # Если все даты в прошлом — берём ближайшую к сегодня.
                    first = sorted(
                        valid_dates,
                        key=lambda d: d.get("start", 0),
                        reverse=True,
                    )[0]

            start_ts = int(first.get("start"))
            end_ts = int(first.get("end") or 0) or None
        else:
            logger.info(
                "Событие '%s' без валидных дат — используем фоллбек",
                raw.get("title", "Без названия"),
            )
            # Фоллбек: сегодня в 12:00 по московскому времени
            moscow_tz = ZoneInfo("Europe/Moscow")
            now_moscow = datetime.now(moscow_tz)
            today_noon = now_moscow.replace(hour=12, minute=0, second=0, microsecond=0)
            start_ts = int(today_noon.astimezone(UTC).timestamp())
            end_ts = None
    else:
        logger.info(
            "Событие '%s' без поля dates — используем фоллбек",
            raw.get("title", "Без названия"),
        )
        # Фоллбек: сегодня в 12:00 по московскому времени
        moscow_tz = ZoneInfo("Europe/Moscow")
        now_moscow = datetime.now(moscow_tz)
        today_noon = now_moscow.replace(hour=12, minute=0, second=0, microsecond=0)
        start_ts = int(today_noon.astimezone(UTC).timestamp())
        end_ts = None

    lat = lon = None
    place = raw.get("place") or {}
    coords = place.get("coords") or {}
    if "lat" in coords or "lon" in coords:
        lat_val = coords.get("lat")
        lon_val = coords.get("lon")
        try:
            lat = float(lat_val) if lat_val is not None else None
        except (TypeError, ValueError):
            lat = None
        try:
            lon = float(lon_val) if lon_val is not None else None
        except (TypeError, ValueError):
            lon = None

    # Безопасная конвертация временных меток в datetime объекты для БД
    starts_at = None
    ends_at = None

    # Проверяем и конвертируем start_ts
    if start_ts and isinstance(start_ts, int | float) and start_ts > 0:
        try:
            starts_at = datetime.fromtimestamp(int(start_ts), tz=UTC)
            logger.debug(f"✅ Конвертировали start_ts {start_ts} в {starts_at}")
        except (ValueError, OSError) as e:
            logger.warning(f"⚠️ Не удалось конвертировать start_ts {start_ts}: {e}")
            starts_at = None

    # Проверяем и конвертируем end_ts
    if end_ts and isinstance(end_ts, int | float) and end_ts > 0:
        try:
            ends_at = datetime.fromtimestamp(int(end_ts), tz=UTC)
            logger.debug(f"✅ Конвертировали end_ts {end_ts} в {ends_at}")
        except (ValueError, OSError) as e:
            logger.warning("⚠️ Не удалось конвертировать end_ts %s: %s", end_ts, e)
            ends_at = None

    # Если не удалось получить валидное время, используем фоллбек
    if starts_at is None:
        moscow_tz = ZoneInfo("Europe/Moscow")
        now_moscow = datetime.now(moscow_tz)
        today_noon = now_moscow.replace(hour=12, minute=0, second=0, microsecond=0)
        starts_at = today_noon.astimezone(UTC)
        logger.info(
            "🔄 Используем фоллбек для времени %s (сегодня 12:00 по МСК)",
            starts_at,
        )

    venue_raw = place.get("title") or raw.get("location", {}).get("name") or "Место не указано"
    venue_name = venue_raw.strip()
    address = (place.get("address") or "").strip()

    return {
        "source": "kudago",
        "source_id": raw.get("id"),
        "country_code": "RU",
        "city": ("moscow" if city_slug == "msk" else "spb" if city_slug == "spb" else city_slug),
        "title": (raw.get("title") or "").strip(),
        "description": (raw.get("description") or "Описание недоступно").strip(),
        "starts_at": starts_at,  # datetime объект для БД
        "ends_at": ends_at,  # datetime объект для БД
        "lat": lat,
        "lon": lon,
        "venue_name": venue_name,
        "location_name": venue_name,
        "address": address,
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
        return KUDAGO_ENABLED

    async def fetch_events(self, lat: float, lng: float, radius_km: float) -> list[dict[str, Any]]:
        """
        Получает события из KudaGo для Москвы и СПб
        """
        if not self.is_enabled():
            logger.info("KudaGo источник отключен")
            return []

        logger.info(
            "🌍 Ищем события KudaGo для координат (%s, %s) с радиусом %s км",
            lat,
            lng,
            radius_km,
        )

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
        self,
        city_slug: str,
        user_point: tuple[float, float] | None = None,
        radius_m: int | None = None,
    ) -> list[dict[str, Any]]:
        """Получает события KudaGo на сегодня и завтра."""
        # Устойчивая загрузка с ретраями, fallback и проверкой целостности.

        start_utc, end_utc = today_window_utc()
        lat_str = f"{round(user_point[0], 3)}" if user_point else "na"
        lon_str = f"{round(user_point[1], 3)}" if user_point else "na"
        cache_key = f"today_tomorrow:{city_slug}:{lat_str}:{lon_str}:{radius_m or 0}"

        async def run_attempt(
            *,
            plan_name: str,
            use_cache: bool,
            page_sizes: list[int],
            offset_limits: list[int],
            allow_offset: bool,
            partial_only: bool,
        ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            stats: dict[str, Any] = {
                "plan": plan_name,
                "use_cache": use_cache,
                "first_batch_attempts": 0,
                "first_batch_failures": 0,
                "first_batch_mode": None,
                "first_batch_page_size": None,
                "timeouts": 0,
                "retries": 0,
                "pages_fetched": 0,
                "pages_failed": 0,
                "pages_recovered": 0,
                "recovery_attempts": 0,
                "safe_pauses": 0,
                "detail_requests": 0,
                "detail_failures": 0,
                "missing_events_count": 0,
                "fallback_source": plan_name,
            }

            cache_key_local = cache_key if use_cache else f"{cache_key}:{plan_name}"
            if use_cache:
                cached = _cache_get(cache_key_local)
                if cached is not None:
                    cap_reached = len(cached) >= TODAY_MAX_EVENTS
                    stats.update(
                        {
                            "from_cache": True,
                            "kudago_ingestion_success": True,
                            "raw_events": len(cached),
                            "pages_total": 0,
                            "total_count": len(cached),
                            "duration_ms": 0,
                            "retry_count_total": 0,
                            "cap_reached": cap_reached,
                            "integrity_failed": False,
                        }
                    )
                    return cached, stats

            page_size_current = KUDAGO_PAGE_SIZE
            current_limit = page_size_current
            if partial_only:
                stats["partial_mode"] = True
                page_size_current = min(page_size_current, KUDAGO_PARTIAL_PAGE_SIZE)
            max_pages_soft = max(5, math.ceil(TODAY_MAX_EVENTS / page_size_current) + 2)

            base_url = "https://kudago.com/public-api/v1.4/events/"
            base_params_full = {
                "location": city_slug,
                "actual_since": _iso(start_utc),
                "actual_until": _iso(end_utc),
                "expand": "place,dates",
                "fields": "id,title,place,dates,site_url,description",
                "page_size": page_size_current,
            }
            base_params_light = dict(base_params_full)
            base_params_light["fields"] = "id,title,place,dates,coords"

            if user_point and radius_m:
                for params in (base_params_full, base_params_light):
                    params.update(
                        {
                            "lat": user_point[0],
                            "lon": user_point[1],
                            "radius": radius_m,
                        }
                    )

            limiter = RateLimiter(KUDAGO_RPS)
            first_timeout = FIRST_BATCH_TIMEOUT or KUDAGO_TIMEOUT_S

            if httpx is None:
                raise FetchPageError("httpx is required for KudaGo fetch")

            start_monotonic = time.monotonic()
            pages_data: dict[int, list[dict[str, Any]]] = {}
            missing_batches: set[int] = set()
            missing_batches_all: set[int] = set()
            total_count: int | None = None

            async with httpx.AsyncClient(
                headers={
                    "User-Agent": "events-bot/1.0 (+ok)",
                    "Accept": "application/json",
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": "https://kudago.com/",
                    "Connection": "keep-alive",
                },
                timeout=KUDAGO_TIMEOUT_S,
                http2=False,
            ) as client:

                async def fetch_details(
                    ids: list[int],
                ) -> dict[int, dict[str, Any]]:
                    detail_map: dict[int, dict[str, Any]] = {}
                    if not ids:
                        return detail_map
                    for offset in range(0, len(ids), 20):
                        chunk_end = offset + 20
                        chunk = ids[offset:chunk_end]
                        stats["detail_requests"] += 1
                        params = {
                            "ids": ",".join(str(i) for i in chunk),
                            "expand": "place,dates",
                            "fields": ("id,title,description,place,dates," "site_url,location,coords"),
                        }
                        try:
                            payload = await _fetch_json(
                                client=client,
                                url=base_url,
                                params=params,
                                limiter=limiter,
                                label=f"detail_ids[{chunk[0]}]",
                                stats=stats,
                            )
                        except FetchPageError:
                            stats["detail_failures"] += len(chunk)
                            continue
                        for item in payload.get("results", []):
                            event_id = item.get("id")
                            if event_id is not None:
                                detail_map[event_id] = item
                    return detail_map

                async def fetch_first_batch(
                    candidate_sizes: list[int],
                    use_offset: bool,
                ) -> tuple[dict[str, Any], str, int] | None:
                    for size in candidate_sizes:
                        stats["first_batch_attempts"] += 1
                        params = dict(base_params_light)
                        label = "page=1"
                        if use_offset:
                            params.pop("page_size", None)
                            params.update({"offset": 0, "limit": size})
                            label = f"offset=0&limit={size}"
                        else:
                            params.update({"page": 1, "page_size": size})
                        try:
                            payload = await _fetch_json(
                                client=client,
                                url=base_url,
                                params=params,
                                limiter=limiter,
                                timeout=first_timeout,
                                backoff=FIRST_BATCH_BACKOFF,
                                jitter=True,
                                label=f"first_batch:{label}",
                                stats=stats,
                            )
                        except FetchPageError:
                            stats["first_batch_failures"] += 1
                            continue
                        return (
                            payload,
                            ("offset" if use_offset else "page"),
                            size,
                        )
                    return None

                first_payload_tuple = await fetch_first_batch(page_sizes, False)
                if first_payload_tuple is None and allow_offset:
                    first_payload_tuple = await fetch_first_batch(offset_limits or page_sizes, True)

                if first_payload_tuple is None:
                    raise FetchPageError("Не удалось получить первую страницу KudaGo")

                payload_first, first_mode, first_size = first_payload_tuple
                stats["first_batch_mode"] = first_mode
                stats["first_batch_page_size"] = first_size

                initial_results = payload_first.get("results", []) or []
                total_count = payload_first.get("count")
                stats["pages_fetched"] += 1
                METRICS["kudago_pages"] += 1

                detail_map = await fetch_details([item.get("id") for item in initial_results if item.get("id")])
                enriched_first: list[dict[str, Any]] = []
                for item in initial_results:
                    event_id = item.get("id")
                    detail = detail_map.get(event_id)
                    if detail:
                        merged = detail.copy()
                        for key in ("place", "dates", "coords"):
                            if key not in merged or not merged.get(key):
                                merged[key] = item.get(key)
                        enriched_first.append(merged)
                    else:
                        enriched_first.append(item)

                pages_data[1] = enriched_first

                async def fetch_page(label: str, params: dict[str, Any]) -> dict[str, Any]:
                    return await _fetch_json(
                        client=client,
                        url=base_url,
                        params=params,
                        limiter=limiter,
                        label=label,
                        stats=stats,
                    )

                next_page = 2
                next_offset = first_size
                page_size_current = min(page_size_current, max(2, first_size))
                current_limit = page_size_current
                base_params_full["page_size"] = page_size_current
                offset_stride = first_size if first_mode == "offset" else None

                if first_mode == "offset":
                    while True:
                        params = dict(base_params_full)
                        params.pop("page_size", None)
                        params.update({"offset": next_offset, "limit": current_limit})
                        label = f"offset={next_offset}"
                        try:
                            payload = await fetch_page(label, params)
                        except FetchPageError as exc:
                            logger.warning(
                                "⚠️ KudaGo: пропущен offset %s: %s",
                                next_offset,
                                exc,
                            )
                            missing_batches.add(next_page)
                            missing_batches_all.add(next_page)
                            stats["pages_failed"] += 1
                            METRICS["pages_failed"] += 1
                        else:
                            items = payload.get("results", []) or []
                            if not items:
                                break
                            pages_data[next_page] = items
                            stats["pages_fetched"] += 1
                            METRICS["kudago_pages"] += 1
                            if total_count is None:
                                total_count = payload.get("count")
                            if not payload.get("next"):
                                break
                        next_offset += offset_stride
                        next_page += 1
                else:
                    page = next_page
                    while page <= max_pages_soft:
                        params = dict(base_params_full)
                        params["page"] = page
                        try:
                            payload = await fetch_page(f"page={page}", params)
                        except FetchPageError as exc:
                            logger.warning(
                                "⚠️ KudaGo: пропущена страница %s: %s",
                                page,
                                exc,
                            )
                            missing_batches.add(page)
                            missing_batches_all.add(page)
                            stats["pages_failed"] += 1
                            METRICS["pages_failed"] += 1
                            page += 1
                            continue

                        items = payload.get("results", []) or []
                        if not items:
                            break
                        pages_data[page] = items
                        stats["pages_fetched"] += 1
                        METRICS["kudago_pages"] += 1

                        if total_count is None:
                            total_count = payload.get("count")
                            if total_count:
                                estimates = math.ceil(total_count / page_size_current) + 1
                                max_pages_soft = max(max_pages_soft, estimates)
                        if not payload.get("next"):
                            break
                        page += 1

                async def recover_batches(batch_numbers: list[int], prefix: str) -> set[int]:
                    nonlocal total_count
                    unresolved: set[int] = set()
                    for batch in batch_numbers:
                        params = dict(base_params_full)
                        if first_mode == "offset" and batch >= 2:
                            offset = first_size + (batch - 2) * first_size
                            params.pop("page_size", None)
                            params.update({"offset": offset, "limit": current_limit})
                            label = f"{prefix}:offset={offset}"
                        else:
                            params["page"] = batch
                            label = f"{prefix}:page={batch}"
                        try:
                            payload = await fetch_page(label, params)
                        except FetchPageError:
                            unresolved.add(batch)
                            missing_batches_all.add(batch)
                            continue
                        stats["pages_recovered"] += 1
                        METRICS["pages_recovered"] += 1
                        pages_data[batch] = payload.get("results", []) or []
                        if total_count is None:
                            total_count = payload.get("count")
                    return unresolved

                unresolved_batches = set(missing_batches)
                recovery_round = 0
                recovery_sizes = [size for size in PARTIAL_PAGE_SIZES if size < page_size_current]
                recovery_idx = 0
                while unresolved_batches and recovery_round < PAGE_RECOVERY_ROUNDS:
                    recovery_round += 1
                    stats["recovery_attempts"] += 1
                    METRICS["recovery_attempts"] += 1
                    unresolved_batches = await recover_batches(sorted(unresolved_batches), f"recover-{recovery_round}")
                    if unresolved_batches and KUDAGO_SAFE_MODE:
                        await asyncio.sleep(SAFE_MODE_PAUSE_S)
                    if unresolved_batches and partial_only and recovery_idx < len(recovery_sizes):
                        next_size = recovery_sizes[recovery_idx]
                        recovery_idx += 1
                        page_size_current = next_size
                        current_limit = next_size
                        base_params_full["page_size"] = page_size_current
                        logger.info(
                            "⬇️ Уменьшаем page_size для догрузки до %s",
                            next_size,
                        )

            def combine_results() -> list[dict[str, Any]]:
                ordered: list[dict[str, Any]] = []
                seen_ids: set[int] = set()
                for page_number in sorted(pages_data):
                    for item in pages_data[page_number]:
                        event_id = item.get("id")
                        if event_id is not None:
                            if event_id in seen_ids:
                                continue
                            seen_ids.add(event_id)
                        ordered.append(item)
                        if len(ordered) >= TODAY_MAX_EVENTS:
                            return ordered
                return ordered

            combined_results = combine_results()
            duration_ms_raw = (time.monotonic() - start_monotonic) * 1000
            stats["duration_ms"] = float(duration_ms_raw) if duration_ms_raw is not None else 0.0
            stats["raw_events"] = len(combined_results)
            stats["pages_total"] = len(pages_data)
            stats["total_count"] = total_count
            stats["missing_pages_final"] = sorted(missing_batches_all)

            missing_events = 0
            cap_reached = len(combined_results) >= TODAY_MAX_EVENTS
            stats["cap_reached"] = cap_reached
            if total_count:
                if cap_reached:
                    missing_events = 0
                else:
                    missing_events = max(0, total_count - len(combined_results))
            stats["missing_events_count"] = missing_events
            if total_count:
                integrity_ratio = missing_events / max(total_count, 1)
                stats["integrity_failed"] = False if cap_reached else integrity_ratio > KUDAGO_INTEGRITY_TOLERANCE
            else:
                stats["integrity_failed"] = bool(missing_batches_all)

            stats["kudago_ingestion_success"] = not stats["integrity_failed"]
            stats["retry_count_total"] = stats.get("retries", 0) + stats.get("recovery_attempts", 0)

            return combined_results, stats

        attempts_plan = [
            {
                "name": "primary",
                "use_cache": True,
                "page_sizes": FIRST_BATCH_PAGE_SIZES,
                "offset_limits": [],
                "allow_offset": False,
                "partial_only": False,
            },
            {
                "name": "offset",
                "use_cache": False,
                "page_sizes": FIRST_BATCH_PAGE_SIZES,
                "offset_limits": FIRST_BATCH_OFFSET_LIMITS,
                "allow_offset": True,
                "partial_only": False,
            },
            {
                "name": "partial",
                "use_cache": False,
                "page_sizes": PARTIAL_PAGE_SIZES,
                "offset_limits": FIRST_BATCH_OFFSET_LIMITS,
                "allow_offset": True,
                "partial_only": True,
            },
        ]

        attempt_stats: list[dict[str, Any]] = []
        global INTEGRITY_FAIL_STREAK
        last_result: list[dict[str, Any]] = []
        last_stats: dict[str, Any] | None = None

        for attempt in attempts_plan:
            try:
                result, stats = await run_attempt(
                    plan_name=attempt["name"],
                    use_cache=attempt["use_cache"],
                    page_sizes=attempt["page_sizes"],
                    offset_limits=attempt["offset_limits"],
                    allow_offset=attempt["allow_offset"],
                    partial_only=attempt["partial_only"],
                )
            except FetchPageError as exc:
                logger.error("❌ KudaGo attempt '%s' failed: %s", attempt["name"], exc)
                attempt_stats.append({"plan": attempt["name"], "error": str(exc)})
                continue

            attempt_stats.append(stats)
            last_result = result
            last_stats = stats

            if stats.get("kudago_ingestion_success"):
                INTEGRITY_FAIL_STREAK = 0
                break

            INTEGRITY_FAIL_STREAK += 1
            logger.warning(
                "⚠️ KudaGo integrity failed " "(plan=%s missing=%s total=%s streak=%s)",
                stats.get("plan"),
                stats.get("missing_events_count"),
                stats.get("total_count"),
                INTEGRITY_FAIL_STREAK,
            )

            if attempt is not attempts_plan[-1]:
                METRICS["fallback_attempts"] += 1

                if KUDAGO_FALLBACK_DELAY_S > 0:
                    logger.info(
                        "⏳ Ждём %.1f с перед следующей попыткой",
                        KUDAGO_FALLBACK_DELAY_S,
                    )
                    await asyncio.sleep(KUDAGO_FALLBACK_DELAY_S)
            else:
                break

        if last_stats is None:
            raise FetchPageError("All attempts to fetch KudaGo data failed")

        self.last_run_stats = {
            "city": city_slug,
            "cache_key": cache_key,
            "attempts": attempt_stats,
            "final": last_stats,
        }

        if last_stats.get("kudago_ingestion_success") and last_stats.get("plan") != "primary":
            METRICS["fallback_success"] += 1

        if not last_stats.get("kudago_ingestion_success"):
            if INTEGRITY_FAIL_STREAK >= KUDAGO_MAX_INTEGRITY_FAILS and KUDAGO_STRICT_MODE:
                logger.error(
                    "🚨 Strict mode: dropping partial results (streak=%s)",
                    INTEGRITY_FAIL_STREAK,
                )
                raise FetchPageError("Strict mode: integrity check failed")

        METRICS["events_received"] += len(last_result)

        normalized = [_normalize_event(r, city_slug) for r in last_result]

        try:
            from utils.event_validator import validate_events_batch

            validated = validate_events_batch(normalized, city_slug)
        except Exception as e:
            logger.warning(f"validator unavailable, skip: {e}")
            validated = normalized

        try:
            from utils.geo_bounds import is_allowed

            filtered = []
            for ev in validated:
                lat, lon = ev.get("lat"), ev.get("lon")
                if lat is None or lon is None or is_allowed(lat, lon, ev.get("country_code")):
                    filtered.append(ev)
            METRICS["events_after_geo"] += len(filtered)
        except Exception as e:
            logger.warning(f"geo filter unavailable, skip: {e}")
            filtered = validated

        summary_fields = {
            "timeouts": last_stats.get("timeouts", 0),
            "retry_count_total": last_stats.get("retry_count_total", 0),
            "pages_fetched": last_stats.get("pages_fetched", 0),
            "pages_failed": last_stats.get("pages_failed", 0),
            "pages_recovered": last_stats.get("pages_recovered", 0),
            "consecutive_timeouts_max": last_stats.get("consecutive_timeouts_max", 0),
            "duration_ms": round(last_stats.get("duration_ms", 0), 2),
            "raw_events": last_stats.get("raw_events", 0),
            "pages_total": last_stats.get("pages_total", 0),
            "total_count": last_stats.get("total_count"),
            "integrity_failed": last_stats.get("integrity_failed"),
            "cap_reached": last_stats.get("cap_reached"),
            "first_batch_mode": last_stats.get("first_batch_mode"),
            "first_batch_page_size": last_stats.get("first_batch_page_size"),
            "attempts": len(attempt_stats),
            "plan_chain": [a.get("plan") for a in attempt_stats],
        }
        logger.info(
            "📊 KudaGo fetch summary city=%s status=%s events=%s %s",
            city_slug,
            ("success" if last_stats.get("kudago_ingestion_success") else "partial"),
            len(last_result),
            ", ".join(f"{key}={value}" for key, value in summary_fields.items()),
        )

        if KUDAGO_DRY_RUN:
            _cache_put(cache_key, filtered)
            return filtered

        from config import load_settings

        settings = load_settings()
        saved = 0
        try:
            from database import get_engine, init_engine
            from storage.events_service import EventsService

            try:
                engine = get_engine()
            except Exception:
                init_engine(settings.database_url)
                engine = get_engine()

            service = EventsService(engine)
            for ev in filtered:
                if city_slug == "msk":
                    ev["country_code"] = "RU"
                    ev["city"] = "moscow"
                elif city_slug == "spb":
                    ev["country_code"] = "RU"
                    ev["city"] = "spb"
                try:
                    if await service.upsert_parser_event(ev):
                        saved += 1
                except Exception as exc:
                    logger.exception(
                        "Ошибка сохранения события '%s': %s",
                        ev.get("title"),
                        exc,
                    )
        except ImportError:
            logger.warning("EventsService unavailable; skip save")
        except Exception as exc:
            logger.exception("Error storing KudaGo events: %s", exc)

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
