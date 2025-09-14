#!/usr/bin/env python3
"""
Валидатор событий для проверки качества данных перед сохранением
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Метрики валидации
VALIDATION_METRICS = {
    "events_validated": 0,
    "events_dropped": 0,
    "validation_errors": 0,
    "title_truncated": 0,
    "invalid_timestamp": 0,
    "missing_coordinates": 0,
    "invalid_url": 0,
}


def validate_event(event: dict[str, Any], city: str = "unknown") -> dict[str, Any] | None:
    """
    Валидирует событие и возвращает очищенную версию или None если событие невалидно

    Args:
        event: Сырое событие
        city: Город для логирования

    Returns:
        Валидированное событие или None если событие отбрасывается
    """
    VALIDATION_METRICS["events_validated"] += 1

    try:
        # 1. Валидация заголовка
        title = event.get("title", "").strip()
        if not title:
            logger.debug(f"Событие без заголовка отброшено в {city}")
            VALIDATION_METRICS["events_dropped"] += 1
            return None

        # Обрезаем заголовок до 180 символов
        if len(title) > 180:
            title = title[:177] + "..."
            VALIDATION_METRICS["title_truncated"] += 1
            logger.debug(f"Заголовок обрезан в {city}: {title[:50]}...")

        # 2. Валидация временной метки (разрешаем события без времени для упрощенного режима)
        starts_at = event.get("starts_at")
        if starts_at is None:
            logger.info(f"Событие без времени принято в упрощенном режиме в {city}: {title[:50]}")
            # Устанавливаем время по умолчанию - сегодня в 12:00 по московскому времени
            now = datetime.now(ZoneInfo("Europe/Moscow"))
            today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
            starts_at = today_noon.astimezone(UTC)
            event["starts_at"] = starts_at
        else:
            # Убеждаемся, что starts_at - это datetime объект
            if isinstance(starts_at, int | float):
                event["starts_at"] = datetime.fromtimestamp(int(starts_at), tz=UTC)
            elif not isinstance(starts_at, datetime):
                # Если это строка или другой формат, пытаемся парсить
                try:
                    from dateutil.parser import parse

                    event["starts_at"] = parse(str(starts_at)).replace(tzinfo=UTC)
                except Exception:
                    # Фоллбек на сегодня в 12:00
                    now = datetime.now(ZoneInfo("Europe/Moscow"))
                    today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
                    event["starts_at"] = today_noon.astimezone(UTC)

        # Проверяем, что событие в разумных временных рамках
        now_utc = datetime.now(UTC)

        # Для KudaGo: принимаем события на сегодня и завтра (для тестирования)
        if event.get("source") == "kudago":
            # Получаем начало сегодня и конец завтра по московскому времени
            moscow_tz = ZoneInfo("Europe/Moscow")
            now_moscow = datetime.now(moscow_tz)
            today_start = now_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow_end = (today_start + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)

            # Конвертируем в UTC
            today_start_utc = today_start.astimezone(UTC)
            tomorrow_end_utc = tomorrow_end.astimezone(UTC)

            # Принимаем события на сегодня и завтра
            if today_start_utc <= starts_at <= tomorrow_end_utc:
                event_date = starts_at.astimezone(moscow_tz).date()
                today_date = now_moscow.date()
                if event_date == today_date:
                    logger.info(f"✅ KudaGo событие на СЕГОДНЯ принято: {title[:50]}")
                else:
                    logger.info(f"✅ KudaGo событие на ЗАВТРА принято: {title[:50]}")
            else:
                logger.info(f"❌ KudaGo событие не в окне отброшено: {title[:50]} (starts_at: {starts_at})")
                VALIDATION_METRICS["invalid_timestamp"] += 1
                VALIDATION_METRICS["events_dropped"] += 1
                return None
        else:
            # Для других источников: мягкий фильтр на неделю
            week_ago = now_utc - timedelta(days=7)
            week_ahead = now_utc + timedelta(days=7)
            if starts_at < week_ago or starts_at > week_ahead:
                logger.info(
                    f"Событие вне временного окна отброшено в {city}: {title[:50]} "
                    f"(starts_at: {starts_at}, now: {now_utc})"
                )
                VALIDATION_METRICS["invalid_timestamp"] += 1
                VALIDATION_METRICS["events_dropped"] += 1
                return None

        # 3. Валидация URL
        source_url = event.get("source_url", "").strip()
        if source_url and not _is_valid_kudago_url(source_url):
            logger.debug(f"Невалидный URL в {city}: {source_url}")
            VALIDATION_METRICS["invalid_url"] += 1
            source_url = ""  # Очищаем невалидный URL

        # 4. Валидация координат
        lat = event.get("lat")
        lng = event.get("lng")
        if lat is None or lng is None:
            VALIDATION_METRICS["missing_coordinates"] += 1
            logger.debug(f"Событие без координат в {city}: {title[:50]}")
            # Не отбрасываем, но помечаем

        # 5. Валидация страны и города
        country_code = event.get("country_code", "RU")
        event_city = event.get("city", "")

        if country_code != "RU":
            logger.warning(f"Неожиданная страна в событии: {country_code}")

        if event_city not in {"moscow", "spb"}:
            logger.warning(f"Неожиданный город в событии: {event_city}")

        # Создаем валидированное событие
        validated_event = {
            "title": title,
            "starts_at": starts_at,
            "ends_at": event.get("ends_at"),
            "lat": lat,
            "lng": lng,
            "lon": lng,  # Добавляем поле lon для совместимости
            "venue_name": (event.get("venue_name", "") or "").strip(),
            "location_name": (event.get("venue_name", "") or "").strip(),  # Добавляем location_name для SQL
            "address": (event.get("address", "") or "").strip(),
            "source_url": source_url,
            "url": source_url,  # Добавляем поле url для SQL запроса
            "country_code": country_code,
            "city": event_city,
            "source": event.get("source", "kudago"),
            "source_id": event.get("source_id"),
            "raw": event.get("raw", {}),
        }

        # Убираем пустые поля
        validated_event = {k: v for k, v in validated_event.items() if v is not None and v != ""}

        logger.debug(f"Событие валидировано в {city}: {title[:50]}")
        return validated_event

    except Exception as e:
        logger.error(f"Ошибка валидации события в {city}: {e}")
        VALIDATION_METRICS["validation_errors"] += 1
        VALIDATION_METRICS["events_dropped"] += 1
        return None


def _is_valid_kudago_url(url: str) -> bool:
    """Проверяет, что URL является валидным KudaGo URL"""
    if not url:
        return False

    # Проверяем базовый домен KudaGo
    kudago_patterns = [
        r"^https://kudago\.com/",
        r"^https://www\.kudago\.com/",
        r"^http://kudago\.com/",
        r"^http://www\.kudago\.com/",
    ]

    for pattern in kudago_patterns:
        if re.match(pattern, url):
            return True

    return False


def validate_events_batch(events: list[dict[str, Any]], city: str = "unknown") -> list[dict[str, Any]]:
    """
    Валидирует пакет событий

    Args:
        events: Список сырых событий
        city: Город для логирования

    Returns:
        Список валидированных событий
    """
    validated_events = []

    for event in events:
        validated = validate_event(event, city)
        if validated:
            validated_events.append(validated)
        else:
            logger.info(f"Событие отброшено валидатором: '{event.get('title', 'Без названия')}'")

    logger.info(f"Валидация в {city}: {len(validated_events)}/{len(events)} событий прошли валидацию")
    return validated_events


def get_validation_metrics() -> dict[str, int]:
    """Возвращает метрики валидации"""
    return VALIDATION_METRICS.copy()


def reset_validation_metrics() -> None:
    """Сбрасывает метрики валидации (для тестов)"""
    for key in VALIDATION_METRICS:
        VALIDATION_METRICS[key] = 0


def get_validation_summary() -> dict[str, Any]:
    """Возвращает сводку по валидации"""
    total = VALIDATION_METRICS["events_validated"]
    if total == 0:
        return {"status": "no_events", "total": 0}

    dropped = VALIDATION_METRICS["events_dropped"]
    success_rate = ((total - dropped) / total) * 100

    return {
        "status": "ok" if success_rate > 80 else "warning" if success_rate > 60 else "error",
        "total_events": total,
        "validated_events": total - dropped,
        "dropped_events": dropped,
        "success_rate_percent": round(success_rate, 1),
        "title_truncated": VALIDATION_METRICS["title_truncated"],
        "invalid_timestamp": VALIDATION_METRICS["invalid_timestamp"],
        "missing_coordinates": VALIDATION_METRICS["missing_coordinates"],
        "invalid_url": VALIDATION_METRICS["invalid_url"],
        "validation_errors": VALIDATION_METRICS["validation_errors"],
    }
