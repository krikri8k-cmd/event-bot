#!/usr/bin/env python3
"""
Упрощенный сервис для работы с событиями через единую таблицу events
"""

# DEPRECATED: not used since 2025-09-18. Do not import in new code.
# Replaced by: utils/unified_events_service.py (UnifiedEventsService)
# This module will be removed in next cleanup phase.

import logging
import warnings

warnings.warn("SimpleEventsService is deprecated. Use UnifiedEventsService instead.", DeprecationWarning, stacklevel=2)
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class SimpleEventsService:
    """Упрощенный сервис для работы с событиями через единую таблицу events"""

    def __init__(self, engine: Engine):
        self.engine = engine

    async def find_events_by_city(
        self,
        city: str,
        center_lat: float | None = None,
        center_lng: float | None = None,
        radius_km: float = 5,
        days_ahead: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Находит события в указанном городе

        Args:
            city: Город поиска (bali, moscow, spb)
            center_lat: Широта центра поиска
            center_lng: Долгота центра поиска
            radius_km: Радиус поиска в км
            days_ahead: Количество дней вперед для поиска

        Returns:
            Список событий
        """
        try:
            # Время поиска
            now = datetime.utcnow()
            end_time = now + timedelta(days=days_ahead)

            # Базовый SQL
            sql = """
                SELECT id, source, external_id, title, description, starts_at, ends_at,
                       url, location_name, location_url, lat, lng, country, city,
                       organizer_id, organizer_username, max_participants, current_participants,
                       participants_ids, status, created_at_utc, updated_at_utc,
                       is_generated_by_ai
                FROM events
                WHERE city = :city
                AND starts_at BETWEEN :start_time AND :end_time
                AND starts_at > NOW()
            """

            params = {
                "city": city,
                "start_time": now,
                "end_time": end_time,
            }

            # Фильтр по геолокации (если указан)
            if center_lat and center_lng:
                sql += """
                    AND lat IS NOT NULL AND lng IS NOT NULL
                    AND (
                        6371 * acos(
                            GREATEST(-1, LEAST(1,
                                cos(radians(:center_lat)) * cos(radians(lat)) *
                                cos(radians(lng) - radians(:center_lng)) +
                                sin(radians(:center_lat)) * sin(radians(lat))
                            ))
                        )
                    ) <= :radius_km
                """
                params["center_lat"] = center_lat
                params["center_lng"] = center_lng
                params["radius_km"] = radius_km

            # Сортировка
            sql += " ORDER BY starts_at ASC"

            # Выполняем запрос
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params)
                events = []
                for row in result:
                    event_dict = {
                        "id": row[0],
                        "source": row[1],
                        "external_id": row[2],
                        "title": row[3],
                        "description": row[4],
                        "starts_at": row[5],
                        "ends_at": row[6],
                        "url": row[7],
                        "location_name": row[8],
                        "location_url": row[9],
                        "lat": row[10],
                        "lng": row[11],
                        "country": row[12],
                        "city": row[13],
                        "organizer_id": row[14],
                        "organizer_username": row[15],
                        "max_participants": row[16],
                        "current_participants": row[17],
                        "participants_ids": row[18],
                        "status": row[19],
                        "created_at_utc": row[20],
                        "updated_at_utc": row[21],
                        "is_generated_by_ai": row[22],
                    }
                    events.append(event_dict)

                logger.info(f"Найдено {len(events)} событий в городе {city}")
                return events

        except Exception as e:
            logger.error(f"Ошибка поиска событий в городе {city}: {e}")
            return []

    async def find_today_events(
        self,
        city: str,
        center_lat: float | None = None,
        center_lng: float | None = None,
        radius_km: float = 5,
    ) -> list[dict[str, Any]]:
        """
        Находит события на сегодня в городе

        Args:
            city: Город поиска
            center_lat: Широта центра поиска
            center_lng: Долгота центра поиска
            radius_km: Радиус поиска

        Returns:
            Список событий на сегодня
        """
        return await self.find_events_by_city(
            city=city, center_lat=center_lat, center_lng=center_lng, radius_km=radius_km, days_ahead=1
        )

    async def find_events_by_location(
        self,
        center_lat: float,
        center_lng: float,
        radius_km: float = 5,
        days_ahead: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Находит события по геолокации (все города)

        Args:
            center_lat: Широта центра поиска
            center_lng: Долгота центра поиска
            radius_km: Радиус поиска в км
            days_ahead: Количество дней вперед для поиска

        Returns:
            Список событий
        """
        try:
            # Время поиска
            now = datetime.utcnow()
            end_time = now + timedelta(days=days_ahead)

            # SQL для поиска по геолокации
            sql = """
                SELECT id, source, external_id, title, description, starts_at, ends_at,
                       url, location_name, location_url, lat, lng, country, city,
                       organizer_id, organizer_username, max_participants, current_participants,
                       participants_ids, status, created_at_utc, updated_at_utc,
                       is_generated_by_ai
                FROM events
                WHERE starts_at BETWEEN :start_time AND :end_time
                AND starts_at > NOW()
                AND lat IS NOT NULL AND lng IS NOT NULL
                AND (
                    6371 * acos(
                        GREATEST(-1, LEAST(1,
                            cos(radians(:center_lat)) * cos(radians(lat)) *
                            cos(radians(lng) - radians(:center_lng)) +
                            sin(radians(:center_lat)) * sin(radians(lat))
                        ))
                    )
                ) <= :radius_km
                ORDER BY starts_at ASC
            """

            params = {
                "start_time": now,
                "end_time": end_time,
                "center_lat": center_lat,
                "center_lng": center_lng,
                "radius_km": radius_km,
            }

            # Выполняем запрос
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params)
                events = []
                for row in result:
                    event_dict = {
                        "id": row[0],
                        "source": row[1],
                        "external_id": row[2],
                        "title": row[3],
                        "description": row[4],
                        "starts_at": row[5],
                        "ends_at": row[6],
                        "url": row[7],
                        "location_name": row[8],
                        "location_url": row[9],
                        "lat": row[10],
                        "lng": row[11],
                        "country": row[12],
                        "city": row[13],
                        "organizer_id": row[14],
                        "organizer_username": row[15],
                        "max_participants": row[16],
                        "current_participants": row[17],
                        "participants_ids": row[18],
                        "status": row[19],
                        "created_at_utc": row[20],
                        "updated_at_utc": row[21],
                        "is_generated_by_ai": row[22],
                    }
                    events.append(event_dict)

                logger.info(f"Найдено {len(events)} событий в радиусе {radius_km}км")
                return events

        except Exception as e:
            logger.error(f"Ошибка поиска событий по геолокации: {e}")
            return []

    async def get_event_by_id(self, event_id: int) -> dict[str, Any] | None:
        """
        Получает событие по ID

        Args:
            event_id: ID события

        Returns:
            Данные события или None
        """
        try:
            sql = """
                SELECT id, source, external_id, title, description, starts_at, ends_at,
                       url, location_name, location_url, lat, lng, country, city,
                       organizer_id, organizer_username, max_participants, current_participants,
                       participants_ids, status, created_at_utc, updated_at_utc,
                       is_generated_by_ai
                FROM events
                WHERE id = :event_id
            """

            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {"event_id": event_id}).fetchone()

                if not result:
                    return None

                event_dict = {
                    "id": result[0],
                    "source": result[1],
                    "external_id": result[2],
                    "title": result[3],
                    "description": result[4],
                    "starts_at": result[5],
                    "ends_at": result[6],
                    "url": result[7],
                    "location_name": result[8],
                    "location_url": result[9],
                    "lat": result[10],
                    "lng": result[11],
                    "country": result[12],
                    "city": result[13],
                    "organizer_id": result[14],
                    "organizer_username": result[15],
                    "max_participants": result[16],
                    "current_participants": result[17],
                    "participants_ids": result[18],
                    "status": result[19],
                    "created_at_utc": result[20],
                    "updated_at_utc": result[21],
                    "is_generated_by_ai": result[22],
                }
                return event_dict

        except Exception as e:
            logger.error(f"Ошибка получения события {event_id}: {e}")
            return None

    async def sync_parser_events_to_main_table(self) -> bool:
        """
        Синхронизирует события из events_parser в основную таблицу events

        Returns:
            True если успешно
        """
        try:
            with self.engine.begin() as conn:
                # Вставляем новые события из events_parser
                insert_sql = """
                    INSERT INTO events (
                        source, external_id, title, description, starts_at, ends_at,
                        url, location_name, location_url, lat, lng, country, city,
                        created_at_utc, updated_at_utc, is_generated_by_ai
                    )
                    SELECT
                        source, external_id, title, description, starts_at, ends_at,
                        url, location_name, location_url, lat, lng, country, city,
                        created_at_utc, updated_at_utc,
                        CASE WHEN source = 'ai' THEN true ELSE false END as is_generated_by_ai
                    FROM events_parser
                    WHERE (source, external_id) NOT IN (
                        SELECT source, external_id FROM events WHERE source != 'user'
                    )
                """

                result = conn.execute(text(insert_sql))
                logger.info(f"Синхронизировано {result.rowcount} новых парсерных событий")

                return True

        except Exception as e:
            logger.error(f"Ошибка синхронизации парсерных событий: {e}")
            return False

    async def sync_user_events_to_main_table(self) -> bool:
        """
        Синхронизирует события из events_user в основную таблицу events

        Returns:
            True если успешно
        """
        try:
            with self.engine.begin() as conn:
                # Вставляем новые события из events_user
                insert_sql = """
                    INSERT INTO events (
                        source, external_id, title, description, starts_at, ends_at,
                        url, location_name, location_url, lat, lng, country, city,
                        organizer_id, organizer_username, max_participants, current_participants,
                        participants_ids, status, created_at_utc, updated_at_utc, is_generated_by_ai
                    )
                    SELECT
                        'user' as source,
                        id::text as external_id,
                        title, description, starts_at, ends_at,
                        url, location_name, location_url, lat, lng, country, city,
                        organizer_id, organizer_username, max_participants, current_participants,
                        participants_ids, status, created_at_utc, updated_at_utc, false as is_generated_by_ai
                    FROM events_user
                    WHERE id NOT IN (
                        SELECT CAST(external_id AS INTEGER) FROM events WHERE source = 'user'
                    )
                """

                result = conn.execute(text(insert_sql))
                logger.info(f"Синхронизировано {result.rowcount} новых пользовательских событий")

                return True

        except Exception as e:
            logger.error(f"Ошибка синхронизации пользовательских событий: {e}")
            return False
