#!/usr/bin/env python3
"""
Обработчик команды /today для поиска событий на сегодня
Поддерживает выбор города (Москва/СПб) и радиус поиска
"""

import logging
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from sources.registry import get_sources_by_country
from utils.geo_bounds import is_allowed

logger = logging.getLogger(__name__)

# Роутер для обработчиков
router = Router()

# Координаты городов
CITY_COORDS = {
    "moscow": (55.7558, 37.6173, "Москва"),
    "spb": (59.9343, 30.3351, "Санкт-Петербург"),
}

# Радиусы поиска
RADIUS_OPTIONS = [5, 10, 15]


@router.message(Command("today"))
async def handle_today_command(message: types.Message):
    """Обработчик команды /today - показывает выбор города"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏙️ Москва", callback_data="today_city_moscow"),
                InlineKeyboardButton(text="🏛️ СПб", callback_data="today_city_spb"),
            ]
        ]
    )

    await message.answer(
        "🌍 <b>События на сегодня</b>\n\n" "Выберите город для поиска событий:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("today_city_"))
async def handle_city_selection(callback: types.CallbackQuery):
    """Обработчик выбора города"""

    city_key = callback.data.replace("today_city_", "")

    if city_key not in CITY_COORDS:
        await callback.answer("❌ Неизвестный город", show_alert=True)
        return

    lat, lng, city_name = CITY_COORDS[city_key]

    # Создаем клавиатуру с радиусами
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 км", callback_data=f"today_radius_{city_key}_5"),
                InlineKeyboardButton(text="10 км", callback_data=f"today_radius_{city_key}_10"),
                InlineKeyboardButton(text="15 км", callback_data=f"today_radius_{city_key}_15"),
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="today_back"),
            ],
        ]
    )

    await callback.message.edit_text(
        f"🌍 <b>События в {city_name}</b>\n\n" "Выберите радиус поиска:", reply_markup=keyboard, parse_mode="HTML"
    )

    await callback.answer()


@router.callback_query(F.data.startswith("today_radius_"))
async def handle_radius_selection(callback: types.CallbackQuery):
    """Обработчик выбора радиуса и поиска событий"""

    try:
        # Парсим данные: today_radius_{city}_{radius}
        parts = callback.data.split("_")
        city_key = parts[2]
        radius = int(parts[3])

        if city_key not in CITY_COORDS:
            await callback.answer("❌ Неизвестный город", show_alert=True)
            return

        lat, lng, city_name = CITY_COORDS[city_key]

        # Показываем индикатор загрузки
        loading_message = await callback.message.answer(
            f"🔍 Ищу события в {city_name} в радиусе {radius} км...\n" "⏳ Пожалуйста, подождите...", parse_mode="HTML"
        )

        # Ищем события
        events = await search_events_for_city(city_key, lat, lng, radius)

        # Удаляем сообщение загрузки
        await loading_message.delete()

        if not events:
            # Создаем клавиатуру для повторного поиска
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔄 Попробовать снова", callback_data=f"today_radius_{city_key}_{radius}"
                        ),
                        InlineKeyboardButton(text="🔙 Выбрать город", callback_data="today_back"),
                    ]
                ]
            )

            await callback.message.edit_text(
                f"😔 <b>События не найдены</b>\n\n"
                f"В {city_name} в радиусе {radius} км на сегодня событий не найдено.\n\n"
                "Попробуйте:\n"
                "• Увеличить радиус поиска\n"
                "• Выбрать другой город\n"
                "• Проверить позже",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            # Формируем сообщение с событиями
            events_text = format_events_message(events, city_name, radius)

            # Создаем клавиатуру для дополнительных действий
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"today_radius_{city_key}_{radius}"),
                        InlineKeyboardButton(text="🔙 Выбрать город", callback_data="today_back"),
                    ]
                ]
            )

            await callback.message.edit_text(events_text, reply_markup=keyboard, parse_mode="HTML")

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при поиске событий: {e}")
        await callback.answer("❌ Произошла ошибка при поиске", show_alert=True)


@router.callback_query(F.data == "today_back")
async def handle_back_to_cities(callback: types.CallbackQuery):
    """Обработчик кнопки 'Назад' - возврат к выбору города"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏙️ Москва", callback_data="today_city_moscow"),
                InlineKeyboardButton(text="🏛️ СПб", callback_data="today_city_spb"),
            ]
        ]
    )

    await callback.message.edit_text(
        "🌍 <b>События на сегодня</b>\n\n" "Выберите город для поиска событий:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    await callback.answer()


async def search_events_for_city(city_key: str, lat: float, lng: float, radius: int) -> list[dict[str, Any]]:
    """Ищет события для указанного города и радиуса"""

    all_events = []

    try:
        # Получаем источники для России
        ru_sources = get_sources_by_country("RU")

        if not ru_sources:
            logger.info("Нет включенных источников для России")
            return []

        # Ищем события в каждом источнике
        for source in ru_sources:
            try:
                logger.info(f"Ищем события в {source.display_name} для {city_key}")
                events = await source.fetch_events(lat, lng, radius)

                # Фильтруем события по гео-границам
                filtered_events = []
                for event in events:
                    event_lat = event.get("lat")
                    event_lng = event.get("lng")
                    country_code = event.get("country_code", "RU")

                    if event_lat and event_lng:
                        if is_allowed(event_lat, event_lng, country_code):
                            filtered_events.append(event)
                        else:
                            logger.debug(f"Событие {event.get('title', 'Unknown')} заблокировано гео-фильтром")
                    else:
                        # Если нет координат, пропускаем событие
                        logger.debug(f"Событие {event.get('title', 'Unknown')} без координат")

                all_events.extend(filtered_events)
                logger.info(f"Найдено {len(filtered_events)} событий в {source.display_name}")

            except Exception as e:
                logger.error(f"Ошибка при поиске в {source.display_name}: {e}")
                continue

        # Сортируем события по времени
        all_events.sort(key=lambda x: x.get("start_ts", 0))

        # Ограничиваем количество событий
        max_events = 20
        if len(all_events) > max_events:
            all_events = all_events[:max_events]

        logger.info(f"Всего найдено {len(all_events)} событий для {city_key}")
        return all_events

    except Exception as e:
        logger.error(f"Ошибка при поиске событий для {city_key}: {e}")
        return []


def format_events_message(events: list[dict[str, Any]], city_name: str, radius: int) -> str:
    """Форматирует сообщение со списком событий"""

    if not events:
        return f"😔 В {city_name} в радиусе {radius} км событий не найдено."

    # Заголовок
    message_parts = [f"🎉 <b>События в {city_name}</b>", f"📍 В радиусе {radius} км найдено: <b>{len(events)}</b>", ""]

    # События
    for i, event in enumerate(events, 1):
        title = event.get("title", "Без названия")
        venue = event.get("venue", {}).get("name", "")
        address = event.get("venue", {}).get("address", "")
        source_url = event.get("source_url", "")

        # Форматируем время
        start_ts = event.get("start_ts")
        time_str = ""
        if start_ts:
            from datetime import datetime

            try:
                dt = datetime.fromtimestamp(start_ts)
                time_str = f"🕐 {dt.strftime('%H:%M')}"
            except (ValueError, OSError):
                time_str = "🕐 Время уточняется"

        # Формируем строку события
        event_parts = [f"<b>{i}. {title}</b>"]

        if time_str:
            event_parts.append(time_str)

        if venue:
            event_parts.append(f"📍 {venue}")

        if address:
            event_parts.append(f"🏠 {address}")

        if source_url:
            event_parts.append(f"🔗 <a href='{source_url}'>Подробнее</a>")

        message_parts.append("\n".join(event_parts))
        message_parts.append("")  # Пустая строка между событиями

    return "\n".join(message_parts)


# Функция для регистрации роутера в основном боте
def register_today_handlers(dp):
    """Регистрирует обработчики команды /today в основном боте"""
    dp.include_router(router)
