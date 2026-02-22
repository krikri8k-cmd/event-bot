#!/usr/bin/env python3
"""
Сервис для работы с событиями сообществ (групповых чатов)
"""

import logging
import threading
from datetime import datetime

from sqlalchemy import text

from config import load_settings
from utils.event_translation import translate_event_to_english

logger = logging.getLogger(__name__)


def _backfill_event_translation_sync(engine, event_id: int, title: str, description: str) -> None:
    """
    В фоне переводит title/description RU→EN и обновляет events_community.
    Если OpenAI не ответил — событие уже создано, поля _en остаются NULL.
    """
    try:
        trans = translate_event_to_english(title=title or "", description=description)
        if not trans or (not trans.get("title_en") and not trans.get("description_en")):
            return
        with engine.begin() as conn:
            conn.execute(
                text("""
                UPDATE events_community
                SET title_en = :title_en, description_en = :description_en
                WHERE id = :event_id
                """),
                {
                    "event_id": event_id,
                    "title_en": trans.get("title_en"),
                    "description_en": trans.get("description_en"),
                },
            )
        logger.info("✅ Фоновый перевод события %s (RU→EN) применён", event_id)
    except Exception as e:
        logger.warning("⚠️ Фоновый перевод события %s не удался: %s", event_id, e)


