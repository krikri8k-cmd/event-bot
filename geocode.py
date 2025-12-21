# geocode.py
import hashlib
import logging
import os
import time
from threading import Lock

import googlemaps

log = logging.getLogger(__name__)

API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
ENABLED = os.getenv("GEOCODE_ENABLE", "1") == "1"
TIMEOUT = float(os.getenv("GEOCODE_TIMEOUT_S", "4"))
QPS = float(os.getenv("GEOCODE_RATE_QPS", "5"))  # запросов в секунду
CACHE_TTL_S = int(os.getenv("GEOCODE_CACHE_TTL_S", "86400"))

_gmaps: googlemaps.Client | None = None
_rate_lock = Lock()
_last_ts = [0.0]  # хранить в списке, чтобы быть мутабельным из замыкания


def _client() -> googlemaps.Client | None:
    global _gmaps
    if not ENABLED:
        return None
    if not API_KEY:
        log.warning("GEOCODE_ENABLE=1, но GOOGLE_MAPS_API_KEY не указан — геокодер выключен")
        return None
    if _gmaps is None:
        _gmaps = googlemaps.Client(key=API_KEY, timeout=TIMEOUT)
    return _gmaps


def _throttle():
    """Простейший QPS-троттлинг для локальной защиты."""
    if QPS <= 0:
        return
    min_interval = 1.0 / QPS
    with _rate_lock:
        now = time.perf_counter()
        delta = now - _last_ts[0]
        if delta < min_interval:
            time.sleep(min_interval - delta)
        _last_ts[0] = time.perf_counter()


def _stable_key(*parts: str) -> str:
    s = " | ".join(p.strip() for p in parts if p)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# --- Кэш уровня процесса с TTL ------------------------------------------------
# lru_cache не умеет TTL — добавим простую прослойку
_cache = {}
_cache_lock = Lock()
# ОГРАНИЧЕНИЕ РАЗМЕРА КЭША для защиты от OOM
_MAX_CACHE_SIZE = 1000  # Максимум 1000 записей в кэше


def _cache_get(k: str):
    with _cache_lock:
        v = _cache.get(k)
        if not v:
            return None
        value, ts = v
        if (time.time() - ts) > CACHE_TTL_S:
            _cache.pop(k, None)
            return None
        return value


def _cache_set(k: str, value):
    with _cache_lock:
        # Очистка устаревших записей при превышении размера
        if len(_cache) >= _MAX_CACHE_SIZE:
            # Удаляем самые старые записи (по timestamp)
            current_time = time.time()
            expired_keys = [key for key, (_, ts) in _cache.items() if (current_time - ts) > CACHE_TTL_S]
            for key in expired_keys:
                _cache.pop(key, None)

            # Если все еще слишком много, удаляем 50% самых старых
            if len(_cache) >= _MAX_CACHE_SIZE:
                sorted_items = sorted(_cache.items(), key=lambda x: x[1][1])  # Сортируем по timestamp
                to_remove = len(_cache) - _MAX_CACHE_SIZE // 2
                for key, _ in sorted_items[:to_remove]:
                    _cache.pop(key, None)

        _cache[k] = (value, time.time())


# --- Публичные функции --------------------------------------------------------


def geocode_best_effort(venue: str | None, address: str | None) -> tuple[float, float] | None:
    """
    1) venue + address 2) address 3) venue
    Возвращает (lat, lon) или None. Не кидает исключения наружу.
    """
    if not ENABLED:
        return None

    c = _client()
    if not c:
        return None

    # Стратегии запросов
    candidates = []
    if venue and address:
        candidates.append(f"{venue}, {address}")
    if address:
        candidates.append(address)
    if venue:
        candidates.append(venue)

    for q in candidates:
        k = _stable_key("G", q)
        if (hit := _cache_get(k)) is not None:
            latlng = hit
            if latlng:
                log.debug("geocode cache HIT %s -> %s", q, latlng)
            return latlng

        try:
            _throttle()
            res = c.geocode(q)
            if res and "geometry" in res[0]:
                loc = res[0]["geometry"]["location"]
                latlng = (float(loc["lat"]), float(loc["lng"]))
                _cache_set(k, latlng)
                log.debug("geocode OK %s -> %s", q, latlng)
                return latlng
            else:
                _cache_set(k, None)
                log.debug("geocode EMPTY %s", q)
        except Exception as e:
            # Не рушим конвейер, просто лог
            log.warning("geocode FAIL %s: %s", q, e)
            _cache_set(k, None)

    return None


def reverse_geocode_best_effort(lat: float, lon: float) -> str | None:
    """
    Пытается получить человекочитаемый адрес. Возвращает строку или None.
    """
    if not ENABLED:
        return None
    c = _client()
    if not c:
        return None

    q = f"{lat},{lon}"
    k = _stable_key("R", q)
    if (hit := _cache_get(k)) is not None:
        return hit

    try:
        _throttle()
        res = c.reverse_geocode((lat, lon))
        if res and "formatted_address" in res[0]:
            addr = res[0]["formatted_address"]
            _cache_set(k, addr)
            log.debug("revgeocode OK %s -> %s", q, addr)
            return addr
        _cache_set(k, None)
        log.debug("revgeocode EMPTY %s", q)
    except Exception as e:
        log.warning("revgeocode FAIL %s: %s", q, e)
        _cache_set(k, None)

    return None
