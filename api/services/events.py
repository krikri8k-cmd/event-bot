#!/usr/bin/env python3
"""
Сервис для поиска событий по локации и радиусу
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from database import get_session
from utils.geo import bbox_around, find_user_region, haversine_km, inside_bbox, validate_coordinates

logger = logging.getLogger(__name__)

# Загружаем настройки
DEFAULT_RADIUS = float(os.getenv("DEFAULT_RADIUS_KM", "5"))
MAX_RADIUS = float(os.getenv("MAX_RADIUS_KM", "30"))
STRICT_REGION_FILTER = os.getenv("STRICT_REGION_FILTER", "0") in ("1", "true", "True")
BALI_TZ = ZoneInfo(os.getenv("DEFAULT_TZ", "Asia/Makassar"))  # UTC+8
NEARBY_DAYS_AHEAD = int(os.getenv("NEARBY_DAYS_AHEAD", "0"))
EXTENDED_DAYS_AHEAD = int(os.getenv("EXTENDED_DAYS_AHEAD", "0"))

try:
    GEO_BBOXES = json.loads(os.getenv("GEO_REGION_BBOXES", "{}"))
except json.JSONDecodeError:
    logger.warning("Неверный формат GEO_REGION_BBOXES, используем пустой словарь")
    GEO_BBOXES = {}


def get_events_nearby(
    lat: float, lon: float, radius_km: float = None, limit: int = 50
) -> list[dict[str, Any]]:
    """
    Находит события рядом с указанной точкой.

    Args:
        lat: Широта
        lon: Долгота
        radius_km: Радиус поиска в км
        limit: Максимальное количество событий

    Returns:
        Список событий с расстоянием до пользователя
    """
    if not validate_coordinates(lat, lon):
        logger.error(f"Некорректные координаты: ({lat}, {lon})")
        return []

    radius_km = float(radius_km or DEFAULT_RADIUS)

    try:
        with get_session() as session:
            # 1) Первичный отбор по рамке (быстро и дешево)
            min_lat, max_lat, min_lon, max_lon = bbox_around(lat, lon, radius_km)

            rows = (
                session.execute(
                    text("""
                SELECT id, title, description, time_utc, starts_at,
                       lat, lng, location_name, source, url,
                       status, created_at_utc, updated_at_utc,
                       city, country, organizer_id, organizer_url
                FROM events
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                  AND lat BETWEEN :min_lat AND :max_lat
                  AND lng BETWEEN :min_lon AND :max_lon
                ORDER BY created_at_utc DESC
                LIMIT :lim
                """),
                    dict(
                        min_lat=min_lat,
                        max_lat=max_lat,
                        min_lon=min_lon,
                        max_lon=max_lon,
                        lim=limit * 5,
                    ),
                )
                .mappings()
                .all()
            )

            # 2) Точная фильтрация по радиусу и сортировка
            enriched = []
            for row in rows:
                distance = haversine_km(lat, lon, row["lat"], row["lng"])
                if distance <= radius_km:
                    event_dict = dict(row)
                    event_dict["distance_km"] = round(distance, 2)
                    enriched.append(event_dict)

            enriched.sort(key=lambda x: x["distance_km"])

            # 3) Жёсткий фильтр по региону (если включено)
            if STRICT_REGION_FILTER and GEO_BBOXES:
                region = find_user_region(lat, lon, GEO_BBOXES)
                if region != "unknown" and enriched:
                    logger.info(f"Применяем региональный фильтр для региона: {region}")
                    bb = GEO_BBOXES[region]
                    original_count = len(enriched)
                    enriched = [
                        e
                        for e in enriched
                        if e["lat"] is not None
                        and e["lng"] is not None
                        and inside_bbox(e["lat"], e["lng"], bb)
                    ]
                    filtered_count = original_count - len(enriched)
                    if filtered_count > 0:
                        logger.info(f"Отфильтровано {filtered_count} событий вне региона {region}")

            logger.info(
                f"Найдено {len(enriched)} событий в радиусе {radius_km} км от ({lat}, {lon})"
            )
            return enriched[:limit]

    except Exception as e:
        logger.error(f"Ошибка при поиске событий: {e}")
        return []


def get_events_by_region(region: str, limit: int = 50) -> list[dict[str, Any]]:
    """Получает события по региону."""
    if region not in GEO_BBOXES:
        logger.warning(f"Неизвестный регион: {region}")
        return []

    bb = GEO_BBOXES[region]

    try:
        with get_session() as session:
            rows = (
                session.execute(
                    text("""
                SELECT id, title, description, time_utc, starts_at,
                       lat, lng, location_name, source, url,
                       status, created_at_utc, updated_at_utc,
                       city, country, organizer_id, organizer_url
                FROM events
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                  AND lat BETWEEN :min_lat AND :max_lat
                  AND lng BETWEEN :min_lon AND :max_lon
                ORDER BY created_at_utc DESC
                LIMIT :lim
                """),
                    dict(
                        min_lat=bb["min_lat"],
                        max_lat=bb["max_lat"],
                        min_lon=bb["min_lon"],
                        max_lon=bb["max_lon"],
                        lim=limit,
                    ),
                )
                .mappings()
                .all()
            )

            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Ошибка при получении событий по региону {region}: {e}")
        return []


def get_events_stats() -> dict[str, Any]:
    """Получает статистику по событиям."""
    try:
        with get_session() as session:
            total = session.execute(text("SELECT COUNT(*) as count FROM events")).scalar()
            with_coords = session.execute(
                text(
                    "SELECT COUNT(*) as count FROM events WHERE lat IS NOT NULL AND lng IS NOT NULL"
                )
            ).scalar()

            return {
                "total_events": total,
                "events_with_coordinates": with_coords,
                "events_without_coordinates": total - with_coords if total else 0,
            }
    except Exception as e:
        logger.error(f"Ошибка при получении статистики событий: {e}")
        return {}


def start_end_of_today(tz: ZoneInfo = BALI_TZ) -> tuple[datetime, datetime]:
    """Возвращает начало и конец сегодняшнего дня в указанной таймзоне."""
    now = datetime.now(tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1 + NEARBY_DAYS_AHEAD)
    return start, end


def get_events_nearby_today(
    lat: float, lon: float, radius_km: float = None, limit: int = 20, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """
    Находит события на сегодня рядом с указанной точкой.

    Args:
        lat: Широта
        lon: Долгота
        radius_km: Радиус поиска в км
        limit: Максимальное количество событий на странице
        offset: Смещение для пагинации

    Returns:
        Кортеж (список событий с расстоянием, общее количество)
    """
    if not validate_coordinates(lat, lon):
        logger.error(f"Некорректные координаты: ({lat}, {lon})")
        return [], 0

    radius_km = float(radius_km or DEFAULT_RADIUS)
    start, end = start_end_of_today()

    try:
        with get_session() as session:
            # 1) Первичный отбор по рамке и времени (быстро и дешево)
            min_lat, max_lat, min_lon, max_lon = bbox_around(lat, lon, radius_km)

            rows = (
                session.execute(
                    text("""
                SELECT id, title, description, time_utc, starts_at,
                       lat, lng, location_name, source, url,
                       status, created_at_utc, updated_at_utc, city, country
                FROM events
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                  AND lat BETWEEN :min_lat AND :max_lat
                  AND lng BETWEEN :min_lon AND :max_lon
                  AND time_utc >= :start_utc AND time_utc < :end_utc
                ORDER BY time_utc ASC
                LIMIT :lim
                """),
                    dict(
                        min_lat=min_lat,
                        max_lat=max_lat,
                        min_lon=min_lon,
                        max_lon=max_lon,
                        start_utc=start.astimezone(ZoneInfo("UTC")),
                        end_utc=end.astimezone(ZoneInfo("UTC")),
                        lim=limit * 10,
                    ),  # Берем больше для фильтрации
                )
                .mappings()
                .all()
            )

            # 2) Точная фильтрация по радиусу и сортировка
            filtered = []
            for row in rows:
                distance = haversine_km(lat, lon, row["lat"], row["lng"])
                if distance <= radius_km:
                    event_dict = dict(row)
                    event_dict["distance_km"] = round(distance, 2)
                    filtered.append((event_dict, distance))

            # Сортировка по времени, затем по расстоянию
            filtered.sort(key=lambda x: (x[0]["time_utc"], x[1]))

            # 3) Жёсткий фильтр по региону (если включено)
            if STRICT_REGION_FILTER and GEO_BBOXES:
                region = find_user_region(lat, lon, GEO_BBOXES)
                if region != "unknown" and filtered:
                    logger.info(f"Применяем региональный фильтр для региона: {region}")
                    bb = GEO_BBOXES[region]
                    original_count = len(filtered)
                    filtered = [
                        (e, d)
                        for e, d in filtered
                        if e["lat"] is not None
                        and e["lng"] is not None
                        and inside_bbox(e["lat"], e["lng"], bb)
                    ]
                    filtered_count = original_count - len(filtered)
                    if filtered_count > 0:
                        logger.info(f"Отфильтровано {filtered_count} событий вне региона {region}")

            # Пагинация
            total = len(filtered)
            page = filtered[offset : offset + limit]

            logger.info(
                f"Найдено {total} событий на сегодня в радиусе {radius_km} км от ({lat}, {lon})"
            )
            return [event for event, _ in page], total

    except Exception as e:
        logger.error(f"Ошибка при поиске событий на сегодня: {e}")
        return [], 0


def get_cities_with_counts_today() -> list[dict[str, Any]]:
    """Получает список городов с количеством событий на сегодня."""
    start, end = start_end_of_today()

    try:
        with get_session() as session:
            rows = (
                session.execute(
                    text("""
                SELECT COALESCE(city, 'Unknown') AS city, COUNT(*) AS cnt
                FROM events
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                  AND time_utc >= :start_utc AND time_utc < :end_utc
                GROUP BY city
                HAVING COUNT(*) > 0
                ORDER BY cnt DESC
                """),
                    dict(
                        start_utc=start.astimezone(ZoneInfo("UTC")),
                        end_utc=end.astimezone(ZoneInfo("UTC")),
                    ),
                )
                .mappings()
                .all()
            )

            # Фильтр по региону Бали (если включено)
            if STRICT_REGION_FILTER and GEO_BBOXES and "bali" in GEO_BBOXES:
                bb = GEO_BBOXES["bali"]
                filtered_cities = []
                for row in rows:
                    # Проверяем, есть ли события в этом городе в рамках Бали
                    city_events = session.execute(
                        text("""
                        SELECT COUNT(*) as cnt
                        FROM events
                        WHERE city = :city
                          AND lat IS NOT NULL AND lng IS NOT NULL
                          AND lat BETWEEN :min_lat AND :max_lat
                          AND lng BETWEEN :min_lon AND :max_lon
                          AND time_utc >= :start_utc AND time_utc < :end_utc
                        """),
                        dict(
                            city=row["city"],
                            min_lat=bb["min_lat"],
                            max_lat=bb["max_lat"],
                            min_lon=bb["min_lon"],
                            max_lon=bb["max_lon"],
                            start_utc=start.astimezone(ZoneInfo("UTC")),
                            end_utc=end.astimezone(ZoneInfo("UTC")),
                        ),
                    ).scalar()

                    if city_events > 0:
                        filtered_cities.append({"city": row["city"], "cnt": city_events})

                return filtered_cities

            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Ошибка при получении городов с событиями: {e}")
        return []


def get_events_today_by_city(city: str, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    """Получает события на сегодня в указанном городе."""
    start, end = start_end_of_today()

    try:
        with get_session() as session:
            rows = (
                session.execute(
                    text("""
                SELECT id, title, description, time_utc, starts_at,
                       lat, lng, location_name, source, url,
                       status, created_at_utc, updated_at_utc, city, country
                FROM events
                WHERE lat IS NOT NULL AND lng IS NOT NULL
                  AND time_utc >= :start_utc AND time_utc < :end_utc
                  AND LOWER(city) = LOWER(:city)
                ORDER BY time_utc ASC
                LIMIT :lim OFFSET :offset
                """),
                    dict(
                        start_utc=start.astimezone(ZoneInfo("UTC")),
                        end_utc=end.astimezone(ZoneInfo("UTC")),
                        city=city,
                        lim=limit,
                        offset=offset,
                    ),
                )
                .mappings()
                .all()
            )

            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Ошибка при получении событий в городе {city}: {e}")
        return []
