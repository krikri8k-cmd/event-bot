"""
Утилиты для работы с языком пользователя
"""

import logging

from database import User, get_session

logger = logging.getLogger(__name__)


def get_user_language(user_id: int) -> str | None:
    """
    Получить язык пользователя из БД

    Args:
        user_id: ID пользователя Telegram

    Returns:
        Код языка ('ru', 'en') или None, если язык не выбран
    """
    try:
        with get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                return user.language_code
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка получения языка пользователя {user_id}: {e}")
        return None


def set_user_language(user_id: int, lang: str) -> bool:
    """
    Установить язык пользователя в БД

    Args:
        user_id: ID пользователя Telegram
        lang: Код языка ('ru' или 'en')

    Returns:
        True если успешно, False если ошибка
    """
    if lang not in ["ru", "en"]:
        logger.warning(f"⚠️ Попытка установить неподдерживаемый язык: {lang}")
        return False

    try:
        with get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                user.language_code = lang
                session.commit()
                logger.info(f"✅ Язык пользователя {user_id} установлен: {lang}")
                return True
            else:
                # Если пользователя нет, создаём его с языком
                # Но лучше сначала создать пользователя через ensure_user_exists
                logger.warning(f"⚠️ Пользователь {user_id} не найден при установке языка")
                return False
    except Exception as e:
        logger.error(f"❌ Ошибка установки языка пользователя {user_id}: {e}")
        return False


def get_user_language_or_default(user_id: int, default: str = "ru") -> str:
    """
    Получить язык пользователя или вернуть значение по умолчанию

    Args:
        user_id: ID пользователя Telegram
        default: Язык по умолчанию (по умолчанию 'ru')

    Returns:
        Код языка ('ru' или 'en')
    """
    lang = get_user_language(user_id)
    if lang in ["ru", "en"]:
        return lang
    return default


def needs_language_selection(user_id: int) -> bool:
    """
    Проверить, нужно ли показывать экран выбора языка

    Args:
        user_id: ID пользователя Telegram

    Returns:
        True если язык не выбран (NULL), False если выбран
    """
    lang = get_user_language(user_id)
    return lang is None
