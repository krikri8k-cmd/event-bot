#!/usr/bin/env python3
"""
Сервис для работы с событиями с поддержкой регионального разделения
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .region_router import EventType, Region, detect_region, get_region_filter, get_source_by_region

logger = logging.getLogger(__name__)


class EventsService:
    """Сервис для работы с событиями с региональным разделением"""

    def __init__(self, engine: Engine):
        self.engine = engine

    async def upsert_parser_event(self, event_data: dict[str, Any]) -> bool:
        """
        Сохраняет событие от парсера в таблицу events_parser

        Args:
            event_data: Данные события

        Returns:
            True если успешно сохранено
        """
        try:
            # Определяем регион
            region = detect_region(event_data.get("country_code"), event_data.get("city"))

            # Добавляем информацию о регионе
            event_data["country"] = "ID" if region == Region.BALI else "RU"
            if region == Region.MOSCOW:
                event_data["city"] = "moscow"
            elif region == Region.SPB:
                event_data["city"] = "spb"

            # Определяем источник
            source = get_source_by_region(region)
            event_data["source"] = source

            # Убеждаемся что есть external_id
            if not event_data.get("external_id"):
                event_data["external_id"] = event_data.get("source_id") or "unknown"

            # Добавляем значения по умолчанию для обязательных полей
            event_data.setdefault("location_url", None)
            event_data.setdefault("community_name", None)
            event_data.setdefault("community_link", None)
            event_data.setdefault("ends_at", None)

            # Upsert в таблицу events_parser
            return await self._upsert_parser_event(event_data)

        except Exception as e:
            logger.error(f"Ошибка сохранения события парсера: {e}")
            return False

    async def upsert_user_event(
        self, event_data: dict[str, Any], country_code: str | None = None, city: str | None = None
    ) -> bool:
        """
        Сохраняет пользовательское событие в таблицу events_user

        Args:
            event_data: Данные события
            country_code: Код страны пользователя
            city: Город пользователя

        Returns:
            True если успешно сохранено
        """
        try:
            # Определяем регион
            region = detect_region(country_code, city)

            # Добавляем информацию о регионе
            event_data["country"] = "ID" if region == Region.BALI else "RU"
            if region == Region.MOSCOW:
                event_data["city"] = "moscow"
            elif region == Region.SPB:
                event_data["city"] = "spb"

            # Устанавливаем значения по умолчанию для пользовательских событий
            if "status" not in event_data:
                event_data["status"] = "open"
            if "current_participants" not in event_data:
                event_data["current_participants"] = 0

            # Добавляем значения по умолчанию для обязательных полей
            event_data.setdefault("url", None)
            event_data.setdefault("location_url", None)
            event_data.setdefault("participants_ids", None)
            event_data.setdefault("community_name", None)
            event_data.setdefault("community_link", None)
            event_data.setdefault("ends_at", None)
            event_data.setdefault("max_participants", None)

            # Upsert в таблицу events_user
            return await self._upsert_user_event(event_data)

        except Exception as e:
            logger.error(f"Ошибка сохранения пользовательского события: {e}")
            return False

    async def find_events_by_region(
        self,
        region: Region,
        center_lat: float | None = None,
        center_lng: float | None = None,
        radius_km: float = 5,
        days_ahead: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Находит события в указанном регионе (из обеих таблиц)

        Args:
            region: Регион поиска
            center_lat: Широта центра поиска
            center_lng: Долгота центра поиска
            radius_km: Радиус поиска в км
            days_ahead: Количество дней вперед для поиска

        Returns:
            Список событий
        """
        try:
            # Получаем фильтры для региона
            region_filters = get_region_filter(region, EventType.PARSER)

            # Время поиска
            now = datetime.utcnow()
            end_time = now + timedelta(days=days_ahead)

            # SQL для объединения событий из обеих таблиц
            sql = """
                SELECT id, title, description, starts_at, ends_at, url,
                       location_name, location_url, lat, lng,
                       country, city, created_at_utc,
                       'parser' as event_type, source, NULL as organizer_id
                FROM events_parser
                WHERE 1=1
            """

            params = {}

            # Добавляем фильтры региона
            if "country" in region_filters:
                sql += " AND country = :country"
                params["country"] = region_filters["country"]

            if "city" in region_filters:
                sql += " AND city = :city"
                params["city"] = region_filters["city"]

            # Фильтр по времени
            sql += " AND starts_at BETWEEN :start_time AND :end_time"
            sql += " AND starts_at > NOW()"
            params["start_time"] = now
            params["end_time"] = end_time

            # UNION с пользовательскими событиями
            sql += """
                UNION ALL
                SELECT id, title, description, starts_at, ends_at, url,
                       location_name, location_url, lat, lng,
                       country, city, created_at_utc,
                       'user' as event_type, NULL as source, organizer_id
                FROM events_user
                WHERE 1=1
            """

            # Добавляем те же фильтры для пользовательских событий
            if "country" in region_filters:
                sql += " AND country = :country"

            if "city" in region_filters:
                sql += " AND city = :city"

            # Фильтр по времени для пользовательских событий
            sql += " AND starts_at BETWEEN :start_time AND :end_time"
            sql += " AND starts_at > NOW()"

            # Фильтр по геолокации (если указан)
            if center_lat and center_lng:
                # Используем приблизительный расчет расстояния с защитой от ошибок округления
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
                        "title": row[1],
                        "description": row[2],
                        "starts_at": row[3],
                        "ends_at": row[4],
                        "url": row[5],
                        "location_name": row[6],
                        "location_url": row[7],
                        "lat": row[8],
                        "lng": row[9],
                        "country": row[10],
                        "city": row[11],
                        "created_at_utc": row[12],
                        "event_type": row[13],  # 'parser' или 'user'
                        "source": row[14],  # только для парсера
                        "organizer_id": row[15],  # только для пользователя
                    }
                    events.append(event_dict)

                logger.info(f"Найдено {len(events)} событий в регионе {region.value}")
                return events

        except Exception as e:
            logger.error(f"Ошибка поиска событий в регионе {region.value}: {e}")
            return []

    async def find_today_events(
        self,
        country_code: str | None = None,
        city: str | None = None,
        center_lat: float | None = None,
        center_lng: float | None = None,
        radius_km: float = 5,
    ) -> list[dict[str, Any]]:
        """
        Находит события на сегодня в регионе пользователя

        Args:
            country_code: Код страны пользователя
            city: Город пользователя
            center_lat: Широта центра поиска
            center_lng: Долгота центра поиска
            radius_km: Радиус поиска

        Returns:
            Список событий на сегодня
        """
        # Определяем регион
        region = detect_region(country_code, city)

        # Ищем события на сегодня
        return await self.find_events_by_region(
            region=region, center_lat=center_lat, center_lng=center_lng, radius_km=radius_km, days_ahead=1
        )

    async def _upsert_parser_event(self, event_data: dict[str, Any]) -> bool:
        """
        Выполняет upsert события парсера в таблицу events_parser

        Args:
            event_data: Данные события

        Returns:
            True если успешно
        """
        try:
            # Проверяем обязательные поля
            if not event_data.get("title"):
                logger.error("Отсутствует обязательное поле 'title'")
                return False

            if not event_data.get("source"):
                logger.error("Отсутствует обязательное поле 'source' для парсера")
                return False

            # Подготавливаем данные для upsert в events_parser
            upsert_sql = """
                INSERT INTO events_parser (
                    source, external_id, title, starts_at, ends_at,
                    url, location_name, location_url, lat, lng, country, city,
                    community_name, community_link, created_at_utc, updated_at_utc
                ) VALUES (
                    :source, :external_id, :title, :starts_at, :ends_at,
                    :url, :location_name, :location_url, :lat, :lng, :country, :city,
                    :community_name, :community_link, NOW(), NOW()
                )
                ON CONFLICT (source, external_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    starts_at = EXCLUDED.starts_at,
                    ends_at = EXCLUDED.ends_at,
                    url = EXCLUDED.url,
                    location_name = EXCLUDED.location_name,
                    location_url = EXCLUDED.location_url,
                    lat = EXCLUDED.lat,
                    lng = EXCLUDED.lng,
                    country = EXCLUDED.country,
                    city = EXCLUDED.city,
                    community_name = EXCLUDED.community_name,
                    community_link = EXCLUDED.community_link,
                    updated_at_utc = NOW()
            """

            # Логируем SQL параметры для отладки
            logger.debug("SQL upsert событий парсера:")
            logger.debug("SQL: %s", upsert_sql)
            logger.debug(
                "PARAMS: %s", {k: str(v) if not isinstance(v, int | float | str) else v for k, v in event_data.items()}
            )

            # Выполняем upsert
            with self.engine.begin() as conn:
                conn.execute(text(upsert_sql), event_data)

            logger.info(f"Событие парсера '{event_data.get('title')}' успешно сохранено в events_parser")
            return True

        except Exception as e:
            logger.error(f"Ошибка upsert события парсера: {e}")
            return False

    async def _upsert_user_event(self, event_data: dict[str, Any]) -> bool:
        """
        Выполняет upsert пользовательского события в таблицу events_user

        Args:
            event_data: Данные события

        Returns:
            True если успешно
        """
        try:
            # Проверяем обязательные поля
            if not event_data.get("title"):
                logger.error("Отсутствует обязательное поле 'title'")
                return False

            # Подготавливаем данные для upsert в events_user
            upsert_sql = """
                INSERT INTO events_user (
                    organizer_id, organizer_username, title, description, starts_at, ends_at,
                    url, location_name, location_url, lat, lng, country, city,
                    max_participants, current_participants, participants_ids, status,
                    community_name, community_link, created_at_utc, updated_at_utc
                ) VALUES (
                    :organizer_id, :organizer_username, :title, :description, :starts_at, :ends_at,
                    :url, :location_name, :location_url, :lat, :lng, :country, :city,
                    :max_participants, :current_participants, :participants_ids, :status,
                    :community_name, :community_link, NOW(), NOW()
                )
                ON CONFLICT (organizer_id, title, starts_at)
                DO UPDATE SET
                    description = EXCLUDED.description,
                    ends_at = EXCLUDED.ends_at,
                    url = EXCLUDED.url,
                    location_name = EXCLUDED.location_name,
                    location_url = EXCLUDED.location_url,
                    lat = EXCLUDED.lat,
                    lng = EXCLUDED.lng,
                    country = EXCLUDED.country,
                    city = EXCLUDED.city,
                    max_participants = EXCLUDED.max_participants,
                    current_participants = EXCLUDED.current_participants,
                    participants_ids = EXCLUDED.participants_ids,
                    status = EXCLUDED.status,
                    community_name = EXCLUDED.community_name,
                    community_link = EXCLUDED.community_link,
                    updated_at_utc = NOW()
            """

            # Выполняем upsert
            with self.engine.begin() as conn:
                conn.execute(text(upsert_sql), event_data)

            logger.info(f"Пользовательское событие '{event_data.get('title')}' успешно сохранено в events_user")
            return True

        except Exception as e:
            logger.error(f"Ошибка upsert пользовательского события: {e}")
            return False
