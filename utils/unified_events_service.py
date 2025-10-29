"""
УНИФИЦИРОВАННЫЙ сервис для работы с событиями через единую таблицу events
"""

import logging
import time
from datetime import datetime

from sqlalchemy import text

from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc
from utils.structured_logging import StructuredLogger

logger = logging.getLogger(__name__)


class UnifiedEventsService:
    """Унифицированный сервис для работы с единой таблицей events"""

    def __init__(self, engine):
        self.engine = engine

    def search_events_today(
        self,
        city: str,
        user_lat: float | None = None,
        user_lng: float | None = None,
        radius_km: float = 15,
        message_id: str | None = None,
    ) -> list[dict]:
        """
        Поиск сегодняшних событий из единой таблицы events
        """
        start_time = time.time()

        # Получаем временные границы для города
        start_utc = get_today_start_utc(city)
        end_utc = get_tomorrow_start_utc(city)

        logger.info(f"🔍 SEARCH: city='{city}', user_lat={user_lat}, user_lng={user_lng}, radius_km={radius_km}")

        with self.engine.connect() as conn:
            if user_lat and user_lng:
                # Поиск с координатами и радиусом
                query = text("""
                    SELECT source, id, title, description, starts_at,
                           location_name as city, lat, lng, location_name, location_url, url as event_url,
                           organizer_id, organizer_username, max_participants,
                           current_participants, status, created_at_utc,
                           community_name as country, community_name as venue_name, location_name as address,
                           '' as geo_hash, starts_at as starts_at_normalized
                    FROM events
                    WHERE starts_at >= :start_utc
                    AND starts_at < :end_utc
                    AND lat IS NOT NULL AND lng IS NOT NULL
                    AND status NOT IN ('closed', 'canceled')
                    AND 6371 * acos(
                        GREATEST(-1, LEAST(1,
                            cos(radians(:user_lat)) * cos(radians(lat)) *
                            cos(radians(lng) - radians(:user_lng)) +
                            sin(radians(:user_lat)) * sin(radians(lat))
                        ))
                    ) <= :radius_km
                    ORDER BY starts_at
                """)

                result = conn.execute(
                    query,
                    {
                        "start_utc": start_utc,
                        "end_utc": end_utc,
                        "user_lat": user_lat,
                        "user_lng": user_lng,
                        "radius_km": radius_km,
                    },
                )
            else:
                # Поиск без координат
                query = text("""
                    SELECT source, id, title, description, starts_at,
                           location_name as city, lat, lng, location_name, location_url, url as event_url,
                           organizer_id, organizer_username, max_participants,
                           current_participants, status, created_at_utc,
                           community_name as country, community_name as venue_name, location_name as address,
                           '' as geo_hash, starts_at as starts_at_normalized
                    FROM events
                    WHERE starts_at >= :start_utc
                    AND starts_at < :end_utc
                    AND status NOT IN ('closed', 'canceled')
                    ORDER BY starts_at
                """)

                result = conn.execute(
                    query,
                    {
                        "start_utc": start_utc,
                        "end_utc": end_utc,
                    },
                )

            events = []
            found_user = 0
            found_parser = 0

            for row in result:
                # Определяем source_type для совместимости с существующим кодом
                source_type = "user" if row[0] == "user" else "parser"

                # Подсчитываем по источникам
                if row[0] == "user":
                    found_user += 1
                else:
                    found_parser += 1

                event_data = {
                    "source_type": source_type,
                    "source": row[0],  # Добавляем исходный source
                    "id": row[1],
                    "title": row[2],
                    "description": row[3],
                    "starts_at": row[4],
                    "city": row[5],
                    "lat": row[6],
                    "lng": row[7],
                    "location_name": row[8],
                    "location_url": row[9],
                    "event_url": row[10],
                    "organizer_id": row[11],
                    "organizer_username": row[12],
                    "max_participants": row[13],
                    "current_participants": row[14],
                    "status": row[15],
                    "created_at_utc": row[16],
                }

                # Логируем пользовательские события
                if row[0] == "user":
                    logger.info(
                        f"🔍 DB EVENT: title='{row[2]}', source='{row[0]}', "
                        f"organizer_id={row[11]}, organizer_username='{row[12]}'"
                    )

                events.append(event_data)

            # Логируем результат поиска
            empty_reason = None
            if not events:
                if user_lat and user_lng:
                    empty_reason = "no_events_in_radius"
                else:
                    empty_reason = "no_events_today"

            # Логируем результаты поиска по городам
            cities_found = {}
            for event in events:
                event_city = event.get("city", "unknown")
                cities_found[event_city] = cities_found.get(event_city, 0) + 1

            logger.info(f"🔍 SEARCH RESULT: запрашивали city='{city}', нашли события по городам: {cities_found}")

            StructuredLogger.log_search(
                region=city,
                radius_km=radius_km if user_lat and user_lng else 0,
                user_lat=user_lat or 0,
                user_lng=user_lng or 0,
                found_total=len(events),
                found_user=found_user,
                found_parser=found_parser,
                message_id=message_id,
                empty_reason=empty_reason,
                duration_ms=(time.time() - start_time) * 1000,
            )

            return events

    def get_events_stats(self, city: str) -> dict:
        """Статистика событий из единой таблицы"""
        start_utc = get_today_start_utc(city)
        end_utc = get_tomorrow_start_utc(city)

        with self.engine.connect() as conn:
            # Общая статистика
            total_result = conn.execute(
                text("""
                SELECT COUNT(*) FROM events
                WHERE city = :city
                AND starts_at >= :start_utc
                AND starts_at < :end_utc
            """),
                {"city": city, "start_utc": start_utc, "end_utc": end_utc},
            ).fetchone()

            # Статистика по источникам
            source_result = conn.execute(
                text("""
                SELECT source, COUNT(*) FROM events
                WHERE city = :city
                AND starts_at >= :start_utc
                AND starts_at < :end_utc
                GROUP BY source
            """),
                {"city": city, "start_utc": start_utc, "end_utc": end_utc},
            ).fetchall()

            # Подсчитываем пользовательские и парсерные события
            parser_events = 0
            user_events = 0

            for source, count in source_result:
                if source == "user":
                    user_events = count
                else:
                    parser_events += count

            return {
                "city": city,
                "parser_events": parser_events,
                "user_events": user_events,
                "total_events": total_result[0],
                "date_range": f"{start_utc.isoformat()} - {end_utc.isoformat()}",
            }

    def create_user_event(
        self,
        organizer_id: int,
        title: str,
        description: str,
        starts_at_utc: datetime,
        city: str,
        lat: float,
        lng: float,
        location_name: str,
        location_url: str = None,
        max_participants: int = None,
        chat_id: int = None,
        organizer_username: str = None,
    ) -> int:
        """
        Создание пользовательского события в единую таблицу events
        """
        with self.engine.begin() as conn:
            # Создаем событие напрямую в events
            user_event_query = text("""
                INSERT INTO events (
                    source, external_id, title, description, starts_at, ends_at,
                    url, location_name, location_url, lat, lng, country, city,
                    organizer_id, organizer_username, max_participants, current_participants,
                    participants_ids, status, created_at_utc, updated_at_utc, is_generated_by_ai, chat_id
                )
                VALUES (
                    'user', :external_id, :title, :description, :starts_at, NULL,
                    NULL, :location_name, :location_url, :lat, :lng, :country, :city,
                    :organizer_id, :organizer_username, :max_participants, 0,
                    NULL, 'open', NOW(), NOW(), false, :chat_id
                )
                RETURNING id
            """)

            country = "ID" if city == "bali" else "RU"

            # Генерируем уникальный external_id для пользовательского события
            import random
            import time

            # Используем микросекунды + случайное число для уникальности
            timestamp_ms = int(time.time() * 1000000)  # микросекунды
            random_suffix = random.randint(1000, 9999)  # случайное число
            external_id = f"user_{organizer_id}_{timestamp_ms}_{random_suffix}"

            user_result = conn.execute(
                user_event_query,
                {
                    "external_id": external_id,
                    "organizer_id": organizer_id,
                    "organizer_username": organizer_username,
                    "title": title,
                    "description": description,
                    "starts_at": starts_at_utc,
                    "city": city,
                    "lat": lat,
                    "lng": lng,
                    "location_name": location_name,
                    "location_url": location_url,
                    "max_participants": max_participants,
                    "country": country,
                    "chat_id": chat_id,
                },
            )

            user_event_id = user_result.fetchone()[0]

            # Обновляем счетчик созданных событий
            conn.execute(
                text("""
                UPDATE users
                SET events_created_total = events_created_total + 1,
                    updated_at_utc = NOW()
                WHERE id = :organizer_id
            """),
                {"organizer_id": organizer_id},
            )

            print(f"✅ Создано пользовательское событие ID {user_event_id}: '{title}'")
            return user_event_id

    def save_parser_event(
        self,
        source: str,
        external_id: str,
        title: str,
        description: str,
        starts_at_utc: datetime,
        city: str,
        lat: float,
        lng: float,
        location_name: str = None,
        location_url: str = None,
        url: str = None,
    ) -> int:
        """
        Сохранение парсерного события в единую таблицу events
        """
        with self.engine.begin() as conn:
            # Проверяем дубликаты в единой таблице events
            existing = conn.execute(
                text("""
                SELECT id FROM events
                WHERE source = :source AND external_id = :external_id
            """),
                {"source": source, "external_id": external_id},
            ).fetchone()

            country = "ID" if city == "bali" else "RU"
            is_ai = source == "ai"

            if existing:
                # Обновляем существующее событие в events
                conn.execute(
                    text("""
                    UPDATE events
                    SET title = :title, description = :description, starts_at = :starts_at,
                        city = :city, lat = :lat, lng = :lng, location_name = :location_name,
                        location_url = :location_url, url = :url, country = :country,
                        updated_at_utc = NOW()
                    WHERE source = :source AND external_id = :external_id
                """),
                    {
                        "title": title,
                        "description": description,
                        "starts_at": starts_at_utc,
                        "city": city,
                        "lat": lat,
                        "lng": lng,
                        "location_name": location_name,
                        "location_url": location_url,
                        "url": url,
                        "country": country,
                        "source": source,
                        "external_id": external_id,
                    },
                )

                event_id = existing[0]
                print(f"🔄 Обновлено парсерное событие ID {event_id}: '{title}'")
            else:
                # Создаем новое событие в events
                result = conn.execute(
                    text("""
                    INSERT INTO events
                    (source, external_id, title, description, starts_at, city, lat, lng,
                     location_name, location_url, url, country, is_generated_by_ai, status, current_participants)
                    VALUES
                    (:source, :external_id, :title, :description, :starts_at, :city, :lat, :lng,
                     :location_name, :location_url, :url, :country, :is_ai, 'open', 0)
                    ON CONFLICT (source, external_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        starts_at = EXCLUDED.starts_at,
                        city = EXCLUDED.city,
                        lat = EXCLUDED.lat,
                        lng = EXCLUDED.lng,
                        location_name = EXCLUDED.location_name,
                        location_url = EXCLUDED.location_url,
                        url = EXCLUDED.url,
                        country = EXCLUDED.country
                    RETURNING id
                """),
                    {
                        "source": source,
                        "external_id": external_id,
                        "title": title,
                        "description": description,
                        "starts_at": starts_at_utc,
                        "city": city,
                        "lat": lat,
                        "lng": lng,
                        "location_name": location_name,
                        "location_url": location_url,
                        "url": url,
                        "country": country,
                        "is_ai": is_ai,
                    },
                )

                event_id = result.fetchone()[0]
                print(f"✅ Создано парсерное событие ID {event_id}: '{title}'")

        return event_id

    def cleanup_old_events(self, city: str) -> int:
        """Очистка старых событий из единой таблицы events"""
        with self.engine.begin() as conn:
            # Очищаем из основной таблицы events
            events_deleted = conn.execute(
                text("""
                DELETE FROM events
                WHERE city = :city
                AND starts_at < NOW() - INTERVAL '1 day'
            """),
                {"city": city},
            ).rowcount

            print(f"🧹 Очистка {city}: удалено {events_deleted} событий из единой таблицы events")

            return events_deleted
