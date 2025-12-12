#!/usr/bin/env python3
"""
Сервис для работы с участниками Community событий
"""

import logging

from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CommunityParticipantsService:
    """Сервис для управления участниками Community событий"""

    def __init__(self, engine: Engine):
        self.engine = engine

    def add_participant(self, event_id: int, user_id: int, username: str | None = None) -> bool:
        """
        Добавить участника к событию

        Args:
            event_id: ID события
            user_id: ID пользователя
            username: Username пользователя (опционально)

        Returns:
            True если добавлен, False если уже был участником
        """
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    text("""
                        INSERT INTO community_event_participants (event_id, user_id, username)
                        VALUES (:event_id, :user_id, :username)
                        ON CONFLICT (event_id, user_id) DO NOTHING
                        RETURNING id
                    """),
                    {"event_id": event_id, "user_id": user_id, "username": username},
                )
                row = result.fetchone()
                if row:
                    logger.info(f"✅ Пользователь {user_id} добавлен к событию {event_id}")
                    return True
                else:
                    logger.info(f"ℹ️ Пользователь {user_id} уже участник события {event_id}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка добавления участника: {e}")
            return False

    def remove_participant(self, event_id: int, user_id: int) -> bool:
        """
        Удалить участника из события

        Args:
            event_id: ID события
            user_id: ID пользователя

        Returns:
            True если удален, False если не был участником
        """
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    text("""
                        DELETE FROM community_event_participants
                        WHERE event_id = :event_id AND user_id = :user_id
                        RETURNING id
                    """),
                    {"event_id": event_id, "user_id": user_id},
                )
                row = result.fetchone()
                if row:
                    logger.info(f"✅ Пользователь {user_id} удален из события {event_id}")
                    return True
                else:
                    logger.info(f"ℹ️ Пользователь {user_id} не был участником события {event_id}")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка удаления участника: {e}")
            return False

    def get_participants_count(self, event_id: int) -> int:
        """
        Получить количество участников события

        Args:
            event_id: ID события

        Returns:
            Количество участников
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM community_event_participants
                        WHERE event_id = :event_id
                    """),
                    {"event_id": event_id},
                )
                count = result.scalar() or 0
                return count
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества участников: {e}")
            return 0

    def get_participants(self, event_id: int) -> list[dict]:
        """
        Получить список участников события

        Args:
            event_id: ID события

        Returns:
            Список участников [{"user_id": int, "username": str}]
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT user_id, username, created_at
                        FROM community_event_participants
                        WHERE event_id = :event_id
                        ORDER BY created_at ASC
                    """),
                    {"event_id": event_id},
                )
                participants = []
                for row in result.fetchall():
                    participants.append(
                        {
                            "user_id": row[0],
                            "username": row[1],
                            "created_at": row[2],
                        }
                    )
                return participants
        except Exception as e:
            logger.error(f"❌ Ошибка получения участников: {e}")
            return []

    def is_participant(self, event_id: int, user_id: int) -> bool:
        """
        Проверить, является ли пользователь участником события

        Args:
            event_id: ID события
            user_id: ID пользователя

        Returns:
            True если участник, False если нет
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT id
                        FROM community_event_participants
                        WHERE event_id = :event_id AND user_id = :user_id
                        LIMIT 1
                    """),
                    {"event_id": event_id, "user_id": user_id},
                )
                return result.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки участника: {e}")
            return False


# Async версии для использования с AsyncSession
async def add_participant_async(
    session: AsyncSession, event_id: int, user_id: int, username: str | None = None
) -> bool:
    """Асинхронная версия добавления участника"""
    from sqlalchemy import text

    try:
        result = await session.execute(
            text("""
                INSERT INTO community_event_participants (event_id, user_id, username)
                VALUES (:event_id, :user_id, :username)
                ON CONFLICT (event_id, user_id) DO NOTHING
                RETURNING id
            """),
            {"event_id": event_id, "user_id": user_id, "username": username},
        )
        await session.commit()
        row = result.fetchone()
        if row:
            logger.info(f"✅ Пользователь {user_id} добавлен к событию {event_id}")
            return True
        else:
            logger.info(f"ℹ️ Пользователь {user_id} уже участник события {event_id}")
            return False
    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Ошибка добавления участника: {e}")
        return False


async def remove_participant_async(session: AsyncSession, event_id: int, user_id: int) -> bool:
    """Асинхронная версия удаления участника"""
    from sqlalchemy import text

    try:
        result = await session.execute(
            text("""
                DELETE FROM community_event_participants
                WHERE event_id = :event_id AND user_id = :user_id
                RETURNING id
            """),
            {"event_id": event_id, "user_id": user_id},
        )
        await session.commit()
        row = result.fetchone()
        if row:
            logger.info(f"✅ Пользователь {user_id} удален из события {event_id}")
            return True
        else:
            logger.info(f"ℹ️ Пользователь {user_id} не был участником события {event_id}")
            return False
    except Exception as e:
        await session.rollback()
        logger.error(f"❌ Ошибка удаления участника: {e}")
        return False


async def get_participants_count_async(session: AsyncSession, event_id: int) -> int:
    """Асинхронная версия получения количества участников"""
    from sqlalchemy import text

    try:
        result = await session.execute(
            text("""
                SELECT COUNT(*)
                FROM community_event_participants
                WHERE event_id = :event_id
            """),
            {"event_id": event_id},
        )
        count = result.scalar() or 0
        return count
    except Exception as e:
        logger.error(f"❌ Ошибка получения количества участников: {e}")
        return 0


async def get_participants_async(session: AsyncSession, event_id: int) -> list[dict]:
    """Асинхронная версия получения списка участников"""
    from sqlalchemy import text

    try:
        result = await session.execute(
            text("""
                SELECT user_id, username, created_at
                FROM community_event_participants
                WHERE event_id = :event_id
                ORDER BY created_at ASC
            """),
            {"event_id": event_id},
        )
        participants = []
        for row in result.fetchall():
            participants.append(
                {
                    "user_id": row[0],
                    "username": row[1],
                    "created_at": row[2],
                }
            )
        return participants
    except Exception as e:
        logger.error(f"❌ Ошибка получения участников: {e}")
        return []


async def is_participant_async(session: AsyncSession, event_id: int, user_id: int) -> bool:
    """Асинхронная версия проверки участника"""
    from sqlalchemy import text

    try:
        result = await session.execute(
            text("""
                SELECT id
                FROM community_event_participants
                WHERE event_id = :event_id AND user_id = :user_id
                LIMIT 1
            """),
            {"event_id": event_id, "user_id": user_id},
        )
        return result.fetchone() is not None
    except Exception as e:
        logger.error(f"❌ Ошибка проверки участника: {e}")
        return False
