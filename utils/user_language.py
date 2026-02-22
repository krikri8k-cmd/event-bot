"""
Утилиты для работы с языком пользователя и отображением событий (RU/EN).
"""

import logging

from sqlalchemy import select

from database import ChatSettings, User, get_session

logger = logging.getLogger(__name__)


# --- Отображение событий по языку (title/description, без перевода локаций) ---


def get_event_title(event, lang: str) -> str:
    """Заголовок события для языка: EN и есть title_en → title_en, иначе title."""
    if lang == "en" and getattr(event, "title_en", None) and (event.title_en or "").strip():
        return event.title_en or event.title or ""
    return getattr(event, "title", None) or ""


def get_event_description(event, lang: str) -> str | None:
    """Описание события для языка: EN и есть description_en → description_en, иначе description."""
    if lang == "en" and getattr(event, "description_en", None) and (event.description_en or "").strip():
        return event.description_en or event.description
    return getattr(event, "description", None)


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
    Получить язык пользователя или вернуть значение по умолчанию (синхронно).

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


async def get_user_language_async(user_id: int, chat_id: int | None = None) -> str:
    """
    Язык для ответа: пользователь → язык чата (default_language) → 'ru'.
    Использовать в хендлерах групп и ЛС, когда нужен учёт языка чата.

    Args:
        user_id: ID пользователя Telegram
        chat_id: ID чата (для групп — fallback на chat_settings.default_language)

    Returns:
        'ru' или 'en'
    """
    from database import async_session_maker

    if async_session_maker is None:
        return get_user_language_or_default(user_id)

    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.language_code in ("ru", "en"):
            return user.language_code
        if chat_id:
            result = await session.execute(select(ChatSettings).where(ChatSettings.chat_id == chat_id))
            chat = result.scalar_one_or_none()
            if chat and getattr(chat, "default_language", None) in ("ru", "en"):
                return chat.default_language
    return "ru"


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
