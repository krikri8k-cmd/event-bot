#!/usr/bin/env python3
"""
Утилиты для единообразного отображения автора событий
"""

import html


def format_author_display(organizer_id: int | None, organizer_username: str | None) -> str:
    """
    Форматирует отображение автора события единообразно

    Args:
        organizer_id: ID организатора
        organizer_username: Username организатора (может быть None)

    Returns:
        Отформатированная строка для отображения автора
    """
    if organizer_id and organizer_username and organizer_username != "None":
        # Есть username - показываем @username
        return f'👤 <a href="tg://user?id={organizer_id}">@{html.escape(organizer_username)}</a>'
    elif organizer_id:
        # Есть ID но нет username - показываем "Автор"
        return f'👤 <a href="tg://user?id={organizer_id}">Автор</a>'
    else:
        # Нет данных - показываем общий "Автор"
        return "👤 Автор"


def format_author_simple(organizer_username: str | None) -> str:
    """
    Форматирует простое отображение автора (без HTML ссылок)

    Args:
        organizer_username: Username организатора (может быть None)

    Returns:
        Отформатированная строка для отображения автора
    """
    if organizer_username and organizer_username != "None":
        return f"@{organizer_username}"
    else:
        return "Аноним"


def format_author_with_group(
    organizer_id: int | None, organizer_username: str | None, group_name: str | None = None
) -> str:
    """
    Форматирует отображение автора события из группы с пометкой о группе

    Args:
        organizer_id: ID организатора
        organizer_username: Username организатора (может быть None)
        group_name: Название группы (может быть None)

    Returns:
        Отформатированная строка для отображения автора с пометкой о группе
    """
    # Формируем часть с автором
    if organizer_id and organizer_username and organizer_username != "None":
        author_part = f'👥 <a href="tg://user?id={organizer_id}">@{html.escape(organizer_username)}</a>'
    elif organizer_id:
        author_part = f'👥 <a href="tg://user?id={organizer_id}">Автор</a>'
    else:
        author_part = "👥 Автор"

    # Формируем часть с группой
    if group_name:
        group_part = f"👥 @{html.escape(group_name)}"
    else:
        group_part = "👥 (из группы)"

    return f"{author_part}  {group_part}"


def get_organizer_username_from_telegram_user(telegram_user) -> str | None:
    """
    Получает username из объекта Telegram User

    Args:
        telegram_user: Объект пользователя Telegram (callback.from_user)

    Returns:
        Username или None
    """
    return telegram_user.username
