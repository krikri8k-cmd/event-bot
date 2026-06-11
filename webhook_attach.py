#!/usr/bin/env python3
"""
Интеграция aiogram бота с FastAPI
Подключает webhook и health check к FastAPI приложению
"""

import asyncio
import logging
import os

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)

# Переменные окружения
# Приоритет: WEBHOOK_URL > PUBLIC_URL > RAILWAY_PUBLIC_DOMAIN (автоматически)
WEBHOOK_URL_ENV = os.getenv("WEBHOOK_URL")
PUBLIC_URL_ENV = os.getenv("PUBLIC_URL")
RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")  # Railway автоматически предоставляет
PORT = os.getenv("PORT", "8000")

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

# Определяем PUBLIC_URL
if WEBHOOK_URL_ENV:
    # Если WEBHOOK_URL уже полный URL с /webhook, используем его без пути
    if WEBHOOK_URL_ENV.endswith("/webhook"):
        PUBLIC_URL = WEBHOOK_URL_ENV[:-8]  # Убираем /webhook
    else:
        PUBLIC_URL = WEBHOOK_URL_ENV
elif PUBLIC_URL_ENV:
    PUBLIC_URL = PUBLIC_URL_ENV
elif RAILWAY_PUBLIC_DOMAIN:
    # Railway автоматически предоставляет публичный домен
    PUBLIC_URL = f"https://{RAILWAY_PUBLIC_DOMAIN}"
    logger.info(f"✅ Используется автоматический Railway домен: {PUBLIC_URL}")
else:
    PUBLIC_URL = None

# Логируем переменные окружения для отладки
logger.info(f"🔍 WEBHOOK_URL из окружения: {WEBHOOK_URL_ENV or 'НЕ УСТАНОВЛЕН'}")
logger.info(f"🔍 PUBLIC_URL из окружения: {PUBLIC_URL_ENV or 'НЕ УСТАНОВЛЕН'}")
logger.info(f"🔍 RAILWAY_PUBLIC_DOMAIN: {RAILWAY_PUBLIC_DOMAIN or 'НЕ УСТАНОВЛЕН'}")
logger.info(f"🔍 Используемый PUBLIC_URL: {PUBLIC_URL or 'НЕ УСТАНОВЛЕН'}")
logger.info(f"🔍 WEBHOOK_PATH: {WEBHOOK_PATH}")

if not PUBLIC_URL:
    logger.error("❌ PUBLIC_URL не установлен - webhook не будет работать!")
    logger.error("❌ Варианты решения:")
    logger.error("   1. Установите PUBLIC_URL=https://your-app.up.railway.app в Railway Variables")
    logger.error("   2. Установите WEBHOOK_URL=https://your-app.up.railway.app/webhook в Railway Variables")
    logger.error("   3. Включите публичный домен в Railway Settings → Networking")


