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
        group_id: int,
        creator_id: int,
        creator_username: str,
        title: str,
        date: datetime,
        description: str,
        city: str,
        location_name: str = None,
        location_url: str = None,
    ) -> int:
        """
        Создание события в сообществе

        Args:
            group_id: ID группового чата
            creator_id: ID создателя события
            title: Название события
            date: Дата и время события
            description: Описание события
            city: Город события
            location_name: Название места

        Returns:
            ID созданного события
        """
        print(
            f"🔥 CommunityEventsService.create_community_event: "
            f"создаем событие в группе {group_id}, создатель {creator_id}"
        )
        with self.engine.connect() as conn:
            query = text("""
                INSERT INTO events_community
                (chat_id, organizer_id, organizer_username, title, starts_at,
                 description, city, location_name, location_url, status)
                VALUES
                (:chat_id, :organizer_id, :organizer_username, :title, :starts_at,
                 :description, :city, :location_name, :location_url, 'open')
                RETURNING id
            """)

            result = conn.execute(
                query,
                {
                    "chat_id": group_id,
                    "organizer_id": creator_id,
                    "organizer_username": creator_username,
                    "title": title,
                    "starts_at": date,
                    "description": description,
                    "city": city,
                    "location_name": location_name,
                    "location_url": location_url,
                },
            )

            event_id = result.fetchone()[0]
            conn.commit()

            print(f"✅ Создано событие сообщества ID {event_id}: '{title}' в группе {group_id}")
            return event_id

    def get_community_events(self, group_id: int, limit: int = 20, include_past: bool = False) -> list[dict]:
        """
        Получение событий сообщества

        Args:
            group_id: ID группового чата
            limit: Максимальное количество событий
            include_past: Включать ли прошедшие события

        Returns:
            Список событий сообщества
        """
        with self.engine.connect() as conn:
            if include_past:
                # Показываем все события
                query = text("""
                    SELECT id, organizer_id, organizer_username, title, starts_at,
                           description, city, location_name, location_url, created_at
                    FROM events_community
                    WHERE chat_id = :chat_id AND status = 'open'
                    ORDER BY starts_at ASC
                    LIMIT :limit
                """)
            else:
                # Показываем только будущие события
                query = text("""
                    SELECT id, organizer_id, organizer_username, title, starts_at,
                           description, city, location_name, location_url, created_at
                    FROM events_community
                    WHERE chat_id = :chat_id AND status = 'open' AND starts_at > NOW()
                    ORDER BY starts_at ASC
                    LIMIT :limit
                """)

            result = conn.execute(query, {"chat_id": group_id, "limit": limit})

            events = []
            for row in result:
                events.append(
                    {
                        "id": row[0],
                        "organizer_id": row[1],
                        "organizer_username": row[2],
                        "title": row[3],
                        "starts_at": row[4],
                        "description": row[5],
                        "city": row[6],
                        "location_name": row[7],
                        "location_url": row[8],
                        "created_at": row[9],
                    }
                )

            return events

    def delete_community_event(self, event_id: int, group_id: int) -> bool:
        """
        Удаление события сообщества

        Args:
            event_id: ID события
            group_id: ID группы (для проверки принадлежности)

        Returns:
            True если событие успешно удалено
        """
        with self.engine.connect() as conn:
            query = text("""
                DELETE FROM events_community
                WHERE id = :event_id AND chat_id = :chat_id
            """)

            result = conn.execute(query, {"event_id": event_id, "chat_id": group_id})
            conn.commit()

            return result.rowcount > 0

    def cleanup_expired_events(self, days_old: int = 1) -> int:
        """
        Очистка старых событий сообществ (удаление на следующий день)

        Args:
            days_old: Количество дней, после которых события считаются старыми (по умолчанию 1)

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

    def get_community_stats(self, group_id: int) -> dict:
        """
        Получение статистики по событиям сообщества

        Args:
            group_id: ID группового чата

        Returns:
            Словарь со статистикой
        """
        with self.engine.connect() as conn:
            # Общее количество событий
            total_query = text("""
                SELECT COUNT(*) FROM events_community
                WHERE chat_id = :chat_id
            """)
            total_result = conn.execute(total_query, {"chat_id": group_id})
            total_events = total_result.fetchone()[0]

            # Будущие события
            future_query = text("""
                SELECT COUNT(*) FROM events_community
                WHERE chat_id = :chat_id AND starts_at > NOW()
            """)
            future_result = conn.execute(future_query, {"chat_id": group_id})
            future_events = future_result.fetchone()[0]

            # События сегодня
            today_query = text("""
                SELECT COUNT(*) FROM events_community
                WHERE chat_id = :chat_id
                AND DATE(starts_at) = CURRENT_DATE
            """)
            today_result = conn.execute(today_query, {"chat_id": group_id})
            today_events = today_result.fetchone()[0]

            return {
                "total_events": total_events,
                "future_events": future_events,
                "today_events": today_events,
            }
