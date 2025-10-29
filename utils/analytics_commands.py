"""
Команды для просмотра аналитики бота
Доступны только администраторам
"""

import logging
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.engine import Engine

from utils.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)

# ID администраторов (добавьте свои)
ADMIN_IDS = [123456789]  # Замените на реальные ID


def is_admin(user_id: int) -> bool:
    """Проверить является ли пользователь администратором"""
    return user_id in ADMIN_IDS


async def handle_analytics_command(message: Message, engine: Engine):
    """Обработчик команды /analytics"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для просмотра аналитики")
        return

    AnalyticsService(engine)

    # Создаем клавиатуру с опциями аналитики
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Общая статистика", callback_data="analytics:overview")],
            [InlineKeyboardButton(text="👥 Активность пользователей", callback_data="analytics:users")],
            [InlineKeyboardButton(text="🏢 Статистика групп", callback_data="analytics:groups")],
            [InlineKeyboardButton(text="📈 Тренды (30 дней)", callback_data="analytics:trends")],
            [InlineKeyboardButton(text="🔄 Обновить данные", callback_data="analytics:refresh")],
        ]
    )

    await message.answer(
        "📊 **Панель аналитики EventAroundBot**\n\n" "Выберите раздел для просмотра:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def handle_analytics_callback(callback_query, engine: Engine):
    """Обработчик callback'ов для аналитики"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("❌ У вас нет прав для просмотра аналитики")
        return

    analytics_service = AnalyticsService(engine)
    action = callback_query.data.split(":")[1]

    try:
        if action == "overview":
            await show_overview(callback_query, analytics_service)
        elif action == "users":
            await show_user_activity(callback_query, analytics_service)
        elif action == "groups":
            await show_group_stats(callback_query, analytics_service)
        elif action == "trends":
            await show_trends(callback_query, analytics_service)
        elif action == "refresh":
            await refresh_analytics(callback_query, analytics_service)
        else:
            await callback_query.answer("❌ Неизвестное действие")

    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике аналитики: {e}")
        await callback_query.answer("❌ Ошибка при получении данных")


async def show_overview(callback_query, analytics_service: AnalyticsService):
    """Показать общую статистику"""
    # Получаем последние данные
    user_activity = analytics_service.get_latest_metric("daily_user_activity")
    group_stats = analytics_service.get_latest_metric("group_statistics")

    if not user_activity and not group_stats:
        await callback_query.answer("📊 Данные аналитики пока не собраны")
        return

    text = "📊 **Общая статистика**\n\n"

    if user_activity:
        text += "👥 **Пользователи:**\n"
        text += f"• Всего: {user_activity.get('total_users', 0)}\n"
        text += f"• Активных сегодня: {user_activity.get('active_users', 0)}\n"
        text += f"• Новых сегодня: {user_activity.get('new_users', 0)}\n"
        text += f"• В личных чатах: {user_activity.get('private_chats', 0)}\n"
        text += f"• В группах: {user_activity.get('group_chats', 0)}\n\n"

    if group_stats:
        text += "🏢 **Группы:**\n"
        text += f"• Всего: {group_stats.get('total_groups', 0)}\n"
        text += f"• Активных: {group_stats.get('active_groups', 0)}\n"
        text += f"• С событиями: {group_stats.get('groups_with_events', 0)}\n"

    await callback_query.message.edit_text(text, parse_mode="Markdown")