def attach_bot_to_app(app: FastAPI) -> None:
    """
    Регистрирует /health, /webhook и инициализирует бота после старта FastAPI.
    Импорт bot_enhanced_v3 не выполняется здесь — только в lifespan и в webhook,
    чтобы сервер поднялся быстро и Railway health check прошёл.
    """
    # Флаг готовности (/health уже зарегистрирован в api.app до импорта webhook)
    if not hasattr(app.state, "ready"):
        app.state.ready = False

    @app.post(WEBHOOK_PATH)
    async def telegram_webhook(req: Request):
        """Обработчик webhook от Telegram"""
        from aiogram.types import Update

        from bot_enhanced_v3 import bot, dp

        try:
            # Получаем JSON данные от Telegram
            data = await req.json()
            logger.debug(f"📨 Получен webhook update: update_id={data.get('update_id')}")

            # Создаем Update объект
            update = Update(**data)

            # Передаем в dispatcher (не ждем завершения, чтобы быстро ответить Telegram)
            # Создаем задачу в фоне для обработки update
            asyncio.create_task(dp.feed_webhook_update(bot, update))

            # Возвращаем 200 сразу, чтобы Telegram не ждал
            return {"ok": True}
        except Exception as e:
            logger.error(f"❌ Ошибка обработки webhook: {e}")
            import traceback

            logger.error(f"❌ Детали ошибки: {traceback.format_exc()}")
            # Возвращаем 200 чтобы Telegram не повторял запрос
            return {"ok": False, "error": str(e)}

    async def init_bot():
        """
        Инициализация бота после старта FastAPI.
        Выполняет все длительные операции: БД, команды, роутеры и т.д.
        Импорт bot_enhanced_v3 здесь — сервер уже слушает, /health уже отвечает.
        """
        import bot_enhanced_v3
        from bot_enhanced_v3 import bot

        try:
            logger.info("🚀 Начало инициализации бота...")

            # Инициализируем BOT_ID для корректной фильтрации в групповых чатах
            bot_info = await bot.me()
            # Обновляем BOT_ID глобально
            bot_enhanced_v3.BOT_ID = bot_info.id
            logger.info(f"BOT_ID инициализирован: {bot_info.id}")

            # === НОВАЯ ИНТЕГРАЦИЯ ГРУППОВЫХ ЧАТОВ (ИЗОЛИРОВАННЫЙ РОУТЕР) ===
            # Устанавливаем username бота для deep-links в group_router
            try:
                from group_router import set_bot_username

                set_bot_username(bot_info.username)
                logger.info("✅ Групповой роутер успешно проинициализирован")
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации группового роутера: {e}")
                import traceback

                logger.error(f"❌ Детали ошибки: {traceback.format_exc()}")

            # Запускаем фоновую задачу для очистки моментов
            from config import load_settings
            from tasks_service import mark_tasks_as_expired

            load_settings()

            # Очищаем просроченные задания при старте
            try:
                expired_count = mark_tasks_as_expired()
                if expired_count > 0:
                    logger.info(f"При старте помечено как истекшие: {expired_count} заданий")
                else:
                    logger.info("При старте просроченных заданий не найдено")
            except Exception as e:
                logger.error(f"Ошибка очистки просроченных заданий при старте: {e}")

            # Устанавливаем команды бота
            try:
                await setup_bot_commands_and_menu(bot)
            except Exception as e:
                logger.warning(f"Не удалось установить команды бота: {e}")

            # Устанавливаем webhook
            if PUBLIC_URL:
                webhook_url = PUBLIC_URL.rstrip("/") + WEBHOOK_PATH
                logger.info(f"🔗 Устанавливаем webhook на URL: {webhook_url}")
                try:
                    # Сначала удаляем старый webhook (один раз при старте)
                    await bot.delete_webhook(drop_pending_updates=True)
                    logger.info("✅ Старый webhook удален")

                    # Устанавливаем новый webhook
                    result = await bot.set_webhook(url=webhook_url)
                    logger.info(f"✅ setWebhook вызван, результат: {result}")

                    # Проверяем что webhook установлен
                    webhook_info = await bot.get_webhook_info()
                    logger.info(f"📡 Webhook info: url={webhook_info.url}, pending={webhook_info.pending_update_count}")

                    if webhook_info.url != webhook_url:
                        logger.error(
                            f"❌ Webhook URL не совпадает! Ожидалось: {webhook_url}, получено: {webhook_info.url}"
                        )
                    else:
                        logger.info("✅ Webhook successfully set")
                        logger.info(f"✅ Webhook установлен успешно: {webhook_url}")
                except Exception as e:
                    logger.error(f"❌ Ошибка установки webhook: {e}")
                    import traceback

                    logger.error(f"❌ Детали ошибки: {traceback.format_exc()}")
            else:
                logger.error("❌ PUBLIC_URL не установлен - webhook не будет установлен!")
                logger.error("❌ Установите PUBLIC_URL в переменных окружения Railway")

            # Запускаем фоновую задачу для периодического обновления команд
            try:
                from bot_enhanced_v3 import periodic_commands_update

                asyncio.create_task(periodic_commands_update())
                logger.info("✅ Фоновая задача обновления команд запущена")
            except Exception as e:
                logger.warning(f"Не удалось запустить периодическое обновление команд: {e}")

            # Запускаем планировщик для автоматических задач (парсинг событий, напоминания)
            try:
                # Запускаем планировщик в отдельном потоке, чтобы не блокировать основной поток
                import threading

                from modern_scheduler import start_modern_scheduler

                def start_scheduler_thread():
                    try:
                        start_modern_scheduler()
                        logger.info("✅ Планировщик запущен в отдельном потоке")
                    except Exception as e:
                        logger.error(f"❌ Ошибка запуска планировщика: {e}")
                        import traceback

                        logger.error(traceback.format_exc())

                scheduler_thread = threading.Thread(target=start_scheduler_thread, daemon=True)
                scheduler_thread.start()
                logger.info("✅ Поток планировщика запущен")
            except Exception as e:
                logger.error(f"❌ Ошибка инициализации планировщика: {e}")
                import traceback

                logger.error(traceback.format_exc())

            # Помечаем как готов
            app.state.ready = True
            logger.info("✅ Бот инициализирован и готов к работе")

        except Exception as e:
            logger.error(f"❌ Критическая ошибка инициализации бота: {e}")
            import traceback

            logger.error(f"❌ Детали ошибки: {traceback.format_exc()}")
            # Не помечаем как ready если была ошибка
            app.state.ready = False

    async def setup_bot_commands_and_menu(bot):
        """Устанавливает команды бота и menu button (bot передаётся из init_bot)."""
        from aiogram import types
        from aiogram.types import (
            BotCommandScopeAllGroupChats,
            BotCommandScopeAllPrivateChats,
            BotCommandScopeChat,
            BotCommandScopeDefault,
            MenuButtonCommands,
        )

        # Импортируем функцию установки команд
        from bot_enhanced_v3 import dump_commands_healthcheck, ensure_commands, setup_bot_commands
        from group_router import setup_group_menu_button

        # АГРЕССИВНАЯ очистка всех команд для всех scope и языков
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
        await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats())

        await bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code="ru")
        await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats(), language_code="ru")
        await bot.delete_my_commands(scope=BotCommandScopeAllGroupChats(), language_code="ru")

        # Ждем чтобы Telegram обработал удаление
        await asyncio.sleep(2)

        # Админские команды
        admin_commands = [
            types.BotCommand(command="ban", description="🚫 Забанить пользователя (админ)"),
            types.BotCommand(command="unban", description="✅ Разбанить пользователя (админ)"),
            types.BotCommand(command="banlist", description="📋 Список забаненных (админ)"),
            types.BotCommand(command="admin_event", description="🔍 Диагностика события (админ)"),
            types.BotCommand(command="add_source", description="📡 Добавить Telegram-канал (ingest)"),
            types.BotCommand(command="list_sources", description="📋 Список ingest-источников"),
            types.BotCommand(command="ingest_stats", description="📊 Статистика ingest"),
            types.BotCommand(command="diag_last", description="📊 Диагностика последнего запроса"),
            types.BotCommand(command="diag_search", description="🔍 Диагностика поиска событий"),
            types.BotCommand(command="diag_webhook", description="🔗 Диагностика webhook"),
            types.BotCommand(command="diag_commands", description="🔧 Диагностика команд бота"),
        ]

        # Используем эталонную функцию установки команд
        await setup_bot_commands()

        # Устанавливаем админские команды для всех админов
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        if admin_ids_str:
            admin_ids = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
            for admin_id in admin_ids:
                await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
                logger.info(f"Админские команды установлены для админа {admin_id}")
        else:
            # Fallback на старый способ
            admin_user_id = int(os.getenv("ADMIN_USER_ID", "123456789"))
            if admin_user_id != 123456789:
                await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_user_id))
                logger.info(f"Админские команды установлены для админа {admin_user_id}")

        # Небольшая задержка для применения команд
        await asyncio.sleep(2)

        # ДИАГНОСТИКА: проверяем, что команды установлены
        try:
            current_commands = await bot.get_my_commands(scope=BotCommandScopeAllGroupChats())
            logger.info(f"🔍 Текущие команды для групп: {[cmd.command for cmd in current_commands]}")
        except Exception as e:
            logger.error(f"❌ Ошибка получения команд: {e}")

        # RUNTIME HEALTHCHECK: проверяем команды по всем скоупам и языкам
        try:
            await dump_commands_healthcheck(bot)
        except Exception as e:
            logger.error(f"❌ Ошибка healthcheck команд: {e}")

        # СТОРОЖ КОМАНД: проверяем и восстанавливаем команды при старте
        try:
            await ensure_commands(bot)
        except Exception as e:
            logger.error(f"❌ Ошибка сторожа команд при старте: {e}")

        # Устанавливаем кнопку меню
        try:
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("✅ Menu Button установлен успешно")
        except Exception as e:
            logger.warning(f"⚠️ Menu Button не удалось установить: {e}")

        # Еще одна задержка для применения Menu Button
        await asyncio.sleep(2)

        # Настраиваем Menu Button специально для групп
        await setup_group_menu_button(bot)

        logger.info("✅ Команды бота и Menu Button установлены")

    @app.on_event("startup")
    async def _startup():
        """Запускается один раз при старте FastAPI. Инициализирует бота и планировщик (не при каждом webhook)."""
        asyncio.create_task(init_bot())

    @app.on_event("shutdown")
    async def _shutdown():
        """Запускается при остановке FastAPI - закрывает соединения бота"""
        try:
            from bot_enhanced_v3 import bot

            logger.info("🛑 Остановка бота...")
            await bot.session.close()
            logger.info("✅ Бот остановлен")
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке бота: {e}")

    logger.info("✅ Webhook и health check подключены к FastAPI приложению")
