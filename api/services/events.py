#!/usr/bin/env python3
"""
Сервис для поиска событий по локации и радиусу
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from database import get_session
from utils.geo_utils import bbox_around, haversine_km, validate_coordinates

logger = logging.getLogger(__name__)

# Загружаем настройки
DEFAULT_RADIUS = float(os.getenv("DEFAULT_RADIUS_KM", "5"))
MAX_RADIUS = float(os.getenv("MAX_RADIUS_KM", "15"))
RADIUS_STEP = float(os.getenv("RADIUS_STEP_KM", "5"))
BALI_TZ = ZoneInfo(os.getenv("DEFAULT_TZ", "Asia/Makassar"))  # UTC+8
NEARBY_DAYS_AHEAD = int(os.getenv("NEARBY_DAYS_AHEAD", "0"))
EXTENDED_DAYS_AHEAD = int(os.getenv("EXTENDED_DAYS_AHEAD", "0"))


def get_events_nearby(lat: float, lon: float, radius_km: float = None, limit: int = 50) -> list[dict[str, Any]]:
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
                  AND (starts_at >= NOW() OR (starts_at IS NULL AND time_utc >= NOW()))
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

            logger.info(f"Найдено {len(enriched)} событий в радиусе {radius_km} км от ({lat}, {lon})")
            return enriched[:limit]

    except Exception as e:
        logger.error(f"Ошибка при поиске событий: {e}")
        return []


def get_events_stats() -> dict[str, Any]:
    """Получает статистику по событиям."""
    try:
        with get_session() as session:
            total = session.execute(text("SELECT COUNT(*) as count FROM events")).scalar()
            with_coords = session.execute(
                text("SELECT COUNT(*) as count FROM events WHERE lat IS NOT NULL AND lng IS NOT NULL")
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
                  AND (starts_at >= NOW() OR (starts_at IS NULL AND time_utc >= NOW()))
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

            # Пагинация
            total = len(filtered)
            page = filtered[offset : offset + limit]

            logger.info(f"Найдено {total} событий на сегодня в радиусе {radius_km} км от ({lat}, {lon})")
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
                  AND (starts_at >= NOW() OR (starts_at IS NULL AND time_utc >= NOW()))
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
