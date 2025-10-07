"""
Утилиты для создания кнопок участия в событиях
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.user_participation_service import UserParticipationService


def create_participation_buttons(
    event_id: int,
    user_id: int,
    participation_service: UserParticipationService,
    include_maps: bool = True,
    maps_url: str = None,
) -> InlineKeyboardMarkup:
    """
    Создает простую кнопку для добавления события в "Мои события"

    Args:
        event_id: ID события
        user_id: ID пользователя
        participation_service: Сервис участия
        include_maps: Включать ли кнопку карты
        maps_url: URL для кнопки карты

    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками участия
    """
    # Получаем текущий статус участия пользователя
    current_status = participation_service.get_user_participation_status(user_id, event_id)

    # Создаем кнопки участия
    participation_buttons = []

    if current_status:
        # Пользователь уже добавил событие - показываем кнопку удаления
        participation_buttons.append(
            [InlineKeyboardButton(text="❌ Убрать из моих событий", callback_data=f"part_remove:{event_id}")]
        )
    else:
        # Пользователь не добавил событие - показываем кнопку добавления
        participation_buttons.append(
            [InlineKeyboardButton(text="➕ Добавить в мои события", callback_data=f"part_add:{event_id}")]
        )

    # Добавляем кнопку карты если нужно
    if include_maps and maps_url:
        participation_buttons.append([InlineKeyboardButton(text="🗺️ Маршрут", url=maps_url)])

    return InlineKeyboardMarkup(inline_keyboard=participation_buttons)


def create_events_list_with_participation(
    events: list, user_id: int, participation_service: UserParticipationService, page: int = 1, page_size: int = 5
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Создает список событий с кнопками участия

    Args:
        events: Список событий
        user_id: ID пользователя
        participation_service: Сервис участия
        page: Номер страницы
        page_size: Размер страницы

    Returns:
        tuple: (текст сообщения, клавиатура)
    """
    if not events:
        return "📅 События не найдены", InlineKeyboardMarkup(inline_keyboard=[])

    # Пагинация
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_events = events[start_idx:end_idx]

    text = f"📅 **События (страница {page}):**\n\n"

    for i, event in enumerate(page_events, start_idx + 1):
        event_id = event.get("id")
        title = event.get("title", "Без названия")
        starts_at = event.get("starts_at")
        location = event.get("location_name", "Место уточняется")

        # Форматируем время
        if starts_at:
            time_str = starts_at.strftime("%H:%M")
        else:
            time_str = "Время уточняется"

        # Получаем статус участия
        participation_status = participation_service.get_user_participation_status(user_id, event_id)

        # Добавляем индикатор участия
        status_emoji = ""
        if participation_status == "going":
            status_emoji = "✅ "
        elif participation_status == "maybe":
            status_emoji = "🤔 "

        text += f"{status_emoji}{i}) **{title}** – {time_str}\n"
        text += f"📍 {location}\n\n"

    # Создаем кнопки навигации
    keyboard_buttons = []

    # Кнопки пагинации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"page:{page-1}"))
    if end_idx < len(events):
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"page:{page+1}"))

    if nav_buttons:
        keyboard_buttons.append(nav_buttons)

    # Кнопка возврата
    keyboard_buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")])

    return text, InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
