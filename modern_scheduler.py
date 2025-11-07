#!/usr/bin/env python3
"""
Современный планировщик для автоматического пополнения событий
Использует новую архитектуру с UnifiedEventsService
"""

import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler

from config import load_settings
from database import get_engine, init_engine
from sources.baliforum import fetch as fetch_baliforum
from utils.unified_events_service import UnifiedEventsService

logger = logging.getLogger(__name__)


class ModernEventScheduler:
    """Современный планировщик событий"""

    def __init__(self):
        self.settings = load_settings()
        init_engine(self.settings.database_url)
        self.engine = get_engine()
        self.service = UnifiedEventsService(self.engine)
        self.scheduler = None

    def ingest_baliforum(self):
        """Парсинг событий с BaliForum через правильную архитектуру"""
        if not self.settings.enable_baliforum:
            logger.info("🌴 BaliForum отключен в настройках")
            return

        try:
            logger.info("🌴 Запуск парсинга BaliForum...")
            start_time = time.time()

            # Получаем события на сегодня и завтра
            # Сначала парсим главную страницу (события на сегодня)
            raw_events = fetch_baliforum(limit=50)

            # Затем парсим страницу с фильтром по завтрашней дате
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo

            tz_bali = ZoneInfo("Asia/Makassar")
            tomorrow_bali = (datetime.now(tz_bali) + timedelta(days=1)).date()
            tomorrow_str = tomorrow_bali.strftime("%Y-%m-%d")

            logger.info(f"🌴 Парсим события на завтра ({tomorrow_str})...")
            from sources.baliforum import fetch_baliforum_events

            tomorrow_events = fetch_baliforum_events(limit=50, date_filter=tomorrow_str)
            # Конвертируем в RawEvent формат
            from event_apis import RawEvent

            for event in tomorrow_events:
                external_id = event.get("external_id", event["url"].rstrip("/").split("/")[-1])
                raw_event = RawEvent(
                    title=event["title"],
                    lat=event.get("lat") or 0.0,
                    lng=event.get("lng") or 0.0,
                    starts_at=event.get("start_time"),
                    source="baliforum",
                    external_id=external_id,
                    url=event["url"],
                    description=event.get("description"),
                )
                raw_events.append(raw_event)

            logger.info(f"🌴 Всего найдено событий: {len(raw_events)} (сегодня + завтра)")

            saved_count = 0
            skipped_no_coords = 0
            error_count = 0

            for event in raw_events:
                try:
                    # Проверяем координаты (как в оригинальном парсере)
                    if not event.lat or not event.lng:
                        skipped_no_coords += 1
                        continue

                    # Логируем дату события для отладки
                    if event.starts_at:
                        from datetime import datetime, timedelta
                        from zoneinfo import ZoneInfo

                        now_bali = datetime.now(ZoneInfo("Asia/Makassar"))
                        event_date_bali = event.starts_at.astimezone(ZoneInfo("Asia/Makassar")).date()
                        today_bali = now_bali.date()
                        tomorrow_bali = today_bali + timedelta(days=1)

                        date_label = (
                            "сегодня"
                            if event_date_bali == today_bali
                            else "завтра"
                            if event_date_bali == tomorrow_bali
                            else f"{event_date_bali}"
                        )
                        logger.info(f"   📅 BaliForum событие: '{event.title}' - {date_label} ({event.starts_at})")

                    # ПРАВИЛЬНАЯ АРХИТЕКТУРА: Сохраняем через UnifiedEventsService
                    # Сначала в events_parser, потом автоматически синхронизируется в events
                    event_id = self.service.save_parser_event(
                        source="baliforum",
                        external_id=event.external_id or event.url.split("/")[-1],
                        title=event.title,
                        description=event.description,
                        starts_at_utc=event.starts_at,
                        city="bali",
                        lat=event.lat,
                        lng=event.lng,
                        location_name=event.description or "",
                        location_url="",
                        url=event.url,
                    )

                    if event_id:
                        saved_count += 1

                except Exception as e:
                    error_count += 1
                    logger.error(f"   ❌ Ошибка сохранения события '{event.title}': {e}")

            duration = (time.time() - start_time) * 1000
            logger.info(
                f"   ✅ BaliForum: сохранено={saved_count}, "
                f"пропущено без координат={skipped_no_coords}, "
                f"ошибок={error_count}, время={duration:.0f}мс"
            )

        except Exception as e:
            logger.error(f"   ❌ Ошибка парсинга BaliForum: {e}")

    async def ingest_kudago(self):
        """Парсинг событий с KudaGo через правильную архитектуру"""
        try:
            from config import load_settings

            settings = load_settings()

            if not settings.kudago_enabled:
                logger.info("🎭 KudaGo отключен в настройках")
                return

            logger.info("🎭 Запуск парсинга KudaGo...")
            start_time = time.time()

            # Координаты центров городов для парсинга
            cities_coords = [
                (55.7558, 37.6173, "moscow"),  # Москва
                (59.9343, 30.3351, "spb"),  # СПб
            ]

            total_saved = 0
            total_errors = 0

            from sources.kudago_source import KudaGoSource

            kudago_source = KudaGoSource()

            for lat, lng, city in cities_coords:
                try:
                    logger.info(f"   🌍 Парсим {city}...")

                    # Получаем события через KudaGo источник
                    events = await kudago_source.fetch_events(lat, lng, 50)  # 50км радиус для города

                    saved_count = 0
                    error_count = 0

                    for event in events:
                        try:
                            # Логируем дату события для отладки
                            if event.get("starts_at"):
                                from datetime import datetime, timedelta
                                from zoneinfo import ZoneInfo

                                now_msk = datetime.now(ZoneInfo("Europe/Moscow"))
                                event_date_msk = event.get("starts_at").astimezone(ZoneInfo("Europe/Moscow")).date()
                                today_msk = now_msk.date()
                                tomorrow_msk = today_msk + timedelta(days=1)

                                date_label = (
                                    "сегодня"
                                    if event_date_msk == today_msk
                                    else "завтра"
                                    if event_date_msk == tomorrow_msk
                                    else f"{event_date_msk}"
                                )
                                logger.info(
                                    f"   📅 KudaGo событие: '{event.get('title', '')}' - {date_label} "
                                    f"({event.get('starts_at')})"
                                )

                            # ПРАВИЛЬНАЯ АРХИТЕКТУРА: Сохраняем через UnifiedEventsService
                            event_id = self.service.save_parser_event(
                                source="kudago",
                                external_id=str(event.get("source_id", event.get("title", ""))),
                                title=event["title"],
                                description=event.get("description", ""),
                                starts_at_utc=event["starts_at"],
                                city=event["city"],
                                lat=event.get("lat", 0.0),
                                lng=event.get("lon", 0.0),
                                location_name=event.get("venue_name", ""),
                                location_url=event.get("address", ""),
                                url=event.get("source_url", ""),
                            )

                            if event_id:
                                saved_count += 1

                        except Exception as e:
                            error_count += 1
                            logger.error(
                                f"   ❌ Ошибка сохранения KudaGo события '{event.get('title', 'Unknown')}': {e}"
                            )

                    total_saved += saved_count
                    total_errors += error_count

                    logger.info(f"   ✅ {city}: сохранено={saved_count}, ошибок={error_count}")

                except Exception as e:
                    total_errors += 1
                    logger.error(f"   ❌ Ошибка парсинга {city}: {e}")

            duration = (time.time() - start_time) * 1000
            logger.info(
                f"   ✅ KudaGo: всего сохранено={total_saved}, " f"ошибок={total_errors}, время={duration:.0f}мс"
            )

        except Exception as e:
            logger.error(f"   ❌ Ошибка парсинга KudaGo: {e}")

    async def ingest_ai_events(self):
        """Генерация AI событий через правильную архитектуру"""
        if not self.settings.ai_parse_enable:
            logger.info("🤖 AI парсинг отключен в настройках")
            return

        try:
            logger.info("🤖 Запуск AI генерации событий...")
            start_time = time.time()

            # Координаты центра Бали
            bali_coords = [
                (-8.6705, 115.2126),  # Denpasar
                (-8.5069, 115.2625),  # Ubud
                (-8.6482, 115.1342),  # Canggu
                (-8.7089, 115.1681),  # Seminyak
            ]

            import hashlib
            from datetime import datetime

            from ai_utils import fetch_ai_events_nearby

            total_ai_events = 0
            error_count = 0

            for lat, lng in bali_coords:
                try:
                    ai_events = await fetch_ai_events_nearby(lat, lng)

                    for event in ai_events:
                        try:
                            # Парсим время
                            starts_at = datetime.strptime(event["time_local"], "%Y-%m-%d %H:%M")

                            # Создаем стабильный external_id
                            raw_id = f"ai_{event['title']}_{event['time_local']}_{lat}_{lng}"
                            external_id = hashlib.sha1(raw_id.encode()).hexdigest()[:16]

                            # ПРАВИЛЬНАЯ АРХИТЕКТУРА: Сохраняем через UnifiedEventsService
                            event_id = self.service.save_parser_event(
                                source="ai",
                                external_id=external_id,
                                title=event["title"],
                                description=event.get("description", ""),
                                starts_at_utc=starts_at,
                                city="bali",
                                lat=event["lat"],
                                lng=event["lng"],
                                location_name=event.get("location_name", ""),
                                location_url=event.get("location_url", ""),
                                url=event.get("community_link", ""),
                            )

                            if event_id:
                                total_ai_events += 1

                        except Exception as e:
                            error_count += 1
                            logger.error(f"   ❌ Ошибка сохранения AI события '{event.get('title', 'Unknown')}': {e}")

                except Exception as e:
                    error_count += 1
                    logger.error(f"   ❌ Ошибка AI парсинга для ({lat}, {lng}): {e}")

            duration = (time.time() - start_time) * 1000
            logger.info(f"   ✅ AI: создано={total_ai_events}, ошибок={error_count}, время={duration:.0f}мс")

        except Exception as e:
            logger.error(f"   ❌ Ошибка AI парсинга: {e}")

    def cleanup_old_events(self):
        """Очистка старых событий"""
        try:
            logger.info("🧹 Очистка старых событий...")

            cities = ["bali", "moscow", "spb"]
            total_deleted = 0

            for city in cities:
                deleted = self.service.cleanup_old_events(city)
                total_deleted += deleted

            logger.info(f"   ✅ Очищено {total_deleted} старых событий")

        except Exception as e:
            logger.error(f"   ❌ Ошибка очистки: {e}")

    def run_full_ingest(self):
        """Полный цикл обновления событий"""
        logger.info("🚀 === НАЧАЛО ЦИКЛА ОБНОВЛЕНИЯ СОБЫТИЙ ===")
        start_time = time.time()

        # 1. Парсим BaliForum (для Бали)
        if self.settings.enable_baliforum:
            self.ingest_baliforum()
        else:
            logger.info("🌴 BaliForum пропущен (отключен в настройках)")

        # KudaGo теперь запускается отдельно по своему расписанию (см. start())

        # 3. Генерируем AI события (если включено)
        if self.settings.ai_generate_synthetic:
            import asyncio

            asyncio.run(self.ingest_ai_events())
        else:
            logger.info("🤖 AI генерация пропущена (отключена в настройках)")

        # 4. Очищаем старые события
        self.cleanup_old_events()

        duration = time.time() - start_time
        logger.info(f"✅ === ЦИКЛ ЗАВЕРШЕН ЗА {duration:.1f}с ===")

    def run_kudago_ingest(self):
        """Отдельный цикл парсинга KudaGo для Москвы и СПб"""
        logger.info("🎭 === НАЧАЛО ЦИКЛА ПАРСИНГА KUDAGO (МОСКВА, СПБ) ===")
        start_time = time.time()

        if self.settings.kudago_enabled:
            import asyncio

            asyncio.run(self.ingest_kudago())
        else:
            logger.info("🎭 KudaGo пропущен (отключен в настройках)")

        duration = time.time() - start_time
        logger.info(f"✅ === ЦИКЛ KUDAGO ЗАВЕРШЕН ЗА {duration:.1f}с ===")

    def cleanup_expired_tasks(self):
        """Очистка просроченных заданий"""
        try:
            from tasks_service import mark_tasks_as_expired

            logger.info("🧹 Запуск очистки просроченных заданий...")
            expired_count = mark_tasks_as_expired()

            if expired_count > 0:
                logger.info(f"✅ Помечено как истекшие: {expired_count} заданий")
            else:
                logger.info("ℹ️ Просроченных заданий не найдено")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки просроченных заданий: {e}")

    def cleanup_expired_community_events(self):
        """Очистка старых событий сообществ (перенос в архив)"""
        try:
            from utils.community_events_service import CommunityEventsService

            logger.info("🧹 Очистка старых событий сообществ...")
            community_service = CommunityEventsService()
            # Очищаем события старше 1 дня (они переносятся в архив)
            deleted_count = community_service.cleanup_expired_events(days_old=1)

            if deleted_count > 0:
                logger.info(f"   ✅ Архивировано и удалено {deleted_count} старых событий сообществ")
            else:
                logger.info("   ℹ️ Старых событий сообществ не найдено")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки событий сообществ: {e}")

    def check_removed_chats(self):
        """Проверка чатов, из которых бот мог быть удален"""
        try:
            from datetime import datetime

            from aiogram import Bot
            from sqlalchemy import select

            from config import load_settings
            from database import ChatSettings

            logger.info("🔍 Проверка чатов на удаление бота...")

            settings = load_settings()
            if not settings.telegram_token:
                logger.warning("⚠️ TELEGRAM_TOKEN не настроен, пропускаем проверку")
                return

            # Создаем async бота для проверки
            bot = Bot(token=settings.telegram_token)

            # Получаем engine и создаем session
            from database import async_engine, async_session_maker

            if not async_engine or not async_session_maker:
                logger.warning("⚠️ Async engine не инициализирован, пропускаем проверку")
                return

            async def check_chats_async():
                checked_count = 0
                removed_count = 0
                updated_admins_count = 0

                async with async_session_maker() as session:
                    # Получаем все активные чаты
                    result = await session.execute(select(ChatSettings).where(ChatSettings.bot_status == "active"))
                    chats = result.scalars().all()

                    logger.info(f"   Найдено {len(chats)} активных чатов для проверки")

                    for chat in chats:
                        checked_count += 1
                        try:
                            # Пробуем получить информацию о чате
                            # Если бот удален, это вызовет ошибку
                            await bot.get_chat(chat.chat_id)

                            # Обновляем админов
                            try:
                                import json

                                from utils.community_events_service import CommunityEventsService

                                community_service = CommunityEventsService()
                                admin_ids = await community_service.get_cached_admin_ids(bot, chat.chat_id)
                                admin_count = len(admin_ids)

                                # Обновляем только если изменилось
                                current_admin_ids = json.loads(chat.admin_ids) if chat.admin_ids else []
                                if set(admin_ids) != set(current_admin_ids):
                                    chat.admin_ids = json.dumps(admin_ids) if admin_ids else None
                                    chat.admin_count = admin_count
                                    updated_admins_count += 1
                                    logger.info(f"   📝 Обновлены админы для чата {chat.chat_id}: count={admin_count}")

                            except Exception as admin_error:
                                logger.warning(
                                    f"   ⚠️ Не удалось обновить админов для чата {chat.chat_id}: {admin_error}"
                                )

                        except Exception as e:
                            error_msg = str(e).lower()
                            # Проверяем, не был ли бот удален
                            if (
                                "bot was kicked" in error_msg
                                or "bot was removed" in error_msg
                                or "chat not found" in error_msg
                                or "forbidden" in error_msg
                            ):
                                logger.warning(f"   🚫 Бот удален из чата {chat.chat_id}")
                                chat.bot_status = "removed"
                                chat.bot_removed_at = datetime.utcnow()
                                removed_count += 1

                    await session.commit()
                    logger.info(
                        f"   ✅ Проверено {checked_count} чатов, удаленных найдено: {removed_count}, "
                        f"админов обновлено: {updated_admins_count}"
                    )

                await bot.session.close()

            # Запускаем async функцию
            import asyncio

            asyncio.run(check_chats_async())

        except Exception as e:
            logger.error(f"❌ Ошибка проверки удаленных чатов: {e}")

    def start(self):
        """Запуск планировщика"""
        if self.scheduler and self.scheduler.running:
            logger.warning("⚠️ Планировщик уже запущен")
            return

        self.scheduler = BackgroundScheduler(timezone="UTC")

        # Основной цикл парсинга событий BaliForum (2 раза в день по времени Бали)
        # Утренний запуск: 18:02 UTC = 00:02 Бали (начало нового дня по Бали)
        self.scheduler.add_job(
            self.run_full_ingest,
            "cron",
            hour=18,
            minute=2,
            id="modern-ingest-morning",
            max_instances=1,
            coalesce=True,
        )
        # Вечерний запуск: 04:02 UTC = 12:02 Бали (середина дня по Бали)
        self.scheduler.add_job(
            self.run_full_ingest,
            "cron",
            hour=4,
            minute=2,
            id="modern-ingest-evening",
            max_instances=1,
            coalesce=True,
        )

        # Парсинг KudaGo (Москва и СПб) - отдельное расписание по времени МСК
        # Утренний запуск: 21:02 UTC = 00:02 МСК (начало нового дня по МСК)
        self.scheduler.add_job(
            self.run_kudago_ingest,
            "cron",
            hour=21,
            minute=2,
            id="kudago-ingest-morning",
            max_instances=1,
            coalesce=True,
        )
        # Вечерний запуск: 09:02 UTC = 12:02 МСК (середина дня по МСК)
        self.scheduler.add_job(
            self.run_kudago_ingest,
            "cron",
            hour=9,
            minute=2,
            id="kudago-ingest-evening",
            max_instances=1,
            coalesce=True,
        )

        # Очистка старых событий каждые 6 часов
        self.scheduler.add_job(
            self.cleanup_old_events, "interval", hours=6, id="cleanup-cycle", max_instances=1, coalesce=True
        )

        # Очистка просроченных заданий каждые 2 часа
        self.scheduler.add_job(
            self.cleanup_expired_tasks, "interval", hours=2, id="tasks-cleanup", max_instances=1, coalesce=True
        )

        # Очистка старых событий сообществ отключена
        # События сообществ удаляются только вручную пользователями
        # Автоматическая очистка может удалить события, которые пользователи еще хотят видеть

        # Проверка удаленных чатов каждые 24 часа
        self.scheduler.add_job(
            self.check_removed_chats, "interval", hours=24, id="chat-status-check", max_instances=1, coalesce=True
        )

        self.scheduler.start()
        logger.info("🚀 Современный планировщик запущен!")
        logger.info("   📅 Полный цикл: каждые 12 часов (2 раза в день)")
        logger.info("   🌴 BaliForum (Бали) + 🎭 KudaGo (Москва, СПб)")
        logger.info("   🧹 Очистка событий: каждые 6 часов")
        logger.info("   ⏰ Очистка заданий: каждые 2 часа")
        logger.info("   🔍 Проверка удаленных чатов: каждые 24 часа")
        logger.info("   ℹ️ События сообществ удаляются только вручную")

        # Запускаем первый цикл сразу
        self.run_full_ingest()

    def stop(self):
        """Остановка планировщика"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("🛑 Планировщик остановлен")


# Глобальный экземпляр
_modern_scheduler = None


def get_modern_scheduler() -> ModernEventScheduler:
    """Получить экземпляр современного планировщика"""
    global _modern_scheduler
    if _modern_scheduler is None:
        _modern_scheduler = ModernEventScheduler()
    return _modern_scheduler


def start_modern_scheduler():
    """Запустить современный планировщик"""
    scheduler = get_modern_scheduler()
    scheduler.start()


if __name__ == "__main__":
    # Ручной запуск для тестирования
    logging.basicConfig(level=logging.INFO)
    scheduler = ModernEventScheduler()
    scheduler.run_full_ingest()
