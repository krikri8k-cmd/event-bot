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
        print("🚨🚨🚨 ПРОВЕРКА ДЕПЛОЯ: CREATE_COMMUNITY_EVENT ОБНОВЛЕН! 🚨🚨🚨")
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

        # НЕ ИСПОЛЬЗУЕМ FALLBACK: если admin_ids пустые, оставляем пустыми
        if not admin_ids:
            print("🔥🔥🔥 ВНИМАНИЕ: admin_ids пустые - SSL ошибки блокируют получение админов группы")
            print("🚨🚨🚨 ВНИМАНИЕ: В таблице будет пустой список админов!")
            print("🚨🚨🚨 Это означает, что get_group_admin_ids() не смог получить админов из-за SSL ошибок!")
            # НЕ подставляем создателя - оставляем пустой список
            admin_ids = []
            admin_id = None  # LEGACY тоже пустой

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
            print(f"🔥🔥🔥 ПЕРЕД COMMIT: organizer_id={creator_id}, admin_ids={admin_ids_json}")
            print(f"🔥🔥🔥 ПРОВЕРКА: admin_ids != organizer_id: {admin_ids != [creator_id]}")

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
        print("🚨🚨🚨 НОВАЯ ВЕРСИЯ GET_GROUP_ADMIN_IDS ЗАПУЩЕНА! 🚨🚨🚨")
        print("🚨🚨🚨 НОВАЯ ВЕРСИЯ GET_GROUP_ADMIN_IDS ЗАПУЩЕНА! 🚨🚨🚨")
        print(f"🔥🔥🔥 get_group_admin_ids: НАЧАЛО - запрос админов для группы {group_id}")
        print(f"🔥🔥🔥 get_group_admin_ids: bot={bot}, type={type(bot)}")
        print("🚨🚨🚨 ПРОВЕРКА ДЕПЛОЯ: КОД ОБНОВЛЕН! 🚨🚨🚨")
        logger.info(f"🔥 get_group_admin_ids: НАЧАЛО - запрос админов для группы {group_id}")

        # АГРЕССИВНАЯ RETRY логика для получения админов группы
        for attempt in range(10):  # 10 попыток для максимальной надежности
            try:
                logger.info(f"🔥 get_group_admin_ids: попытка {attempt + 1}/10 для группы {group_id}")

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
                    result = future.result(timeout=30)  # Увеличили timeout до 30 секунд
                    logger.info(f"🔥 get_group_admin_ids: получен результат {result} для группы {group_id}")
                    print(f"🎉🎉🎉 УСПЕХ: Получены настоящие админы группы: {result}")
                    print(f"🎉🎉🎉 Количество админов: {len(result)}")
                    return result

            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Попытка {attempt + 1}/3 - Ошибка получения админов группы {group_id}: {e}")

                # АГРЕССИВНАЯ SSL retry логика с разными стратегиями
                if "SSL" in error_msg or "APPLICATION_DATA_AFTER_CLOSE_NOTIFY" in error_msg:
                    if attempt < 9:  # Не последняя попытка (10 попыток)
                        # Разные стратегии ожидания для разных попыток
                        if attempt < 3:
                            wait_time = (attempt + 1) * 2  # 2, 4, 6 секунд
                        elif attempt < 6:
                            wait_time = (attempt + 1) * 3  # 12, 15, 18 секунд
                        else:
                            wait_time = (attempt + 1) * 4  # 28, 32, 36, 40 секунд

                        logger.info(f"⏳ SSL ошибка, ждем {wait_time} сек перед повтором для группы {group_id}")
                        print(f"🔥🔥🔥 SSL ошибка, попытка {attempt + 1}/10, ждем {wait_time} сек...")
                        time.sleep(wait_time)
                        continue

                # Если не SSL ошибка или последняя попытка
                if attempt == 9:  # Последняя попытка (10 попыток)
                    logger.error(f"💥 Все попытки исчерпаны для группы {group_id}")
                    break

        # АЛЬТЕРНАТИВНЫЙ МЕТОД: попробуем получить админов через прямой HTTP запрос с RETRY
        for http_attempt in range(5):  # 5 попыток HTTP запроса
            try:
                print(f"🔥🔥🔥 АЛЬТЕРНАТИВНЫЙ МЕТОД: попытка {http_attempt + 1}/5 HTTP запроса для группы {group_id}")
                import os
                import time

                import requests

                # Получаем токен бота из переменных окружения
                bot_token = os.getenv("BOT_TOKEN")
                if bot_token:
                    url = f"https://api.telegram.org/bot{bot_token}/getChatAdministrators"
                    params = {"chat_id": group_id}

                    # Увеличиваем timeout и добавляем retry для HTTP с обходом SSL
                    import urllib3

                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

                    # Пробуем разные стратегии подключения
                    session = requests.Session()
                    session.verify = False
                    session.headers.update(
                        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )

                    response = session.get(url, params=params, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("ok"):
                            admins = data.get("result", [])
                            admin_ids = [
                                admin["user"]["id"]
                                for admin in admins
                                if admin["status"] in ("creator", "administrator")
                            ]
                            print(f"🔥🔥🔥 АЛЬТЕРНАТИВНЫЙ МЕТОД УСПЕШЕН: получены админы {admin_ids}")
                            print(f"🎉🎉🎉 HTTP УСПЕХ: Получены настоящие админы группы через HTTP: {admin_ids}")
                            print(f"🎉🎉🎉 HTTP Количество админов: {len(admin_ids)}")
                            return admin_ids
                    else:
                        print(f"🔥🔥🔥 HTTP ОШИБКА: статус {response.status_code}, попытка {http_attempt + 1}/5")
                        if http_attempt < 4:  # Не последняя попытка
                            time.sleep(2)  # Ждем 2 секунды перед повтором
                            continue
            except Exception as e:
                print(f"🔥🔥🔥 АЛЬТЕРНАТИВНЫЙ МЕТОД НЕ УДАЛСЯ (попытка {http_attempt + 1}/5): {e}")
                if http_attempt < 4:  # Не последняя попытка
                    time.sleep(2)  # Ждем 2 секунды перед повтором
                    continue

        # ДИАГНОСТИКА SSL: проверяем окружение Railway
        try:
            print(f"🔥🔥🔥 ДИАГНОСТИКА SSL: проверяем окружение для группы {group_id}")
            import ssl

            import certifi

            print(f"🔥🔥🔥 OpenSSL версия: {ssl.OPENSSL_VERSION}")
            print(f"🔥🔥🔥 Certifi bundle: {certifi.where()}")

            # Проверяем базовое подключение к api.telegram.org
            import requests

            test_response = requests.get("https://api.telegram.org", timeout=10, verify=certifi.where())
            print(f"🔥🔥🔥 Тест подключения к api.telegram.org: статус {test_response.status_code}")

        except Exception as e:
            print(f"🔥🔥🔥 ДИАГНОСТИКА SSL НЕ УДАЛАСЬ: {e}")

        # ПОСЛЕДНИЙ ШАНС: попробуем через curl-подобный запрос
        try:
            print(f"🔥🔥🔥 ПОСЛЕДНИЙ ШАНС: curl-подобный запрос для группы {group_id}")
            import json
            import subprocess

            bot_token = os.getenv("BOT_TOKEN")
            if bot_token:
                # Используем curl через subprocess для обхода SSL проблем
                curl_cmd = [
                    "curl",
                    "-s",
                    "--insecure",
                    "--connect-timeout",
                    "30",
                    f"https://api.telegram.org/bot{bot_token}/getChatAdministrators",
                    "-d",
                    f"chat_id={group_id}",
                ]

                result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    if data.get("ok"):
                        admins = data.get("result", [])
                        admin_ids = [
                            admin["user"]["id"] for admin in admins if admin["status"] in ("creator", "administrator")
                        ]
                        print(f"🔥🔥🔥 CURL УСПЕХ: получены админы {admin_ids}")
                        print(f"🎉🎉🎉 CURL УСПЕХ: Получены настоящие админы группы через curl: {admin_ids}")
                        return admin_ids
                else:
                    print(f"🔥🔥🔥 CURL ОШИБКА: exit code {result.returncode}, stderr: {result.stderr}")
        except Exception as e:
            print(f"🔥🔥🔥 CURL МЕТОД НЕ УДАЛСЯ: {e}")

        # FALLBACK: если все попытки не удались, возвращаем пустой список
        logger.warning(f"💡 FALLBACK: Возвращаем пустой список для группы {group_id}")
        print(f"💥💥💥 FALLBACK: Возвращаем пустой список для группы {group_id}")
        print("🚨🚨🚨 ВНИМАНИЕ: SSL ошибки блокируют получение админов группы!")
        print("🚨🚨🚨 В результате в таблице будет только создатель события!")
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
