"""
Утилиты для работы с временными окнами по регионам
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

# Часовые пояса по регионам
REGION_TZ = {
    "bali": ZoneInfo("Asia/Makassar"),  # GMT+8
    "msk": ZoneInfo("Europe/Moscow"),  # GMT+3
    "spb": ZoneInfo("Europe/Moscow"),  # GMT+3
    "jakarta": ZoneInfo("Asia/Jakarta"),  # GMT+7
}


def today_window_utc_for(region: str) -> tuple[datetime, datetime]:
    """
    Возвращает временное окно "сегодня" для региона в UTC

    Args:
        region: Регион ("bali", "msk", "spb", "jakarta")

    Returns:
        Tuple[start_utc, end_utc] - начало и конец дня в UTC
    """
    if region not in REGION_TZ:
        raise ValueError(f"Unknown region: {region}. Available: {list(REGION_TZ.keys())}")

    tz = REGION_TZ[region]
    now_local = datetime.now(tz)

    # Начало дня в локальном времени
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    # Конец дня в локальном времени
    end_local = start_local + timedelta(days=1) - timedelta(seconds=1)

    # Конвертируем в UTC
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    return start_utc, end_utc


def normalize_to_utc(dt: datetime, region: str) -> datetime:
    """
    Нормализует datetime к UTC для региона

    Args:
        dt: datetime объект (может быть naive или с tzinfo)
        region: Регион для определения часового пояса

    Returns:
        datetime в UTC
    """
    if region not in REGION_TZ:
        raise ValueError(f"Unknown region: {region}. Available: {list(REGION_TZ.keys())}")

    tz = REGION_TZ[region]

    # Если datetime naive, добавляем локальный tz
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)

    # Конвертируем в UTC
    return dt.astimezone(UTC)


def get_region_from_coordinates(lat: float, lng: float) -> str:
    """
    Определяет регион по координатам

    Args:
        lat: Широта
        lng: Долгота

    Returns:
        Код региона
    """
    # Простая логика по координатам
    if -8.5 <= lat <= -8.0 and 114.0 <= lng <= 116.0:
        return "bali"
    elif 55.0 <= lat <= 56.0 and 37.0 <= lng <= 38.0:
        return "msk"
    elif 59.0 <= lat <= 60.0 and 29.0 <= lng <= 31.0:
        return "spb"
    elif -6.5 <= lat <= -6.0 and 106.0 <= lng <= 107.0:
        return "jakarta"
    else:
        # По умолчанию Бали для тестирования
        return "bali"


def format_time_window_log(region: str, start_utc: datetime, end_utc: datetime) -> str:
    """
    Форматирует лог временного окна

    Args:
        region: Регион
        start_utc: Начало окна в UTC
        end_utc: Конец окна в UTC

    Returns:
        Отформатированная строка для лога
    """
    return f"🕒 today window ({region}): {start_utc.isoformat()} .. {end_utc.isoformat()} (UTC)"


def get_cleanup_cutoff_utc(region: str) -> datetime:
    """
    Получает дату отсечения для очистки старых событий

    Args:
        region: Регион

    Returns:
        Дата отсечения в UTC (начало сегодняшнего дня)
    """
    if region not in REGION_TZ:
        raise ValueError(f"Unknown region: {region}. Available: {list(REGION_TZ.keys())}")

    tz = REGION_TZ[region]
    now_local = datetime.now(tz)

    # Начало сегодняшнего дня в локальном времени
    cutoff_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

    # Конвертируем в UTC
    cutoff_utc = cutoff_local.astimezone(UTC)

    return cutoff_utc
