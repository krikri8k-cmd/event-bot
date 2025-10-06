"""
Простая логика работы с событиями
"""

from datetime import datetime

from sqlalchemy import text

from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc


class SimpleEventsService:
    """Простой сервис для работы с событиями"""

    def __init__(self, engine):
        self.engine = engine

    def search_events_today(
        self, city: str, user_lat: float | None = None, user_lng: float | None = None, radius_km: float = 15
    ) -> list[dict]:
        """
        Поиск сегодняшних событий в городе

        Args:
            city: Город ('bali', 'moscow', 'spb')
            user_lat, user_lng: Координаты пользователя (опционально)
            radius_km: Радиус поиска в км

        Returns:
            Список событий
        """
        # Получаем временные границы для города
        start_utc = get_today_start_utc(city)
        end_utc = get_tomorrow_start_utc(city)

        with self.engine.connect() as conn:
            if user_lat and user_lng:
                # Поиск с координатами и радиусом
                query = text("""
                    SELECT source_type, id, title, description, starts_at,
                           city, lat, lng, location_name, location_url,
                           organizer_id, max_participants, current_participants, status
                    FROM events
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
                # Поиск без координат (все события в городе)
                query = text("""
                    SELECT source_type, id, title, description, starts_at,
                           city, lat, lng, location_name, location_url,
                           organizer_id, max_participants, current_participants, status
                    FROM events
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
                        "organizer_id": row[10],
                        "max_participants": row[11],
                        "current_participants": row[12],
                        "status": row[13],
                    }
                )

            return events

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
                 location_name, location_url, max_participants, chat_id)
                VALUES
                (:organizer_id, :title, :description, :starts_at, :city, :lat, :lng,
                 :location_name, :location_url, :max_participants, :chat_id)
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
                    "chat_id": chat_id,
                },
            )

            event_id = result.fetchone()[0]
            conn.commit()

            return event_id

    def cleanup_old_events(self, city: str) -> int:
        """
        Очистка старых событий в городе

        Args:
            city: Город для очистки

        Returns:
            Количество удаленных событий
        """
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

    def get_events_stats(self, city: str) -> dict:
        """
        Получение статистики событий в городе

        Args:
            city: Город

        Returns:
            Словарь со статистикой
        """
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

            # По источникам
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
                "total_events": total_result[0],
                "parser_events": parser_result[0],
                "user_events": user_result[0],
                "date_range": f"{start_utc.isoformat()} - {end_utc.isoformat()}",
            }