async def show_user_activity(callback_query, analytics_service: AnalyticsService):
    """Показать активность пользователей"""
    user_activity = analytics_service.get_latest_metric("daily_user_activity")

    if not user_activity:
        await callback_query.answer("📊 Данные активности пользователей не найдены")
        return

    text = "👥 **Активность пользователей**\n\n"
    text += f"📅 Дата: {date.today().strftime('%d.%m.%Y')}\n\n"
    text += "🔢 **Общая статистика:**\n"
    text += f"• Всего пользователей: {user_activity.get('total_users', 0)}\n"
    text += f"• Активных сегодня: {user_activity.get('active_users', 0)}\n"
    text += f"• Новых сегодня: {user_activity.get('new_users', 0)}\n\n"

    text += "💬 **По типам чатов:**\n"
    text += f"• Личные чаты: {user_activity.get('private_chats', 0)}\n"
    text += f"• Групповые чаты: {user_activity.get('group_chats', 0)}\n\n"

    # Вычисляем проценты
    total_users = user_activity.get("total_users", 1)
    active_users = user_activity.get("active_users", 0)
    activity_rate = round((active_users / total_users) * 100, 1)

    text += f"📈 **Активность:** {activity_rate}%"

    await callback_query.message.edit_text(text, parse_mode="Markdown")


async def show_group_stats(callback_query, analytics_service: AnalyticsService):
    """Показать статистику групп"""
    group_stats = analytics_service.get_latest_metric("group_statistics")

    if not group_stats:
        await callback_query.answer("📊 Данные статистики групп не найдены")
        return

    text = "🏢 **Статистика групп**\n\n"
    text += f"📅 Дата: {date.today().strftime('%d.%m.%Y')}\n\n"

    total_groups = group_stats.get("total_groups", 0)
    active_groups = group_stats.get("active_groups", 0)
    groups_with_events = group_stats.get("groups_with_events", 0)

    text += "🔢 **Общая статистика:**\n"
    text += f"• Всего групп: {total_groups}\n"
    text += f"• Активных (7 дней): {active_groups}\n"
    text += f"• С событиями (30 дней): {groups_with_events}\n\n"

    # Вычисляем проценты
    if total_groups > 0:
        activity_rate = round((active_groups / total_groups) * 100, 1)
        events_rate = round((groups_with_events / total_groups) * 100, 1)

        text += "📈 **Проценты:**\n"
        text += f"• Активность: {activity_rate}%\n"
        text += f"• С событиями: {events_rate}%"

    await callback_query.message.edit_text(text, parse_mode="Markdown")


async def show_trends(callback_query, analytics_service: AnalyticsService):
    """Показать тренды за 30 дней"""
    trends = analytics_service.get_dau_trend(30)

    if not trends:
        await callback_query.answer("📊 Данные трендов не найдены")
        return

    text = "📈 **Тренды за 30 дней**\n\n"

    # Показываем последние 7 дней
    recent_trends = trends[:7]

    for trend in recent_trends:
        trend_date = trend["date"].strftime("%d.%m")
        active_users = trend["data"].get("active_users", 0)
        new_users = trend["data"].get("new_users", 0)

        text += f"📅 **{trend_date}:**\n"
        text += f"• Активных: {active_users}\n"
        text += f"• Новых: {new_users}\n\n"

    await callback_query.message.edit_text(text, parse_mode="Markdown")


async def refresh_analytics(callback_query, analytics_service: AnalyticsService):
    """Обновить данные аналитики"""
    await callback_query.answer("🔄 Обновляем данные...")

    # Собираем новые данные
    user_success = analytics_service.collect_daily_user_activity()
    group_success = analytics_service.collect_group_statistics()

    if user_success and group_success:
        await callback_query.answer("✅ Данные обновлены!")
    else:
        await callback_query.answer("⚠️ Частично обновлено (возможны ошибки)")


async def setup_analytics_commands(router, engine: Engine):
    """Настроить команды аналитики"""
    from aiogram import F
    from aiogram.filters import Command
    from aiogram.types import CallbackQuery

    # Команда /analytics
    @router.message(Command("analytics"))
    async def analytics_command(message: Message):
        await handle_analytics_command(message, engine)

    # Callback для кнопок аналитики
    @router.callback_query(F.data.startswith("analytics:"))
    async def analytics_callback(callback_query: CallbackQuery):
        await handle_analytics_callback(callback_query, engine)
