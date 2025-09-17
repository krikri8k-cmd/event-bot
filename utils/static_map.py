#!/usr/bin/env python3
"""
Универсальный модуль для работы с Google Static Maps API
с circuit breaker и graceful fallback
"""

import logging
import time
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None


logger = logging.getLogger(__name__)

# Circuit breaker для Google Maps
_MAP_CB = {
    "open_until": 0,  # Время до которого предохранитель "открыт"
    "fails": 0,  # Количество последовательных ошибок
}


# Настройки загружаются из config
def _get_settings():
    from config import load_settings

    return load_settings()


def build_static_map_url(
    user_lat: float,
    user_lng: float,
    points: list[tuple[float, float]],
    api_key: str,
    size: str = "800x600",
    zoom: int = 13,
) -> str:
    """
    Строит URL для Google Static Maps API

    Args:
        user_lat, user_lng: координаты пользователя
        points: список координат событий [(lat, lng), ...]
        api_key: Google Maps API ключ
        size: размер изображения
        zoom: уровень зума

    Returns:
        URL для запроса карты
    """
    base_url = "https://maps.googleapis.com/maps/api/staticmap"

    # Маркер пользователя (красный)
    markers = [f"color:red%7Clabel:U%7C{user_lat},{user_lng}"]

    # Маркеры событий (синие)
    for i, (lat, lng) in enumerate(points[:20]):  # Ограничиваем 20 маркерами
        if lat and lng:
            label = str(i + 1) if i < 9 else "E"  # 1-9, потом E для остальных
            markers.append(f"color:blue%7Clabel:{label}%7C{lat},{lng}")

    # Формируем URL
    markers_str = "&markers=".join([""] + markers)
    url = (
        f"{base_url}?"
        f"size={size}&"
        f"zoom={zoom}&"
        f"center={user_lat},{user_lng}&"
        f"key={api_key}"
        f"{markers_str}"
    )

    return url


async def fetch_static_map(url: str, timeout_s: float = None) -> bytes | None:
    """
    Получает изображение карты с circuit breaker защитой

    Args:
        url: URL для запроса карты
        timeout_s: таймаут запроса

    Returns:
        bytes изображения или None при ошибке
    """
    if httpx is None:
        logger.warning("httpx не установлен, карты недоступны")
        return None

    # Загружаем настройки
    settings = _get_settings()
    if not settings.maps_enabled:
        logger.debug("Карты отключены в настройках")
        return None

    if timeout_s is None:
        timeout_s = settings.maps_timeout_s

    now = time.time()

    # Circuit breaker: если недавно падало — сразу возвращаем None
    if _MAP_CB["open_until"] > now:
        logger.debug(f"Circuit breaker открыт до {_MAP_CB['open_until']}")
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.get(url)

        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

        # Проверяем content-type (иногда вместо изображения приходит HTML)
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type.lower():
            raise RuntimeError(f"Неожиданный content-type: {content_type}")

        content = response.content
        if not content:
            raise RuntimeError("Пустой ответ")

        # Успех — сбрасываем счётчик ошибок
        _MAP_CB["fails"] = 0

        # Логируем успех
        logger.info(f"✅ Карта загружена успешно: {len(content)} байт, {content_type}")

        return content

    except Exception as e:
        _MAP_CB["fails"] += 1

        # Если подряд N+ падений — "открываем" предохранитель
        settings = _get_settings()
        if _MAP_CB["fails"] >= settings.maps_cb_fails:
            _MAP_CB["open_until"] = now + (settings.maps_cb_cooldown_min * 60)
            logger.warning(
                f"Circuit breaker открыт на {settings.maps_cb_cooldown_min} минут " f"после {_MAP_CB['fails']} ошибок"
            )

        # Логируем ошибку (но не показываем пользователю)
        logger.debug(
            f"static_map_fail: {str(e)}, fails={_MAP_CB['fails']}, "
            f"type={type(e).__name__}, cb_open={_MAP_CB['open_until'] > now}"
        )

        logger.debug(f"Ошибка получения карты: {e}")
        return None


def get_circuit_breaker_status() -> dict[str, Any]:
    """Возвращает статус circuit breaker для мониторинга"""
    now = time.time()
    return {
        "is_open": _MAP_CB["open_until"] > now,
        "fails_count": _MAP_CB["fails"],
        "open_until": _MAP_CB["open_until"],
        "seconds_until_reset": max(0, int(_MAP_CB["open_until"] - now)),
    }


def reset_circuit_breaker():
    """Принудительно сбрасывает circuit breaker (для админки)"""
    global _MAP_CB
    _MAP_CB = {"open_until": 0, "fails": 0}
    logger.info("Circuit breaker принудительно сброшен")


def is_maps_available() -> bool:
    """Проверяет, доступны ли карты (для предварительной проверки)"""
    return time.time() > _MAP_CB["open_until"]
