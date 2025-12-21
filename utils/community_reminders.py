#!/usr/bin/env python3
"""
Утилиты для отправки напоминаний о Community событиях
"""

import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import load_settings
from database import CommunityEvent, init_engine
from utils.community_participants_service_optimized import get_participants_optimized
from utils.messaging_utils import send_tracked

logger = logging.getLogger(__name__)


def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown"""
    return text.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")


async def send_24h_reminders(bot: Bot, session: AsyncSession):
    """
    Отправляет напоминания о событиях, которые начнутся через 24 часа
    """
    try:
        # Вычисляем временной диапазон: события, которые начнутся через 23-25 часов
        # Это позволяет отправлять напоминание один раз, даже если задача запускается несколько раз
        now = datetime.now(UTC)
        target_time = now + timedelta(hours=24)

        # Диапазон: от 23.5 до 24.5 часов (окно в 1 час)
        time_min = target_time - timedelta(minutes=30)
        time_max = target_time + timedelta(minutes=30)

        # Для Community событий starts_at - это TIMESTAMP WITHOUT TIME ZONE
        # Нужно сравнивать без timezone
        time_min_naive = time_min.replace(tzinfo=None)
        time_max_naive = time_max.replace(tzinfo=None)

        logger.info(f"🔔 Проверка событий для напоминаний: ищем события между {time_min_naive} и {time_max_naive}")

        # Получаем события, которые начнутся через ~24 часа
        stmt = (
            select(CommunityEvent)
            .where(
                CommunityEvent.status == "open",
                CommunityEvent.starts_at >= time_min_naive,
                CommunityEvent.starts_at <= time_max_naive,
            )
            .order_by(CommunityEvent.starts_at)
        )

        result = await session.execute(stmt)
        events = result.scalars().all()

        logger.info(f"🔔 Найдено {len(events)} событий для отправки напоминаний")

        sent_count = 0
        skipped_count = 0

        for event in events:
            try:
                # Получаем участников
                participants = await get_participants_optimized(session, event.id)

                if not participants or len(participants) == 0:
                    logger.info(f"⏭️ Пропускаем событие {event.id} '{event.title}': нет участников")
                    skipped_count += 1
                    continue

                # Формируем текст напоминания (похоже на уведомление о новом событии)
                safe_title = escape_markdown(event.title)
                safe_description = escape_markdown(event.description or "")
                safe_location = escape_markdown(event.location_name or "Место не указано")
                safe_city = escape_markdown(event.city or "")
                safe_username = escape_markdown(event.organizer_username or "Пользователь")

                # Форматируем дату и время
                event_time = event.starts_at
                if event_time:
                    date_str = event_time.strftime("%d.%m.%Y")
                    time_str = event_time.strftime("%H:%M")
                else:
                    date_str = "Дата не указана"
                    time_str = ""

                # Формируем список участников для отметки
                mentions = []
                for participant in participants:
                    username = participant.get("username")
                    if username:
                        mentions.append(f"@{username}")

                mentions_text = " ".join(mentions) if mentions else ""

                # Формируем текст сообщения (похоже на уведомление о новом событии)
                reminder_text = "⏰ **Напоминание о событии!**\n\n"
                reminder_text += f"**{safe_title}**\n"
                reminder_text += f"📅 {date_str} в {time_str}\n"

                if safe_city:
                    reminder_text += f"🏙️ {safe_city}\n"
                reminder_text += f"📍 {safe_location}\n"

                if event.location_url:
                    reminder_text += f"🔗 {event.location_url}\n"

                if safe_description:
                    reminder_text += f"\n📝 {safe_description}\n"

                reminder_text += f"\n*Создано пользователем @{safe_username}*\n\n"
                reminder_text += f"👥 **Участники ({len(participants)}):**\n"
                reminder_text += mentions_text

                # Отправляем в группу
                try:
                    await send_tracked(
                        bot,
                        session,
                        chat_id=event.chat_id,
                        text=reminder_text,
                        tag="reminder",
                        parse_mode="Markdown",
                    )
                    logger.info(f"✅ Отправлено напоминание о событии {event.id} '{event.title}' в чат {event.chat_id}")
                    sent_count += 1

                    # Небольшая задержка между отправками
                    import asyncio

                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"❌ Ошибка отправки напоминания для события {event.id}: {e}")
                    continue

            except Exception as e:
                logger.error(f"❌ Ошибка обработки события {event.id}: {e}")
                import traceback

                logger.error(traceback.format_exc())
                continue

        logger.info(f"🔔 Итоги отправки напоминаний: отправлено {sent_count}, пропущено {skipped_count}")

    except Exception as e:
        logger.error(f"❌ Ошибка при отправке напоминаний: {e}")
        import traceback

        logger.error(traceback.format_exc())


async def send_24h_reminders_sync(bot_token: str):
    """
    Синхронная обертка для отправки напоминаний за 24 часа (для использования в планировщике)
    """
    from aiogram import Bot
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    settings = load_settings()
    init_engine(settings.database_url)

    # Создаем async engine для работы с async сессиями
    async_engine = create_async_engine(
        settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
        echo=False,
    )

    async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    bot = Bot(token=bot_token)

    try:
        async with async_session() as session:
            await send_24h_reminders(bot, session)
    finally:
        await bot.session.close()
        await async_engine.dispose()
