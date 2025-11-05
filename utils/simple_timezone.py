"""
Простая логика часовых поясов по городам
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# Часовые пояса по городам
CITY_TIMEZONES = {
    "bali": "Asia/Makassar",  # GMT+8
    "moscow": "Europe/Moscow",  # GMT+3
    "spb": "Europe/Moscow",  # GMT+3
    "jakarta": "Asia/Jakarta",  # GMT+7
}


def get_city_timezone(city: str | None) -> str:
    """
    Получает часовой пояс для города

    Args:
        city: Название города или None, если регион не определен

    Returns:
        Часовой пояс в формате IANA (UTC, если город не определен)
    """
    if city is None:
        return "UTC"  # Если регион не определен, используем UTC
    return CITY_TIMEZONES.get(city.lower(), "UTC")  # По умолчанию UTC, если город неизвестен


def get_today_start_utc(city: str | None) -> datetime:
    """
    Получает начало сегодняшнего дня в UTC для города
    Окно "сегодня" = с 00:00 до 23:59:59 по местному времени города

    Args:
        city: Название города

    Returns:
        Начало дня в UTC
    """
    tz_name = get_city_timezone(city)
    tz = ZoneInfo(tz_name)

    # Текущее время в городе
    now_local = datetime.now(tz)

    # Начало сегодняшнего дня в городе (00:00:00)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    # Конвертируем в UTC
    start_utc = start_local.astimezone(UTC)

    return start_utc


def get_tomorrow_start_utc(city: str | None) -> datetime:
    """
    Получает начало завтрашнего дня в UTC для города
    Окно "сегодня" заканчивается в 00:00:00 следующего дня по местному времени

    Args:
        city: Название города

    Returns:
        Начало завтрашнего дня в UTC
    """
    from datetime import timedelta

    tz_name = get_city_timezone(city)
    tz = ZoneInfo(tz_name)

    # Текущее время в городе
    now_local = datetime.now(tz)

    # Начало завтрашнего дня в городе (00:00:00 следующего дня)
    tomorrow_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

    # Конвертируем в UTC
    tomorrow_utc = tomorrow_local.astimezone(UTC)

    return tomorrow_utc


def convert_local_to_utc(local_dt: datetime, city: str | None) -> datetime:
    """
    Конвертирует локальное время города в UTC

    Args:
        local_dt: Локальное время (может быть naive)
        city: Название города

    Returns:
        Время в UTC
    """
    tz_name = get_city_timezone(city)
    tz = ZoneInfo(tz_name)

    # Если время naive, добавляем часовой пояс города
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=tz)

    # Конвертируем в UTC
    return local_dt.astimezone(UTC)


def get_city_from_coordinates(lat: float, lng: float) -> str | None:
    """
    Определяет город по координатам (простая логика)

    Args:
        lat: Широта
        lng: Долгота

    Returns:
        Название города или None, если регион не определен
    """
    # Простая логика по координатам
    # Расширенные границы для Бали (включая южные районы типа Нуса Дуа, Джимбаран)
    if -9.0 <= lat <= -8.0 and 114.0 <= lng <= 116.0:
        return "bali"
    elif 55.0 <= lat <= 56.0 and 37.0 <= lng <= 38.0:
        return "moscow"
    elif 59.0 <= lat <= 60.0 and 29.0 <= lng <= 31.0:
        return "spb"
    elif -6.5 <= lat <= -6.0 and 106.0 <= lng <= 107.0:
        return "jakarta"
    else:
        return None  # Регион не определен


def format_city_time_info(city: str | None) -> str:
    """
    Форматирует информацию о времени для города

    Args:
        city: Название города

    Returns:
        Отформатированная строка с информацией о времени
    """
    tz_name = get_city_timezone(city)
    tz = ZoneInfo(tz_name)

    now_local = datetime.now(tz)
    today_start_utc = get_today_start_utc(city)
    tomorrow_start_utc = get_tomorrow_start_utc(city)

    city_name = city.title() if city else "Не определен"
    return (
        f"🌍 Город: {city_name}\n"
        f"🕒 Часовой пояс: {tz_name}\n"
        f"⏰ Текущее время: {now_local.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📅 Начало дня (UTC): {today_start_utc.isoformat()}\n"
        f"📅 Начало завтра (UTC): {tomorrow_start_utc.isoformat()}"
    )
