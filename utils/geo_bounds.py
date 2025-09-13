#!/usr/bin/env python3
"""
Географические границы и фильтрация для источников событий
Безопасный модуль с флагами по умолчанию false
"""

import logging
import math
import os
from dataclasses import dataclass

# === Конфигурация (флаги читаем разово при импорте) ===
ENABLE_GEO_BOUNDS = os.getenv("ENABLE_GEO_BOUNDS", "false").lower() == "true"
RUSSIA_BOUNDS_ENABLED = os.getenv("RUSSIA_BOUNDS_ENABLED", "false").lower() == "true"

# Логгер
logger = logging.getLogger(__name__)

# Метрики (собираются даже при выключенных флагах)
METRICS = {
    "ru_checked": 0,
    "ru_passed": 0,
    "ru_failed": 0,
    "checks_total": 0,
    "passed_total": 0,
    "failed_total": 0,
}


@dataclass(frozen=True)
class Circle:
    """Круг с центром и радиусом"""

    lat: float
    lon: float
    radius_km: float


@dataclass(frozen=True)
class Box:
    """Прямоугольная область"""

    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Точное расстояние между двумя точками в километрах по формуле Haversine
    """
    R = 6371.0  # Радиус Земли в км
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def in_circle(lat: float, lon: float, circle: Circle) -> bool:
    """Проверяет, находится ли точка внутри круга"""
    return haversine_km(lat, lon, circle.lat, circle.lon) <= circle.radius_km


def in_box(lat: float, lon: float, box: Box) -> bool:
    """Проверяет, находится ли точка внутри прямоугольника"""
    return box.min_lat <= lat <= box.max_lat and box.min_lon <= lon <= box.max_lon


# ======== Преднастройки для РФ (первый этап: Москва + СПб) ========

# Большая «грубая» рамка РФ (с запасом; исключает явный выход за пределы)
RUSSIA_BIG_BOX = Box(
    min_lat=41.0,
    min_lon=-180.0,  # Западная граница (включает СПб)
    max_lat=82.0,
    max_lon=180.0,  # Восточная граница
)

# Белые зоны — города (центр+радиус) для безопасного старта
RUSSIA_CITY_WHITELIST: dict[str, Circle] = {
    "moscow": Circle(55.7558, 37.6173, 60.0),  # Москва и область
    "spb": Circle(59.9343, 30.3351, 50.0),  # Санкт-Петербург
}


def is_allowed_russia(lat: float, lon: float) -> bool:
    """
    Проверяет, находится ли точка в разрешенных зонах России
    Сначала общий «большой бокс» (дешёвый фильтр)
    Затем белый список городов (строгий фильтр)
    """
    # Сначала общий «большой бокс» (дешёвый фильтр)
    if not in_box(lat, lon, RUSSIA_BIG_BOX):
        logger.debug(f"Точка ({lat:.4f}, {lon:.4f}) вне большого бокса России")
        return False

    # Затем белый список городов (строгий фильтр)
    for city_name, circle in RUSSIA_CITY_WHITELIST.items():
        if in_circle(lat, lon, circle):
            logger.debug(f"Точка ({lat:.4f}, {lon:.4f}) в зоне города {city_name}")
            return True

    logger.debug(f"Точка ({lat:.4f}, {lon:.4f}) не в whitelist городов")
    return False


def is_allowed(lat: float, lon: float, country_code: str | None) -> bool:
    """
    Универсальная точка входа для гео-фильтрации.

    Args:
        lat: Широта
        lon: Долгота
        country_code: Код страны ('RU', 'ID', ...) или None

    Returns:
        True если точка разрешена, False если заблокирована

    Логика:
    - Если флаги выключены - всегда True (обратная совместимость)
    - Для RU: проверяем whitelist городов
    - Для других стран: пока ничего не ограничиваем
    """
    # Всегда собираем метрики для наблюдаемости
    METRICS["checks_total"] += 1

    # Если гео-фильтры выключены - пропускаем все
    if not ENABLE_GEO_BOUNDS:
        METRICS["passed_total"] += 1
        return True

    # Обработка по странам
    if country_code == "RU":
        METRICS["ru_checked"] += 1

        # Если фильтр для России выключен - пропускаем
        if not RUSSIA_BOUNDS_ENABLED:
            METRICS["ru_passed"] += 1
            METRICS["passed_total"] += 1
            return True

        # Проверяем whitelist городов
        if is_allowed_russia(lat, lon):
            METRICS["ru_passed"] += 1
            METRICS["passed_total"] += 1
            logger.debug(f"RU точка ({lat:.4f}, {lon:.4f}) прошла фильтр")
            return True
        else:
            METRICS["ru_failed"] += 1
            METRICS["failed_total"] += 1
            logger.debug(f"RU точка ({lat:.4f}, {lon:.4f}) заблокирована фильтром")
            return False

    # Для других стран пока ничего не ограничиваем
    METRICS["passed_total"] += 1
    return True


def get_metrics() -> dict[str, int]:
    """Возвращает текущие метрики"""
    return METRICS.copy()


def reset_metrics() -> None:
    """Сбрасывает метрики (для тестов)"""
    for key in METRICS:
        METRICS[key] = 0


# ======== Тестовые функции ========


def test_geo_bounds():
    """Простой тест гео-границ"""
    print("🧪 Тестирование гео-границ...")

    # Отладочная информация
    print("📋 Настройки:")
    print(f"  ENABLE_GEO_BOUNDS: {ENABLE_GEO_BOUNDS}")
    print(f"  RUSSIA_BOUNDS_ENABLED: {RUSSIA_BOUNDS_ENABLED}")
    print(f"  RUSSIA_BIG_BOX: {RUSSIA_BIG_BOX}")
    print(f"  RUSSIA_CITY_WHITELIST: {RUSSIA_CITY_WHITELIST}")

    # Тестовые точки
    test_cases = [
        # (lat, lon, country, expected, description)
        (55.7558, 37.6173, "RU", True, "Москва - центр"),
        (59.9343, 30.3351, "RU", True, "СПб - центр"),
        (55.5, 37.5, "RU", True, "Москва - область"),
        (59.5, 30.5, "RU", True, "СПб - область"),
        (51.5074, -0.1278, "RU", False, "Лондон (как RU)"),
        (0.0, -140.0, "RU", False, "Океан (как RU)"),
        (55.7558, 37.6173, "ID", True, "Москва (как ID) - должна проходить"),
        (55.7558, 37.6173, None, True, "Москва (без страны) - должна проходить"),
    ]

    # Включаем фильтры для теста (используем глобальные переменные)
    import sys

    current_module = sys.modules[__name__]
    original_enable = current_module.ENABLE_GEO_BOUNDS
    original_russia = current_module.RUSSIA_BOUNDS_ENABLED

    current_module.ENABLE_GEO_BOUNDS = True
    current_module.RUSSIA_BOUNDS_ENABLED = True

    try:
        passed = 0
        total = len(test_cases)

        for lat, lon, country, expected, description in test_cases:
            result = is_allowed(lat, lon, country)
            status = "✅" if result == expected else "❌"
            print(f"  {status} {description}: {result} (ожидалось {expected})")

            # Отладочная информация для неудачных тестов
            if result != expected and country == "RU":
                print(f"    🔍 Отладка для ({lat}, {lon}):")
                print(f"      - В большом боксе: {in_box(lat, lon, RUSSIA_BIG_BOX)}")
                for city_name, circle in RUSSIA_CITY_WHITELIST.items():
                    distance = haversine_km(lat, lon, circle.lat, circle.lon)
                    in_city = in_circle(lat, lon, circle)
                    print(f"      - {city_name}: расстояние {distance:.1f}км, в круге {in_city}")

            if result == expected:
                passed += 1

        print(f"\n📊 Результат: {passed}/{total} тестов прошли")
        print(f"📈 Метрики: {get_metrics()}")

        return passed == total

    finally:
        # Восстанавливаем оригинальные значения
        current_module.ENABLE_GEO_BOUNDS = original_enable
        current_module.RUSSIA_BOUNDS_ENABLED = original_russia


if __name__ == "__main__":
    # Запуск тестов
    test_geo_bounds()
