#!/usr/bin/env python3
"""
Роутер для разделения событий по регионам
Использует существующую таблицу events с логическим разделением
"""

from enum import Enum
from typing import Any


class Region(Enum):
    BALI = "bali"
    MOSCOW = "moscow"
    SPB = "spb"


class EventType(Enum):
    PARSER = "parser"  # События от парсеров
    USER = "user"  # События от пользователей


def detect_region(country_code: str | None, city: str | None) -> Region:
    """
    Определяет регион по коду страны и городу

    Args:
        country_code: Код страны (ID, RU, etc)
        city: Название города (moscow, spb, bali, etc)

    Returns:
        Region enum
    """
    if not country_code and not city:
        return Region.BALI  # По умолчанию Бали

    # Россия
    if country_code == "RU":
        if city and city.lower() in ("moscow", "msk", "москва"):
            return Region.MOSCOW
        elif city and city.lower() in ("spb", "saint-petersburg", "sp", "питер", "санкт-петербург"):
            return Region.SPB
        else:
            return Region.MOSCOW  # По умолчанию Москва для РФ

    # Индонезия (Бали)
    elif country_code == "ID":
        return Region.BALI

    # По умолчанию Бали
    return Region.BALI


def get_region_filter(region: Region, event_type: EventType = EventType.PARSER) -> dict[str, Any]:
    """
    Возвращает фильтры для SQL запросов по региону

    Args:
        region: Регион
        event_type: Тип событий (парсер или пользователь)

    Returns:
        Словарь с условиями WHERE
    """
    filters = {}

    if region == Region.BALI:
        filters["country"] = "ID"
        # Можно добавить фильтр по city если нужно
    elif region == Region.MOSCOW:
        filters["country"] = "RU"
        filters["city"] = "moscow"
    elif region == Region.SPB:
        filters["country"] = "RU"
        filters["city"] = "spb"

    # Дополнительный фильтр по типу события
    if event_type == EventType.PARSER:
        # События от парсеров имеют source
        filters["source__isnot"] = None
    elif event_type == EventType.USER:
        # Пользовательские события могут не иметь source или иметь специальный
        pass

    return filters


def get_source_by_region(region: Region) -> str:
    """
    Возвращает название источника для региона

    Args:
        region: Регион

    Returns:
        Название источника
    """
    if region == Region.BALI:
        return "baliforum"
    elif region == Region.MOSCOW:
        return "kudago"
    elif region == Region.SPB:
        return "kudago"

    return "unknown"


def get_table_name(region: Region, event_type: EventType = EventType.PARSER) -> str:
    """
    Возвращает имя таблицы для региона и типа событий

    В текущей архитектуре все события идут в таблицу 'events',
    но логически разделяются по фильтрам

    Args:
        region: Регион
        event_type: Тип событий

    Returns:
        Имя таблицы (пока всегда 'events')
    """
    return "events"


# Константы для удобства
REGION_FILTERS = {
    Region.BALI: get_region_filter(Region.BALI),
    Region.MOSCOW: get_region_filter(Region.MOSCOW),
    Region.SPB: get_region_filter(Region.SPB),
}

PARSER_SOURCES = {
    Region.BALI: "baliforum",
    Region.MOSCOW: "kudago",
    Region.SPB: "kudago",
}
