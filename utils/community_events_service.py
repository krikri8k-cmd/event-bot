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
        admin_id: int = None,
        admin_ids: list[int] = None,
    ) -> int:
        print("🚨🚨🚨 НОВАЯ ВЕРСИЯ КОДА ЗАПУЩЕНА! 🚨🚨🚨")
        print("🚨🚨🚨 НОВАЯ ВЕРСИЯ КОДА ЗАПУЩЕНА! 🚨🚨🚨")
        print("🚨🚨🚨 НОВАЯ ВЕРСИЯ КОДА ЗАПУЩЕНА! 🚨🚨🚨")
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
        print(
            f"🔥 CommunityEventsService.create_community_event: "
            f"создаем событие в группе {group_id}, создатель {creator_id}"
        )
        print(f"🔥 Получены admin_ids: {admin_ids}")
        print(f"🔥 Получен admin_id (LEGACY): {admin_id}")

        # КРИТИЧЕСКИЙ FALLBACK: если admin_ids пустые, используем создателя
        if not admin_ids:
            admin_ids = [creator_id]
            admin_id = creator_id  # Также исправляем LEGACY admin_id
            print(f"🔥🔥🔥 КРИТИЧЕСКИЙ FALLBACK: admin_ids пустые, используем создателя {creator_id}")

        # Подготавливаем admin_ids как JSON
        import json

        admin_ids_json = json.dumps(admin_ids) if admin_ids else None
        print(f"🔥 admin_ids_json для сохранения: {admin_ids_json}")
        print("🔥🔥🔥 create_community_event: ВХОДЯЩИЕ ПАРАМЕТРЫ")
        print(f"🔥🔥🔥 create_community_event: group_id={group_id}, admin_ids={admin_ids}")
        print(f"🔥🔥🔥 create_community_event: admin_ids_json={admin_ids_json}")
        print(f"🔥🔥🔥 ТИПЫ ДАННЫХ: admin_ids={type(admin_ids)}, admin_ids_json={type(admin_ids_json)}")
        print(f"🔥🔥🔥 ДЛИНА JSON: {len(admin_ids_json) if admin_ids_json else 'None'}")

        with self.engine.connect() as conn:
            query = text("""
                INSERT INTO events_community
                (chat_id, organizer_id, organizer_username, admin_id, admin_ids, title, starts_at,
                 description, city, location_name, location_url, status)
                VALUES
                (:chat_id, :organizer_id, :organizer_username, :admin_id, :admin_ids, :title, :starts_at,
                 :description, :city, :location_name, :location_url, 'open')
                RETURNING id
            """)

            # Логируем параметры SQL запроса
            sql_params = {
                "chat_id": group_id,
                "organizer_id": creator_id,
                "organizer_username": creator_username,
                "admin_id": admin_id,
                "admin_ids": admin_ids_json,
                "title": title,
                "starts_at": date,
                "description": description,
                "city": city,
                "location_name": location_name,
                "location_url": location_url,
            }
            print(f"🔥🔥🔥 SQL ПАРАМЕТРЫ: {sql_params}")
            print(f"🔥🔥🔥 admin_ids в SQL: {sql_params['admin_ids']}")

            result = conn.execute(query, sql_params)

            event_id = result.fetchone()[0]
            conn.commit()

            print(f"✅ Создано событие сообщества ID {event_id}: '{title}' в группе {group_id}")
            print(f"🔥🔥🔥 create_community_event: chat_id={group_id}, admin_ids={admin_ids_json}")

            # ПРОВЕРЯЕМ, что сохранилось в базе
            check_query = text("SELECT admin_ids FROM events_community WHERE id = :event_id")
            check_result = conn.execute(check_query, {"event_id": event_id})
            saved_admin_ids = check_result.fetchone()[0]
            print(f"🔥🔥🔥 ПРОВЕРКА: admin_ids в базе: {saved_admin_ids}")

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

    async def get_group_admin_ids_async(self, group_id: int, bot) -> list[int]:
        """
        Получает ID всех администраторов группы - асинхронная версия
        БЕЗ retry логики (retry делается на уровне синхронной функции)

        Args:
            group_id: ID группового чата
            bot: Экземпляр бота для получения списка админов

        Returns:
            Список ID всех администраторов группы
        """
        import logging

        logger = logging.getLogger(__name__)

        # КРИТИЧЕСКАЯ ОТЛАДКА: print для гарантированного вывода
        print(f"🔄🔄🔄 get_group_admin_ids_async: Получение админов группы {group_id}")

        try:
            logger.info(f"🔄 get_group_admin_ids_async: Получение админов группы {group_id}")

            # Получаем список администраторов
            logger.info(f"🔄 get_group_admin_ids_async: Вызов bot.get_chat_administrators({group_id})")
            administrators = await bot.get_chat_administrators(group_id)
            logger.info(f"🔄 get_group_admin_ids_async: Получен ответ от Telegram API для группы {group_id}")

            if not administrators:
                logger.warning(f"⚠️ get_group_admin_ids_async: Нет администраторов в группе {group_id}")
                return []

            admin_ids = []
            for admin in administrators:
                if admin.status in ("creator", "administrator"):
                    admin_ids.append(admin.user.id)

            logger.info(f"✅ get_group_admin_ids_async: Получены админы группы {group_id}: {admin_ids}")
            return admin_ids

        except Exception as e:
            logger.error(f"❌ get_group_admin_ids_async: Ошибка получения админов группы {group_id}: {e}")
            # Пробрасываем ошибку наверх для retry логики в синхронной функции
            raise

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

    def get_group_admin_ids(self, group_id: int, bot) -> list[int]:
        """
        Получает ID всех администраторов группы - синхронная версия
        ОБХОДНОЙ ПУТЬ: используем новый event loop в отдельном потоке
        С RETRY логикой и fallback механизмом

        Args:
            group_id: ID группового чата
            bot: Экземпляр бота для получения списка админов

        Returns:
            Список ID всех администраторов группы
        """
        import asyncio
        import concurrent.futures
        import logging
        import time

        logger = logging.getLogger(__name__)

        # КРИТИЧЕСКАЯ ОТЛАДКА: print для гарантированного вывода
        print("🚨🚨🚨 НОВАЯ ВЕРСИЯ GET_GROUP_ADMIN_IDS ЗАПУЩЕНА! 🚨🚨🚨")
        print(f"🔥🔥🔥 get_group_admin_ids: НАЧАЛО - запрос админов для группы {group_id}")
        print(f"🔥🔥🔥 get_group_admin_ids: bot={bot}, type={type(bot)}")
        logger.info(f"🔥 get_group_admin_ids: НАЧАЛО - запрос админов для группы {group_id}")

        # RETRY логика на уровне синхронной функции
        for attempt in range(5):  # 5 попыток для большей надежности
            try:
                logger.info(f"🔥 get_group_admin_ids: попытка {attempt + 1}/5 для группы {group_id}")

                # ОБХОДНОЙ ПУТЬ: запускаем в отдельном потоке с новым event loop
                def run_in_thread():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(self.get_group_admin_ids_async(group_id, bot))
                    finally:
                        loop.close()

                logger.info(f"🔥 get_group_admin_ids: запуск ThreadPoolExecutor для группы {group_id}")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    result = future.result(timeout=15)  # Увеличили timeout
                    logger.info(f"🔥 get_group_admin_ids: получен результат {result} для группы {group_id}")
                    return result

            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Попытка {attempt + 1}/3 - Ошибка получения админов группы {group_id}: {e}")

                # Если это SSL ошибка, ждем перед повтором
                if "SSL" in error_msg or "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" in error_msg:
                    if attempt < 4:  # Не последняя попытка (5 попыток)
                        wait_time = (attempt + 1) * 2  # 2, 4, 6, 8 секунд
                        logger.info(f"⏳ SSL ошибка, ждем {wait_time} сек перед повтором для группы {group_id}")
                        print(f"🔥🔥🔥 SSL ошибка, попытка {attempt + 1}/5, ждем {wait_time} сек...")
                        time.sleep(wait_time)
                        continue

                # Если не SSL ошибка или последняя попытка
                if attempt == 4:  # Последняя попытка (5 попыток)
                    logger.error(f"💥 Все попытки исчерпаны для группы {group_id}")
                    break

        # FALLBACK: если все попытки не удались, возвращаем пустой список
        logger.warning(f"💡 FALLBACK: Возвращаем пустой список для группы {group_id}")
        print(f"💥💥💥 FALLBACK: Возвращаем пустой список для группы {group_id}")
        return []

    def get_group_admin_id(self, group_id: int, bot) -> int | None:
        """
        Получает ID первого администратора группы (создателя или админа) - синхронная версия
        LEGACY метод для обратной совместимости

        Args:
            group_id: ID группового чата
            bot: Экземпляр бота для получения списка админов

        Returns:
            ID администратора или None если не найден
        """
        admin_ids = self.get_group_admin_ids(group_id, bot)
        return admin_ids[0] if admin_ids else None
