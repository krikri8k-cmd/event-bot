"""
Сервис для управления банами пользователей
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class BanService:
    """Сервис для работы с банами пользователей"""

    def __init__(self, engine: Engine):
        self.engine = engine

    def is_banned(self, user_id: int) -> bool:
        """
        Проверяет, забанен ли пользователь (быстрая проверка через users.is_banned)

        Args:
            user_id: ID пользователя

        Returns:
            True если пользователь забанен, False если нет
        """
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT is_banned FROM users WHERE id = :user_id"),
                {"user_id": user_id},
            )
            row = result.fetchone()
            if row:
                return bool(row[0])
            return False

    async def is_banned_async(self, session: AsyncSession, user_id: int) -> bool:
        """
        Асинхронная проверка бана пользователя (быстрая проверка через users.is_banned)

        Args:
            session: AsyncSession
            user_id: ID пользователя

        Returns:
            True если пользователь забанен, False если нет
        """
        result = await session.execute(
            text("SELECT is_banned FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        )
        row = result.fetchone()
        if row:
            return bool(row[0])
        return False

    def ban_user(
        self,
        user_id: int,
        banned_by: int,
        reason: str | None = None,
        username: str | None = None,
        first_name: str | None = None,
        days: int | None = None,
    ) -> bool:
        """
        Банит пользователя

        Args:
            user_id: ID пользователя для бана
            banned_by: ID админа, который банит
            reason: Причина бана (опционально)
            username: Username пользователя (опционально)
            first_name: Имя пользователя (опционально)
            days: Количество дней бана (None = бессрочный)

        Returns:
            True если успешно, False если ошибка
        """
        try:
            expires_at = None
            if days:
                expires_at = datetime.utcnow() + timedelta(days=days)

            with self.engine.begin() as conn:
                # Проверяем, не забанен ли уже
                existing = conn.execute(
                    text("SELECT id FROM banned_users WHERE user_id = :user_id"),
                    {"user_id": user_id},
                ).fetchone()

                if existing:
                    # Обновляем существующий бан
                    conn.execute(
                        text(
                            """
                            UPDATE banned_users
                            SET banned_by = :banned_by,
                                reason = :reason,
                                username = :username,
                                first_name = :first_name,
                                expires_at = :expires_at,
                                is_active = TRUE,
                                banned_at = NOW()
                            WHERE user_id = :user_id
                            """
                        ),
                        {
                            "user_id": user_id,
                            "banned_by": banned_by,
                            "reason": reason,
                            "username": username,
                            "first_name": first_name,
                            "expires_at": expires_at,
                        },
                    )
                    logger.info(f"🔄 Обновлен бан для пользователя {user_id}")
                else:
                    # Создаем новый бан
                    conn.execute(
                        text(
                            """
                            INSERT INTO banned_users (user_id, username, first_name, banned_by, reason, expires_at)
                            VALUES (:user_id, :username, :first_name, :banned_by, :reason, :expires_at)
                            """
                        ),
                        {
                            "user_id": user_id,
                            "username": username,
                            "first_name": first_name,
                            "banned_by": banned_by,
                            "reason": reason,
                            "expires_at": expires_at,
                        },
                    )
                    logger.info(f"🚫 Пользователь {user_id} забанен админом {banned_by}")

                # Синхронизируем поле is_banned в таблице users
                conn.execute(
                    text("UPDATE users SET is_banned = TRUE WHERE id = :user_id"),
                    {"user_id": user_id},
                )

            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при бане пользователя {user_id}: {e}")
            return False

    def unban_user(self, user_id: int) -> bool:
        """
        Разбанивает пользователя

        Args:
            user_id: ID пользователя для разбана

        Returns:
            True если успешно, False если ошибка
        """
        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    text(
                        """
                        UPDATE banned_users
                        SET is_active = FALSE
                        WHERE user_id = :user_id
                        """
                    ),
                    {"user_id": user_id},
                )
                if result.rowcount > 0:
                    # Синхронизируем поле is_banned в таблице users
                    conn.execute(
                        text("UPDATE users SET is_banned = FALSE WHERE id = :user_id"),
                        {"user_id": user_id},
                    )
                    logger.info(f"✅ Пользователь {user_id} разбанен")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден в списке банов")
                    return False
        except Exception as e:
            logger.error(f"❌ Ошибка при разбане пользователя {user_id}: {e}")
            return False

    def get_banned_users(self, limit: int = 50) -> list[dict]:
        """
        Получает список забаненных пользователей

        Args:
            limit: Максимальное количество записей

        Returns:
            Список словарей с информацией о забаненных пользователях
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                        SELECT user_id, username, first_name, banned_by, reason, banned_at, expires_at
                        FROM banned_users
                        WHERE is_active = TRUE
                        ORDER BY banned_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
                return [
                    {
                        "user_id": row[0],
                        "username": row[1],
                        "first_name": row[2],
                        "banned_by": row[3],
                        "reason": row[4],
                        "banned_at": row[5],
                        "expires_at": row[6],
                    }
                    for row in result.fetchall()
                ]
        except Exception as e:
            logger.error(f"❌ Ошибка при получении списка банов: {e}")
            return []
