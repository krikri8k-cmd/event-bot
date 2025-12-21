#!/usr/bin/env python3
"""
Health-страница для мониторинга KudaGo источника
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter()

# Глобальные метрики (в реальном проекте лучше использовать Redis/DB)
# ОГРАНИЧЕНИЕ РАЗМЕРА для защиты от OOM
_MAX_METRICS_SIZE = 1000  # Максимум записей в каждом списке метрик
_METRICS_CLEANUP_INTERVAL = 100  # Очистка каждые N записей

_metrics_store: dict[str, Any] = {
    "requests": [],
    "errors": [],
    "events_received": [],
    "events_after_geo": [],
    "cache_hits": [],
    "latencies": [],
    "last_success_ts": 0,
    "rps_estimate": 0.0,
    "_record_count": 0,  # Счетчик для периодической очистки
}


def _cleanup_metrics(now: float):
    """Очищает старые метрики и ограничивает размер списков"""
    cutoff = now - 3600  # Старше 1 часа

    # Очищаем устаревшие данные
    _metrics_store["requests"] = [ts for ts in _metrics_store["requests"] if ts > cutoff]
    _metrics_store["errors"] = [ts for ts in _metrics_store["errors"] if ts > cutoff]
    _metrics_store["events_received"] = [(ts, count) for ts, count in _metrics_store["events_received"] if ts > cutoff]
    _metrics_store["events_after_geo"] = [
        (ts, count) for ts, count in _metrics_store["events_after_geo"] if ts > cutoff
    ]
    _metrics_store["cache_hits"] = [ts for ts in _metrics_store["cache_hits"] if ts > cutoff]
    _metrics_store["latencies"] = [(ts, lat) for ts, lat in _metrics_store["latencies"] if ts > cutoff]

    # Ограничиваем размер списков (оставляем последние N записей)
    for key in ["requests", "errors", "cache_hits"]:
        if len(_metrics_store[key]) > _MAX_METRICS_SIZE:
            _metrics_store[key] = _metrics_store[key][-_MAX_METRICS_SIZE:]

    for key in ["events_received", "events_after_geo", "latencies"]:
        if len(_metrics_store[key]) > _MAX_METRICS_SIZE:
            _metrics_store[key] = _metrics_store[key][-_MAX_METRICS_SIZE:]


def record_request(
    success: bool, latency_ms: float, events_count: int = 0, events_after_geo: int = 0, cache_hit: bool = False
):
    """Записывает метрику запроса"""
    now = time.time()

    # Записываем запрос
    _metrics_store["requests"].append(now)

    if success:
        _metrics_store["last_success_ts"] = now
        _metrics_store["events_received"].append((now, events_count))
        _metrics_store["events_after_geo"].append((now, events_after_geo))
    else:
        _metrics_store["errors"].append(now)

    if cache_hit:
        _metrics_store["cache_hits"].append(now)

    _metrics_store["latencies"].append((now, latency_ms))

    # Периодическая очистка (каждые N записей)
    _metrics_store["_record_count"] = _metrics_store.get("_record_count", 0) + 1
    if _metrics_store["_record_count"] % _METRICS_CLEANUP_INTERVAL == 0:
        _cleanup_metrics(now)
    elif _metrics_store["_record_count"] == 1:
        # Первая запись - сразу очищаем
        _cleanup_metrics(now)

    # Обновляем RPS
    recent_requests = [ts for ts in _metrics_store["requests"] if ts > now - 60]
    _metrics_store["rps_estimate"] = len(recent_requests) / 60.0


def window_stats(minutes: int = 5) -> dict[str, Any]:
    """Возвращает статистику за указанное окно времени"""
    now = time.time()
    cutoff = now - (minutes * 60)

    # Запросы и ошибки за окно
    window_requests = [ts for ts in _metrics_store["requests"] if ts > cutoff]
    window_errors = [ts for ts in _metrics_store["errors"] if ts > cutoff]

    # События за окно
    window_events = [count for ts, count in _metrics_store["events_received"] if ts > cutoff]
    window_events_after_geo = [count for ts, count in _metrics_store["events_after_geo"] if ts > cutoff]

    # Кэш-хиты за окно
    window_cache_hits = [ts for ts in _metrics_store["cache_hits"] if ts > cutoff]

    # Латентность за окно
    window_latencies = [lat for ts, lat in _metrics_store["latencies"] if ts > cutoff]

    return {
        "errors": len(window_errors),
        "requests": len(window_requests),
        "avg_ms": sum(window_latencies) / len(window_latencies) if window_latencies else 0,
        "cache_hits": len(window_cache_hits),
        "events": sum(window_events),
        "events_after_geo": sum(window_events_after_geo),
        "last_success_ts": _metrics_store["last_success_ts"],
        "rps": _metrics_store["rps_estimate"],
    }


@router.get("/health/kudago")
def health_kudago():
    """Health-эндпоинт для KudaGo источника"""
    try:
        # Получаем статистику за 5 минут
        st_5m = window_stats(5)

        # Получаем статистику за 15 минут для событий
        st_15m = window_stats(15)

        # Вычисляем error rate
        error_rate = (st_5m["errors"] / max(1, st_5m["requests"])) * 100

        # Определяем статус
        status = "ok"
        if error_rate >= 10 or (st_15m["events"] == 0 and st_5m["requests"] > 0):
            status = "degraded"
        if st_5m["requests"] > 0 and st_5m["errors"] == st_5m["requests"]:
            status = "down"

        # Проверяем, когда был последний успешный запрос
        last_success_ago = time.time() - st_5m["last_success_ts"] if st_5m["last_success_ts"] > 0 else float("inf")
        if last_success_ago > 600:  # 10 минут без успешных запросов
            status = "down"

        # Форматируем время последнего успешного запроса
        last_fetch_utc = None
        if st_5m["last_success_ts"] > 0:
            last_fetch_utc = datetime.fromtimestamp(st_5m["last_success_ts"], tz=UTC).isoformat()

        return {
            "status": status,
            "last_fetch_utc": last_fetch_utc,
            "events_received_15m": st_15m["events"],
            "events_after_geo_15m": st_15m["events_after_geo"],
            "error_rate_5m": round(error_rate, 2),
            "avg_latency_ms_5m": round(st_5m["avg_ms"], 1),
            "rps_current": round(st_5m["rps"], 2),
            "cache_hit_rate_5m": round((st_5m["cache_hits"] / max(1, st_5m["requests"])) * 100, 1),
            "requests_5m": st_5m["requests"],
            "errors_5m": st_5m["errors"],
        }

    except Exception as e:
        logger.error(f"Ошибка в health-эндпоинте: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health/kudago/metrics")
def kudago_metrics():
    """Детальные метрики KudaGo для Prometheus"""
    try:
        st_5m = window_stats(5)
        st_15m = window_stats(15)

        # Prometheus-формат метрик
        metrics = []

        # Счетчики
        metrics.append(f"kudago_requests_total {st_5m['requests']}")
        metrics.append(f"kudago_api_errors_total {st_5m['errors']}")
        metrics.append(f"kudago_events_received_total {st_15m['events']}")
        metrics.append(f"kudago_events_after_geo_total {st_15m['events_after_geo']}")
        metrics.append(f"kudago_cache_hits_total {st_5m['cache_hits']}")

        # Gauge метрики
        metrics.append(f"kudago_rps_current {st_5m['rps']}")
        metrics.append(f"kudago_avg_latency_ms {st_5m['avg_ms']}")
        metrics.append(f"kudago_error_rate_percent {round((st_5m['errors'] / max(1, st_5m['requests'])) * 100, 2)}")

        # Время последнего успешного запроса
        if st_5m["last_success_ts"] > 0:
            metrics.append(f"kudago_last_success_timestamp {st_5m['last_success_ts']}")

        return "\n".join(metrics)

    except Exception as e:
        logger.error(f"Ошибка в метриках: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/health/kudago/status")
def kudago_status():
    """Простой статус для алертов"""
    try:
        st_5m = window_stats(5)
        st_15m = window_stats(15)

        error_rate = (st_5m["errors"] / max(1, st_5m["requests"])) * 100

        # Критерии для алертов
        alerts = []

        if error_rate > 10:
            alerts.append(f"high_error_rate:{error_rate:.1f}%")

        if st_15m["events"] == 0 and st_5m["requests"] > 0:
            alerts.append("no_events_received")

        if st_5m["avg_ms"] > 3000:
            alerts.append(f"high_latency:{st_5m['avg_ms']:.0f}ms")

        last_success_ago = time.time() - st_5m["last_success_ts"] if st_5m["last_success_ts"] > 0 else float("inf")
        if last_success_ago > 600:
            alerts.append("no_successful_requests_10min")

        return {
            "status": "ok" if not alerts else "alert",
            "alerts": alerts,
            "error_rate": round(error_rate, 2),
            "events_15m": st_15m["events"],
            "avg_latency_ms": round(st_5m["avg_ms"], 1),
        }

    except Exception as e:
        logger.error(f"Ошибка в статусе: {e}")
        return {"status": "error", "error": str(e)}


# Функция для интеграции с KudaGo источником
def record_kudago_request(
    success: bool, latency_ms: float, events_count: int = 0, events_after_geo: int = 0, cache_hit: bool = False
):
    """Записывает метрику запроса KudaGo (для вызова из источника)"""
    record_request(success, latency_ms, events_count, events_after_geo, cache_hit)
