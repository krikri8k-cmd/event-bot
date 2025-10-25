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

        # Кэш для админов групп (chat_id -> (admin_ids, timestamp))
        self._admin_cache = {}
        self._cache_ttl = 600  # 10 минут

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
        admin_id: int = None,
        admin_ids: list[int] = None,
    ) -> int:
        """
        Создание события в сообществе

        Args:
            group_id: ID группового чата
            creator_id: ID создателя события
            creator_username: Username создателя
            title: Название события
            date: Дата и время события
            description: Описание события
            city: Город события
            location_name: Название места
            location_url: Ссылка на место
            admin_id: ID админа группы (LEGACY - для обратной совместимости)
            admin_ids: Список ID всех админов группы (новый подход)

        Returns:
            ID созданного события
        """
        print(f"🔥 Создание события в группе {group_id}, создатель {creator_id}")
        print(f"🔥 Получены admin_ids: {admin_ids}")
        print(f"🔥 Получен admin_id (LEGACY): {admin_id}")

        # Подготавливаем admin_ids как JSON и считаем admin_count
        import json

        admin_ids_json = json.dumps(admin_ids) if admin_ids else None
        admin_count = len(admin_ids) if admin_ids else 0

        print(f"🔥 admin_ids_json: {admin_ids_json}")
        print(f"🔥 admin_count = {admin_count}")

        with self.engine.connect() as conn:
            query = text("""
                INSERT INTO events_community
                (chat_id, organizer_id, organizer_username, admin_id, admin_ids, admin_count, title, starts_at,
                 description, city, location_name, location_url, status)
                VALUES
                (:chat_id, :organizer_id, :organizer_username, :admin_id, :admin_ids, :admin_count, :title, :starts_at,
                 :description, :city, :location_name, :location_url, 'open')
                RETURNING id
            """)

            sql_params = {
                "chat_id": group_id,
                "organizer_id": creator_id,
                "organizer_username": creator_username,
                "admin_id": admin_id,
                "admin_ids": admin_ids_json,
                "admin_count": admin_count,
                "title": title,
                "starts_at": date,
                "description": description,
                "city": city,
                "location_name": location_name,
                "location_url": location_url,
            }

            result = conn.execute(query, sql_params)
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
                query = text("""
                    SELECT id, organizer_id, organizer_username, title, starts_at,
                           description, city, location_name, location_url, created_at
                    FROM events_community
                    WHERE chat_id = :chat_id AND status = 'open'
                    ORDER BY starts_at ASC
                    LIMIT :limit
                """)
            else:
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

    async def get_group_admin_ids_async(self, bot, group_id: int) -> list[int]:
        """
        Получает ID всех администраторов группы - асинхронная версия
        Использует переданный объект bot напрямую

        Args:
            bot: Экземпляр бота для получения списка админов
            group_id: ID группового чата

        Returns:
            Список ID всех администраторов группы
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            logger.info(f"🔄 Получаю админов для группы {group_id}")

            # ПРЯМОЕ ИСПОЛЬЗОВАНИЕ BOT: используем переданный объект bot
            administrators = await bot.get_chat_administrators(group_id)

            if not administrators:
                logger.warning(f"⚠️ Нет администраторов в группе {group_id}")
                return []

            # Получаем ID бота для исключения из списка админов
            bot_info = await bot.get_me()
            bot_id = bot_info.id

            admin_ids = []
            for admin in administrators:
                if admin.status in ("creator", "administrator") and admin.user.id != bot_id:
                    admin_ids.append(admin.user.id)

            logger.info(f"✅ Получены админы группы {group_id}: {admin_ids}")
            return admin_ids

        except Exception as e:
            logger.error(f"❌ Ошибка получения админов группы {group_id}: {e}")
            return []

    async def get_cached_admin_ids(self, bot, group_id: int) -> list[int]:
        """
        Получает ID админов группы с кэшированием

        Args:
            bot: Экземпляр бота
            group_id: ID группового чата

        Returns:
            Список ID администраторов группы
        """
        import logging
        import time

        logger = logging.getLogger(__name__)
        current_time = time.time()

        # Проверяем кэш
        if group_id in self._admin_cache:
            admin_ids, timestamp = self._admin_cache[group_id]
            if current_time - timestamp < self._cache_ttl:
                logger.info(f"⚡ Использован кэш админов для группы {group_id}: {admin_ids}")
                return admin_ids
            else:
                # Кэш устарел, удаляем
                del self._admin_cache[group_id]

        # Получаем свежие данные
        admin_ids = await self.get_group_admin_ids_async(bot, group_id)

        # Сохраняем в кэш
        self._admin_cache[group_id] = (admin_ids, current_time)
        logger.info(f"💾 Админы группы {group_id} сохранены в кэш: {admin_ids}")

        return admin_ids

    async def get_group_admin_id_async(self, group_id: int, bot) -> int | None:
        """
        Получает ID первого администратора группы (создателя или админа) - асинхронная версия
        LEGACY метод для обратной совместимости

        Args:
            group_id: ID группового чата
            bot: Экземпляр бота для получения списка админов

        Returns:
            ID администратора или None если не найден
        """
        admin_ids = await self.get_group_admin_ids_async(group_id, bot)
        return admin_ids[0] if admin_ids else None
