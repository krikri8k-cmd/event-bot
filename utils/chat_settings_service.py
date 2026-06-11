"""Создание и обновление chat_settings при подключении бота к группе."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from aiogram import Bot
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import ChatSettings, User

logger = logging.getLogger(__name__)


async def ensure_chat_settings(
    session: AsyncSession,
    bot: Bot,
    chat_id: int,
    *,
    chat_type: str | None = None,
    adder_user_id: int | None = None,
    award_rockets: bool = False,
) -> bool:
    """
    Создаёт запись chat_settings или реактивирует существующую (bot_status=active).

    Returns:
        True если создана новая запись, False если уже была или обновлена.
    """
    result = await session.execute(select(ChatSettings).where(ChatSettings.chat_id == chat_id))
    settings = result.scalar_one_or_none()

    if settings:
        if settings.bot_status != "active":
            settings.bot_status = "active"
            settings.bot_removed_at = None
            await session.commit()
            logger.info("✅ chat_settings реактивирован для чата %s", chat_id)
        return False

    seq_row = await session.execute(text("SELECT nextval('chat_number_seq')"))
    chat_number = seq_row.scalar()

    admin_ids: list[int] = []
    admin_count = 0
    try:
        from utils.community_events_service import CommunityEventsService

        community_service = CommunityEventsService()
        admin_ids = await community_service.get_cached_admin_ids(bot, chat_id)
        admin_count = len(admin_ids)
    except Exception as e:
        logger.warning("⚠️ ensure_chat_settings: не удалось получить админов для %s: %s", chat_id, e)

    settings = ChatSettings(
        chat_id=chat_id,
        chat_number=chat_number,
        admin_ids=json.dumps(admin_ids) if admin_ids else None,
        admin_count=admin_count,
        bot_status="active",
        total_events=0,
    )
    try:
        session.add(settings)
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(
            "❌ Не удалось создать chat_settings для %s (chat_number_seq есть?): %s",
            chat_id,
            e,
            exc_info=True,
        )
        raise

    logger.info("✅ chat_settings создан для чата %s, chat_number=%s", chat_id, chat_number)

    if award_rockets and adder_user_id and chat_type != "channel":
        try:
            user_result = await session.execute(select(User).where(User.id == adder_user_id))
            user = user_result.scalar_one_or_none()
            if user and not settings.rockets_awarded_at:
                user.rockets_balance = (user.rockets_balance or 0) + 150
                settings.added_by_user_id = adder_user_id
                settings.rockets_awarded_at = datetime.now(UTC)
                await session.commit()
                logger.info("🎉 Начислено 150 ракет пользователю %s за чат %s", adder_user_id, chat_id)
        except Exception as e:
            logger.error("❌ Ошибка начисления ракет за добавление бота: %s", e)

    return True