class CommunityEventsService:
    """Сервис для управления событиями в групповых чатах"""

    def __init__(self, engine=None):
        if engine is None:
            settings = load_settings()
            # Используем ту же функцию что и в database.py для нормализации URL
            from database import make_engine

            self.engine = make_engine(settings.database_url)
        else:
            self.engine = engine

        # Кэш для админов групп (chat_id -> (admin_ids, timestamp))
        # ОГРАНИЧЕНИЕ РАЗМЕРА для защиты от OOM
        self._admin_cache = {}
        self._cache_ttl = 600  # 10 минут
        self._max_cache_size = 200  # Максимум 200 групп в кэше

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
        title_en: str | None = None,
        description_en: str | None = None,
        creator_lang: str = "ru",
    ) -> int:
        """
        Создание события в сообществе.

        - RU (creator_lang="ru"): title/description = оригинал; title_en/description_en заполняются
          в фоне через OpenAI. Если OpenAI не ответил — событие уже создано, _en остаются NULL.
        - EN (creator_lang="en"): и основные поля, и _en заполняются английским текстом
          (fallback для русскоязычных при отображении).

        Returns:
            ID созданного события
        """
        import json

        admin_ids_json = json.dumps(admin_ids) if admin_ids else None
        admin_count = len(admin_ids) if admin_ids else 0

        run_background_translation = False
        # EN: заполняем и основные поля, и _en одним текстом (fallback для RU при отображении)
        if creator_lang == "en":
            title_en = (title or "").strip() or None
            description_en = (description or "").strip() or None
        else:
            # RU (или по умолчанию): _en заполняем в фоне через OpenAI; не блокируем создание
            if (title or "").strip():
                run_background_translation = True
                title_en = None
                description_en = None

        with self.engine.begin() as conn:
            # Создаем событие (с title_en, description_en)
            query = text("""
                INSERT INTO events_community
                (chat_id, organizer_id, organizer_username, admin_id, admin_ids, admin_count, title, title_en,
                 description, description_en, starts_at, city, location_name, location_url, status)
                VALUES
                (:chat_id, :organizer_id, :organizer_username, :admin_id, :admin_ids, :admin_count, :title, :title_en,
                 :description, :description_en, :starts_at, :city, :location_name, :location_url, 'open')
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
                "title_en": title_en,
                "description": description,
                "description_en": description_en,
                "starts_at": date,
                "city": city,
                "location_name": location_name,
                "location_url": location_url,
            }

            result = conn.execute(query, sql_params)
            event_id = result.fetchone()[0]

            # Обновляем счетчик созданных событий (Community версия) для пользователя
            conn.execute(
                text("""
                UPDATE users
                SET events_created_community = events_created_community + 1,
                    updated_at_utc = NOW()
                WHERE id = :creator_id
            """),
                {"creator_id": creator_id},
            )

            # Обновляем счетчик total_events в chat_settings
            conn.execute(
                text("""
                UPDATE chat_settings
                SET total_events = COALESCE(total_events, 0) + 1,
                    updated_at = NOW()
                WHERE chat_id = :group_id
            """),
                {"group_id": group_id},
            )

            logger.info("✅ Создано событие сообщества ID %s в группе %s", event_id, group_id)

        # Фоновый перевод RU→EN не блокирует создание: поток запускается после commit,
        # событие уже сохранено и event_id возвращается сразу.
        if run_background_translation:
            thread = threading.Thread(
                target=_backfill_event_translation_sync,
                args=(self.engine, event_id, title or "", description or ""),
                name=f"community-translate-{event_id}",
                daemon=True,
            )
            thread.start()
            logger.debug("Запущен фоновый перевод события %s (RU→EN)", event_id)

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
                    WHERE chat_id = :chat_id AND status = 'open' AND starts_at > NOW() - INTERVAL '3 hours'
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
            # Переносим запись в архив, затем удаляем из основной
            archive_query = text(
                """
                INSERT INTO events_community_archive (
                    id, chat_id, organizer_id, organizer_username,
                    admin_id, admin_ids, admin_count,
                    title, title_en, description, description_en, starts_at, city,
                    location_name, location_url, created_at,
                    status, archived_at_utc
                )
                SELECT id, chat_id, organizer_id, organizer_username,
                       admin_id, admin_ids, admin_count,
                       title, title_en, description, description_en, starts_at, city,
                       location_name, location_url, created_at,
                       status, NOW()
                FROM events_community
                WHERE id = :event_id AND chat_id = :chat_id
                ON CONFLICT (id) DO NOTHING
                """
            )
            conn.execute(archive_query, {"event_id": event_id, "chat_id": group_id})

            delete_query = text(
                """
                DELETE FROM events_community
                WHERE id = :event_id AND chat_id = :chat_id
                """
            )
            result = conn.execute(delete_query, {"event_id": event_id, "chat_id": group_id})
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
            # Сначала переносим старые записи в архив
            # Для открытых событий: по дате начала (starts_at)
            # Для закрытых событий: по времени закрытия (updated_at), чтобы можно было возобновить в течение 24 часов
            archive_query = text(
                """
                INSERT INTO events_community_archive (
                    id, chat_id, organizer_id, organizer_username,
                    admin_id, admin_ids, admin_count,
                    title, title_en, description, description_en, starts_at, city,
                    location_name, location_url, created_at,
                    status, archived_at_utc
                )
                SELECT id, chat_id, organizer_id, organizer_username,
                       admin_id, admin_ids, admin_count,
                       title, title_en, description, description_en, starts_at, city,
                       location_name, location_url, created_at,
                       status, NOW()
                FROM events_community
                WHERE (
                    -- Открытые события: архивируем по дате начала
                    (status = 'open' AND starts_at < NOW() - make_interval(days => :days_old))
                    OR
                    -- Закрытые события: архивируем только если закрыты более 24 часов назад
                    (status = 'closed' AND updated_at < NOW() - INTERVAL '24 hours')
                )
                ON CONFLICT (id) DO NOTHING
                """
            )
            conn.execute(archive_query, {"days_old": days_old})

            # Затем удаляем их из основной таблицы
            delete_query = text(
                """
                DELETE FROM events_community
                WHERE (
                    -- Открытые события: удаляем по дате начала
                    (status = 'open' AND starts_at < NOW() - make_interval(days => :days_old))
                    OR
                    -- Закрытые события: удаляем только если закрыты более 24 часов назад
                    (status = 'closed' AND updated_at < NOW() - INTERVAL '24 hours')
                )
                """
            )
            result = conn.execute(delete_query, {"days_old": days_old})
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
        ИСКЛЮЧАЕТ ID самого бота из списка админов

        Args:
            bot: Экземпляр бота для получения списка админов
            group_id: ID группового чата

        Returns:
            Список ID всех администраторов группы (без бота)
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            logger.info(f"🔄 Получаю админов для группы {group_id}")

            # Получаем ID бота для исключения из списка админов
            bot_info = await bot.get_me()
            bot_id = bot_info.id
            logger.info(f"🤖 bot_id = {bot_id}")

            # Получаем список администраторов
            administrators = await bot.get_chat_administrators(group_id)

            if not administrators:
                logger.warning(f"⚠️ Нет администраторов в группе {group_id}")
                return []

            # ИСКЛЮЧАЕМ БОТА НА ЭТАПЕ ВЫБОРКИ
            admin_ids = []
            for admin in administrators:
                if admin.status in ("creator", "administrator") and admin.user.id != bot_id:
                    admin_ids.append(admin.user.id)

            logger.info(f"✅ Получены админы группы {group_id} (без бота): {admin_ids}")
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

        # Очистка кэша при превышении размера
        if len(self._admin_cache) >= self._max_cache_size:
            # Удаляем устаревшие записи
            expired_keys = [key for key, (_, ts) in self._admin_cache.items() if (current_time - ts) >= self._cache_ttl]
            for key in expired_keys:
                self._admin_cache.pop(key, None)

            # Если все еще слишком много, удаляем 50% самых старых
            if len(self._admin_cache) >= self._max_cache_size:
                sorted_items = sorted(self._admin_cache.items(), key=lambda x: x[1][1])
                to_remove = len(self._admin_cache) - self._max_cache_size // 2
                for key, _ in sorted_items[:to_remove]:
                    self._admin_cache.pop(key, None)

        # Сохраняем в кэш
        self._admin_cache[group_id] = (admin_ids, current_time)
        logger.info("💾 Админы сохранены в кэш")

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
