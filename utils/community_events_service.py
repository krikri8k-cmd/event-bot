#!/usr/bin/env python3
"""
Сервис для работы с событиями сообществ (групповых чатов)
"""

from datetime import datetime

from sqlalchemy import create_engine, text

from config import load_settings


class CommunityEventsService:
    """Сервис для управления событиями в групповых чатах"""

    def __init__(self, engine=None):
        if engine is None:
            settings = load_settings()
            self.engine = create_engine(settings.database_url)
        else:
            self.engine = engine

    def create_community_event(
        self,
        chat_id: int,
        organizer_id: int,
        organizer_username: str,
        title: str,
        description: str,
        starts_at: datetime,
        city: str,
        location_name: str = None,
        location_url: str = None,
    ) -> int:
        """
        Создание события в сообществе

        Args:
            chat_id: ID группового чата
            organizer_id: ID создателя события
            organizer_username: Username создателя
            title: Название события
            description: Описание события
            starts_at: Время начала события
            city: Город события
            location_name: Название места
            location_url: Ссылка на место

        Returns:
            ID созданного события
        """
        with self.engine.connect() as conn:
            query = text("""
                INSERT INTO events_community
                (chat_id, organizer_id, organizer_username, title, description,
                 starts_at, city, location_name, location_url, status)
                VALUES
                (:chat_id, :organizer_id, :organizer_username, :title, :description,
                 :starts_at, :city, :location_name, :location_url, 'open')
                RETURNING id
            """)

            result = conn.execute(
                query,
                {
                    "chat_id": chat_id,
                    "organizer_id": organizer_id,
                    "organizer_username": organizer_username,
                    "title": title,
                    "description": description,
                    "starts_at": starts_at,
                    "city": city,
                    "location_name": location_name,
                    "location_url": location_url,
                },
            )

            event_id = result.fetchone()[0]
            conn.commit()

            print(f"✅ Создано событие сообщества ID {event_id}: '{title}' в чате {chat_id}")
            return event_id

    def get_community_events(self, chat_id: int, limit: int = 20, include_past: bool = False) -> list[dict]:
        """
        Получение событий сообщества

        Args:
            chat_id: ID группового чата
            limit: Максимальное количество событий
            include_past: Включать ли прошедшие события

        Returns:
            Список событий сообщества
        """
        with self.engine.connect() as conn:
            if include_past:
                # Показываем все события
                query = text("""
                    SELECT id, organizer_id, organizer_username, title, description,
                           starts_at, city, location_name, location_url, status,
                           created_at
                    FROM events_community
                    WHERE chat_id = :chat_id AND status = 'open'
                    ORDER BY starts_at ASC
                    LIMIT :limit
                """)
            else:
                # Показываем только будущие события
                query = text("""
                    SELECT id, organizer_id, organizer_username, title, description,
                           starts_at, city, location_name, location_url, status,
                           created_at
                    FROM events_community
                    WHERE chat_id = :chat_id AND status = 'open' AND starts_at > NOW()
                    ORDER BY starts_at ASC
                    LIMIT :limit
                """)

            result = conn.execute(query, {"chat_id": chat_id, "limit": limit})

            events = []
            for row in result:
                events.append(
                    {
                        "id": row[0],
                        "organizer_id": row[1],
                        "organizer_username": row[2],
                        "title": row[3],
                        "description": row[4],
                        "starts_at": row[5],
                        "city": row[6],
                        "location_name": row[7],
                        "location_url": row[8],
                        "status": row[9],
                        "created_at": row[10],
                    }
                )

            return events

    def close_community_event(self, event_id: int, chat_id: int) -> bool:
        """
        Закрытие события сообщества

        Args:
            event_id: ID события
            chat_id: ID чата (для проверки принадлежности)

        Returns:
            True если событие успешно закрыто
        """
        with self.engine.connect() as conn:
            query = text("""
                UPDATE events_community
                SET status = 'closed', updated_at = NOW()
                WHERE id = :event_id AND chat_id = :chat_id AND status = 'open'
            """)

            result = conn.execute(query, {"event_id": event_id, "chat_id": chat_id})
            conn.commit()

            return result.rowcount > 0

    def cleanup_expired_events(self, days_old: int = 7) -> int:
        """
        Очистка старых событий сообществ

        Args:
            days_old: Количество дней, после которых события считаются старыми

        Returns:
            Количество удаленных событий
        """
        with self.engine.connect() as conn:
            query = text("""
                DELETE FROM events_community
                WHERE starts_at < NOW() - INTERVAL ':days_old days'
            """)

            result = conn.execute(query, {"days_old": days_old})
            conn.commit()

            deleted_count = result.rowcount
            if deleted_count > 0:
                print(f"🧹 Удалено {deleted_count} старых событий сообществ")

            return deleted_count

    def get_community_stats(self, chat_id: int) -> dict:
        """
        Получение статистики по событиям сообщества

        Args:
            chat_id: ID группового чата

        Returns:
            Словарь со статистикой
        """
        with self.engine.connect() as conn:
            # Общее количество событий
            total_query = text("""
                SELECT COUNT(*) FROM events_community
                WHERE chat_id = :chat_id
            """)
            total_result = conn.execute(total_query, {"chat_id": chat_id})
            total_events = total_result.fetchone()[0]

            # Активные события
            active_query = text("""
                SELECT COUNT(*) FROM events_community
                WHERE chat_id = :chat_id AND status = 'open' AND starts_at > NOW()
            """)
            active_result = conn.execute(active_query, {"chat_id": chat_id})
            active_events = active_result.fetchone()[0]

            # События сегодня
            today_query = text("""
                SELECT COUNT(*) FROM events_community
                WHERE chat_id = :chat_id AND status = 'open'
                AND DATE(starts_at) = CURRENT_DATE
            """)
            today_result = conn.execute(today_query, {"chat_id": chat_id})
            today_events = today_result.fetchone()[0]

            return {
                "total_events": total_events,
                "active_events": active_events,
                "today_events": today_events,
            }
