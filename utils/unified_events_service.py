"""
УНИФИЦИРОВАННЫЙ сервис для работы с событиями через единую таблицу events
"""

import time
from datetime import datetime

from sqlalchemy import text

from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc
from utils.structured_logging import StructuredLogger


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

        with self.engine.connect() as conn:
            if user_lat and user_lng:
                # Поиск с координатами и радиусом
                query = text("""
                    SELECT source, id, title, description, starts_at,
                           city, lat, lng, location_name, location_url, url as event_url,
                           organizer_id, organizer_username, max_participants,
                           current_participants, status, created_at_utc
                    FROM events
                    WHERE city = :city
                    AND starts_at >= :start_utc
                    AND starts_at < :end_utc
                    AND lat IS NOT NULL AND lng IS NOT NULL
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
                        "city": city,
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
                           city, lat, lng, location_name, location_url, url as event_url,
                           organizer_id, organizer_username, max_participants,
                           current_participants, status, created_at_utc
                    FROM events
                    WHERE city = :city
                    AND starts_at >= :start_utc
                    AND starts_at < :end_utc
                    ORDER BY starts_at
                """)

                result = conn.execute(
                    query,
                    {
                        "city": city,
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

                events.append(
                    {
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
                )

            # Логируем результат поиска
            empty_reason = None
            if not events:
                if user_lat and user_lng:
                    empty_reason = "no_events_in_radius"
                else:
                    empty_reason = "no_events_today"

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
        organizer_username: str = None,
    ) -> int:
        """
        Создание пользовательского события (сначала в events_user, потом синхронизация)
        """
        with self.engine.begin() as conn:
            # 1. Создаем в events_user
            user_event_query = text("""
                INSERT INTO events_user
                (organizer_id, organizer_username, title, description, starts_at, city, lat, lng,
                 location_name, location_url, max_participants, country)
                VALUES
                (:organizer_id, :organizer_username, :title, :description, :starts_at, :city, :lat, :lng,
                 :location_name, :location_url, :max_participants, :country)
                RETURNING id
            """)

            country = "ID" if city == "bali" else "RU"

            user_result = conn.execute(
                user_event_query,
                {
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
                },
            )

            user_event_id = user_result.fetchone()[0]

            # 2. Синхронизируем в events
            sync_query = text("""
                INSERT INTO events (
                    source, external_id, title, description, starts_at, ends_at,
                    url, location_name, location_url, lat, lng, country, city,
                    organizer_id, organizer_username, max_participants, current_participants,
                    participants_ids, status, created_at_utc, updated_at_utc, is_generated_by_ai
                )
                SELECT
                    'user' as source,
                    id::text as external_id,
                    title, description, starts_at, NULL as ends_at,
                    NULL as url, location_name, location_url, lat, lng, country, city,
                    organizer_id, organizer_username, max_participants, 0 as current_participants,
                    NULL as participants_ids, 'open' as status, NOW(), NOW(), false as is_generated_by_ai
                FROM events_user
                WHERE id = :user_event_id
            """)

            conn.execute(sync_query, {"user_event_id": user_event_id})

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
        Сохранение парсерного события (сначала в events_parser, потом синхронизация)
        """
        with self.engine.begin() as conn:
            # 1. Сохраняем в events_parser
            # Проверяем дубликаты
            existing = conn.execute(
                text("""
                SELECT id FROM events_parser
                WHERE source = :source AND external_id = :external_id
            """),
                {"source": source, "external_id": external_id},
            ).fetchone()

            country = "ID" if city == "bali" else "RU"
            is_ai = source == "ai"

            if existing:
                # Обновляем существующее событие в events_parser
                conn.execute(
                    text("""
                    UPDATE events_parser
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
                # Создаем новое событие в events_parser
                result = conn.execute(
                    text("""
                    INSERT INTO events_parser
                    (source, external_id, title, description, starts_at, city, lat, lng,
                     location_name, location_url, url, country)
                    VALUES
                    (:source, :external_id, :title, :description, :starts_at, :city, :lat, :lng,
                     :location_name, :location_url, :url, :country)
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
                    },
                )

                event_id = result.fetchone()[0]
                print(f"✅ Создано парсерное событие ID {event_id}: '{title}'")

        # 2. Синхронизируем в events в отдельной транзакции
        try:
            with self.engine.begin() as sync_conn:
                sync_query = text("""
                    INSERT INTO events (
                        source, external_id, title, description, starts_at, ends_at,
                        url, location_name, location_url, lat, lng, country, city,
                        created_at_utc, updated_at_utc, is_generated_by_ai
                    )
                    SELECT
                        source, external_id, title, description, starts_at, NULL as ends_at,
                        url, location_name, location_url, lat, lng, country, city,
                        NOW(), NOW(), :is_ai
                    FROM events_parser
                    WHERE source = :source AND external_id = :external_id
                    ON CONFLICT (source, external_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        starts_at = EXCLUDED.starts_at,
                        ends_at = EXCLUDED.ends_at,
                        url = EXCLUDED.url,
                        location_name = EXCLUDED.location_name,
                        location_url = EXCLUDED.location_url,
                        lat = EXCLUDED.lat,
                        lng = EXCLUDED.lng,
                        country = EXCLUDED.country,
                        city = EXCLUDED.city,
                        updated_at_utc = NOW()
                """)

                sync_conn.execute(sync_query, {"source": source, "external_id": external_id, "is_ai": is_ai})

        except Exception as e:
            # Игнорируем ошибки дублирования - событие уже есть в основной таблице
            print(f"⚠️ Событие уже синхронизировано: {e}")

        return event_id

    def cleanup_old_events(self, city: str) -> int:
        """Очистка старых событий из всех таблиц"""
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

            # Очищаем из events_parser
            parser_deleted = conn.execute(
                text("""
                DELETE FROM events_parser
                WHERE city = :city
                AND starts_at < NOW() - INTERVAL '1 day'
            """),
                {"city": city},
            ).rowcount

            # Очищаем из events_user
            user_deleted = conn.execute(
                text("""
                DELETE FROM events_user
                WHERE city = :city
                AND starts_at < NOW() - INTERVAL '1 day'
            """),
                {"city": city},
            ).rowcount

            total_deleted = events_deleted + parser_deleted + user_deleted
            print(
                f"🧹 Очистка {city}: удалено {total_deleted} событий "
                f"(events: {events_deleted}, parser: {parser_deleted}, user: {user_deleted})"
            )

            return total_deleted
