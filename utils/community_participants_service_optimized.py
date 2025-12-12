#!/usr/bin/env python3
"""
Оптимизированный сервис для работы с участниками Community событий
Использует столбцы participants_count и participants_ids в events_community
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import CommunityEvent

logger = logging.getLogger(__name__)


async def add_participant_optimized(
    session: AsyncSession, event_id: int, user_id: int, username: str | None = None
) -> bool:
    """
    Добавить участника к событию (оптимизированная версия)
    Обновляет participants_count и participants_ids в events_community
    """
    try:
        # Получаем событие
        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            logger.error(f"❌ Событие {event_id} не найдено")
            return False

        # Получаем текущий список участников
        participants = event.participants_ids or []

        # Проверяем, не является ли пользователь уже участником
        for participant in participants:
            if participant.get("user_id") == user_id:
                logger.info(f"ℹ️ Пользователь {user_id} уже участник события {event_id}")
                return False

        # Добавляем нового участника
        new_participant = {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now(UTC).isoformat(),
        }
        participants.append(new_participant)

        # Обновляем событие
        await session.execute(
            update(CommunityEvent)
            .where(CommunityEvent.id == event_id)
            .values(
                participants_count=len(participants),
                participants_ids=participants,
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

        logger.info(f"✅ Пользователь {user_id} добавлен к событию {event_id}")
        return True

    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Ошибка добавления участника: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


async def remove_participant_optimized(session: AsyncSession, event_id: int, user_id: int) -> bool:
    """
    Удалить участника из события (оптимизированная версия)
    """
    try:
        # Получаем событие
        stmt = select(CommunityEvent).where(CommunityEvent.id == event_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            logger.error(f"❌ Событие {event_id} не найдено")
            return False

        # Получаем текущий список участников
        participants = event.participants_ids or []

        # Удаляем участника
        original_count = len(participants)
        participants = [p for p in participants if p.get("user_id") != user_id]

        if len(participants) == original_count:
            logger.info(f"ℹ️ Пользователь {user_id} не был участником события {event_id}")
            return False

        # Обновляем событие
        await session.execute(
            update(CommunityEvent)
            .where(CommunityEvent.id == event_id)
            .values(
                participants_count=len(participants),
                participants_ids=participants,
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

        logger.info(f"✅ Пользователь {user_id} удален из события {event_id}")
        return True

    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Ошибка удаления участника: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return False


async def get_participants_count_optimized(session: AsyncSession, event_id: int) -> int:
    """
    Получить количество участников события (оптимизированная версия)
    """
    try:
        stmt = select(CommunityEvent.participants_count).where(CommunityEvent.id == event_id)
        result = await session.execute(stmt)
        count = result.scalar() or 0
        return count
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества участников: {e}")
        return 0


async def get_participants_optimized(session: AsyncSession, event_id: int) -> list[dict]:
    """
    Получить список участников события (оптимизированная версия)
    """
    try:
        stmt = select(CommunityEvent.participants_ids).where(CommunityEvent.id == event_id)
        result = await session.execute(stmt)
        participants = result.scalar() or []
        return participants
    except Exception as e:
        logger.error(f"❌ Ошибка получения участников: {e}")
        return []


async def is_participant_optimized(session: AsyncSession, event_id: int, user_id: int) -> bool:
    """
    Проверить, является ли пользователь участником события (оптимизированная версия)
    """
    try:
        stmt = select(CommunityEvent.participants_ids).where(CommunityEvent.id == event_id)
        result = await session.execute(stmt)
        participants = result.scalar() or []

        for participant in participants:
            if participant.get("user_id") == user_id:
                return True
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка проверки участника: {e}")
        return False
