"""
УЛЬТРА ПРОСТАЯ логика работы с событиями БЕЗ VIEW
"""

from datetime import datetime

from sqlalchemy import text

from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc


class UltraSimpleEventsService:
    """Ультра простой сервис БЕЗ VIEW - только прямые запросы"""

    def __init__(self, engine):
        self.engine = engine

    def search_events_today(
        self, city: str, user_lat: float | None = None, user_lng: float | None = None, radius_km: float = 15
    ) -> list[dict]:
        """
        Поиск сегодняшних событий БЕЗ VIEW - прямые запросы к таблицам
        """
        # Получаем временные границы для города
        start_utc = get_today_start_utc(city)
        end_utc = get_tomorrow_start_utc(city)

        with self.engine.connect() as conn:
            # Прямой UNION ALL запрос БЕЗ VIEW
            if user_lat and user_lng:
                # Поиск с координатами и радиусом
                query = text("""
                    SELECT 'parser' as source_type, id, title, description, starts_at,
                           city, lat, lng, location_name, location_url, url as event_url,
                           NULL as organizer_id, NULL as max_participants,
                           NULL as current_participants, 'open' as status, created_at_utc
                    FROM events_parser
                    WHERE city = :city
                    AND starts_at >= :start_utc
                    AND starts_at < :end_utc
                    AND (lat IS NULL OR lng IS NULL OR
                        6371 * acos(
                            GREATEST(-1, LEAST(1,
                                cos(radians(:user_lat)) * cos(radians(lat)) *
                                cos(radians(lng) - radians(:user_lng)) +
                                sin(radians(:user_lat)) * sin(radians(lat))
                            ))
                        ) <= :radius_km)

                    UNION ALL

                    SELECT 'user' as source_type, id, title, description, starts_at,
                           city, lat, lng, location_name, location_url, NULL as event_url,
                           organizer_id, max_participants, current_participants, status, created_at_utc
                    FROM events_user
                    WHERE city = :city
                    AND starts_at >= :start_utc
                    AND starts_at < :end_utc
                    AND (lat IS NULL OR lng IS NULL OR
                        6371 * acos(
                            GREATEST(-1, LEAST(1,
                                cos(radians(:user_lat)) * cos(radians(lat)) *
                                cos(radians(lng) - radians(:user_lng)) +
                                sin(radians(:user_lat)) * sin(radians(lat))
                            ))
                        ) <= :radius_km)

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
                    SELECT 'parser' as source_type, id, title, description, starts_at,
                           city, lat, lng, location_name, location_url, url as event_url,
                           NULL as organizer_id, NULL as max_participants,
                           NULL as current_participants, 'open' as status, created_at_utc
                    FROM events_parser
                    WHERE city = :city
                    AND starts_at >= :start_utc
                    AND starts_at < :end_utc

                    UNION ALL

                    SELECT 'user' as source_type, id, title, description, starts_at,
                           city, lat, lng, location_name, location_url, NULL as event_url,
                           organizer_id, max_participants, current_participants, status, created_at_utc
                    FROM events_user
                    WHERE city = :city
                    AND starts_at >= :start_utc
                    AND starts_at < :end_utc

                    ORDER BY starts_at
                """)

                result = conn.execute(query, {"city": city, "start_utc": start_utc, "end_utc": end_utc})

            events = []
            for row in result:
                events.append(
                    {
                        "source_type": row[0],
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
                        "max_participants": row[12],
                        "current_participants": row[13],
                        "status": row[14],
                        "created_at_utc": row[15],
                    }
                )

            return events

    def get_events_stats(self, city: str) -> dict:
        """Статистика событий БЕЗ VIEW"""
        start_utc = get_today_start_utc(city)
        end_utc = get_tomorrow_start_utc(city)

        with self.engine.connect() as conn:
            # Прямые запросы к таблицам
            parser_result = conn.execute(
                text("""
                SELECT COUNT(*) FROM events_parser
                WHERE city = :city
                AND starts_at >= :start_utc
                AND starts_at < :end_utc
            """),
                {"city": city, "start_utc": start_utc, "end_utc": end_utc},
            ).fetchone()

            user_result = conn.execute(
                text("""
                SELECT COUNT(*) FROM events_user
                WHERE city = :city
                AND starts_at >= :start_utc
                AND starts_at < :end_utc
            """),
                {"city": city, "start_utc": start_utc, "end_utc": end_utc},
            ).fetchone()

            return {
                "city": city,
                "parser_events": parser_result[0],
                "user_events": user_result[0],
                "total_events": parser_result[0] + user_result[0],
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
    ) -> int:
        """
        Создание пользовательского события

        Args:
            organizer_id: ID пользователя
            title: Название события
            description: Описание
            starts_at_utc: Время начала в UTC
            city: Город
            lat, lng: Координаты
            location_name: Название места
            location_url: Ссылка на место
            max_participants: Максимум участников

        Returns:
            ID созданного события
        """
        with self.engine.connect() as conn:
            query = text("""
                INSERT INTO events_user
                (organizer_id, title, description, starts_at, city, lat, lng,
                 location_name, location_url, max_participants)
                VALUES
                (:organizer_id, :title, :description, :starts_at, :city, :lat, :lng,
                 :location_name, :location_url, :max_participants)
                RETURNING id
            """)

            result = conn.execute(
                query,
                {
                    "organizer_id": organizer_id,
                    "title": title,
                    "description": description,
                    "starts_at": starts_at_utc,
                    "city": city,
                    "lat": lat,
                    "lng": lng,
                    "location_name": location_name,
                    "location_url": location_url,
                    "max_participants": max_participants,
                },
            )

            event_id = result.fetchone()[0]
            conn.commit()

            return event_id

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
        Сохранение парсерного события в БД

        Args:
            source: Источник (baliforum, kudago, ai)
            external_id: Уникальный ID из источника
            title: Название события
            description: Описание
            starts_at_utc: Время начала в UTC
            city: Город
            lat, lng: Координаты
            location_name: Название места
            location_url: Ссылка на место
            url: Ссылка на событие

        Returns:
            ID созданного события
        """
        with self.engine.connect() as conn:
            # Проверяем дубликаты по source + external_id
            existing = conn.execute(
                text("""
                SELECT id FROM events_parser
                WHERE source = :source AND external_id = :external_id
            """),
                {"source": source, "external_id": external_id},
            ).fetchone()

            if existing:
                # Обновляем существующее событие
                conn.execute(
                    text("""
                    UPDATE events_parser
                    SET title = :title, description = :description, starts_at = :starts_at,
                        city = :city, lat = :lat, lng = :lng, location_name = :location_name,
                        location_url = :location_url, url = :url, updated_at_utc = NOW()
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
                        "source": source,
                        "external_id": external_id,
                    },
                )

                event_id = existing[0]
                print(f"🔄 Обновлено парсерное событие ID {event_id}: '{title}'")
            else:
                # Создаем новое событие
                result = conn.execute(
                    text("""
                    INSERT INTO events_parser
                    (source, external_id, title, description, starts_at, city, lat, lng,
                     location_name, location_url, url)
                    VALUES
                    (:source, :external_id, :title, :description, :starts_at, :city, :lat, :lng,
                     :location_name, :location_url, :url)
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
                    },
                )

                event_id = result.fetchone()[0]
                print(f"✅ Создано парсерное событие ID {event_id}: '{title}'")

            conn.commit()
            return event_id

    def cleanup_old_events(self, city: str) -> int:
        """Очистка старых событий"""
        with self.engine.connect() as conn:
            # Очищаем парсерные события
            parser_deleted = conn.execute(
                text("""
                DELETE FROM events_parser
                WHERE city = :city
                AND starts_at < NOW() - INTERVAL '1 day'
            """),
                {"city": city},
            ).rowcount

            # Очищаем пользовательские события
            user_deleted = conn.execute(
                text("""
                DELETE FROM events_user
                WHERE city = :city
                AND starts_at < NOW() - INTERVAL '1 day'
            """),
                {"city": city},
            ).rowcount

            conn.commit()

            total_deleted = parser_deleted + user_deleted
            print(
                f"🧹 Очистка {city}: удалено {total_deleted} событий "
                f"({parser_deleted} парсерных, {user_deleted} пользовательских)"
            )

            return total_deleted
