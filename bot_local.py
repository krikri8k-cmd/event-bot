#!/usr/bin/env python3
"""
Локальная версия EventBot для тестирования без базы данных
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Location

from config import load_settings

logging.basicConfig(level=logging.INFO)


class CreateEventFSM(StatesGroup):
    title = State()
    time_local = State()
    location = State()
    description = State()
    max_participants = State()
    preview = State()


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Что рядом", request_location=False)],
            [KeyboardButton(text="➕ Создать")],
            [KeyboardButton(text="🤝 Поделиться")],
        ],
        resize_keyboard=True,
    )


async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я EventAroundBot. Помогаю находить события рядом и создавать свои. 🎉\n\n"
        "Это локальная версия для тестирования - база данных недоступна.",
        reply_markup=main_menu_kb(),
    )


async def ask_location(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить геопозицию", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Отправь свежую геопозицию, чтобы я нашла события рядом ✨", reply_markup=kb)


async def on_what_nearby(message: Message):
    await ask_location(message)


async def on_location(message: Message):
    if not message.location:
        await ask_location(message)
        return
    
    lat = message.location.latitude
    lng = message.location.longitude
    
    await message.answer(
        f"📍 Получил твою геопозицию!\n"
        f"Координаты: {lat:.6f}, {lng:.6f}\n\n"
        f"🔍 Ищу события рядом...\n\n"
        f"⚠️ Это тестовая версия - база данных недоступна.\n"
        f"В продакшене здесь будут показаны реальные события!",
        reply_markup=main_menu_kb(),
    )


async def on_create(message: Message, state: FSMContext):
    await state.set_state(CreateEventFSM.title)
    await message.answer(
        "Создаём новое событие! 🎉\n\n"
        "Как называется твоё событие?",
        reply_markup=ReplyKeyboardRemove(),
    )


async def fsm_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(CreateEventFSM.time_local)
    await message.answer(
        f"Отлично! Событие: {message.text}\n\n"
        f"Когда оно состоится? (например: 25.12.2024 19:00)",
    )


async def fsm_time_local(message: Message, state: FSMContext):
    await state.update_data(time_local=message.text)
    await state.set_state(CreateEventFSM.location)
    await message.answer(
        f"Время: {message.text}\n\n"
        f"Где будет проходить событие? (адрес или название места)",
    )


async def fsm_location(message: Message, state: FSMContext):
    await state.update_data(location=message.text)
    await state.set_state(CreateEventFSM.description)
    await message.answer(
        f"Место: {message.text}\n\n"
        f"Расскажи подробнее о событии (описание)",
    )


async def fsm_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(CreateEventFSM.max_participants)
    await message.answer(
        f"Описание: {message.text[:50]}...\n\n"
        f"Сколько человек может участвовать? (число или 'неограниченно')",
    )


async def fsm_max(message: Message, state: FSMContext):
    await state.update_data(max_participants=message.text)
    await state.set_state(CreateEventFSM.preview)
    
    data = await state.get_data()
    
    preview_text = f"""
🎉 ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР СОБЫТИЯ:

📝 Название: {data.get('title', 'Не указано')}
🕐 Время: {data.get('time_local', 'Не указано')}
📍 Место: {data.get('location', 'Не указано')}
📖 Описание: {data.get('description', 'Не указано')}
👥 Максимум участников: {data.get('max_participants', 'Не указано')}

⚠️ Это тестовая версия - событие не будет сохранено в базе данных.

Хочешь создать событие? (да/нет)
"""
    
    await message.answer(preview_text)


async def on_share(message: Message):
    await message.answer(
        "🤝 Функция 'Поделиться' пока недоступна в тестовой версии.\n\n"
        "В продакшене здесь можно будет делиться событиями с друзьями!",
        reply_markup=main_menu_kb(),
    )


async def cmd_admin(message: Message):
    await message.answer(
        "👑 Админ-панель недоступна в тестовой версии.\n\n"
        "В продакшене здесь будут административные функции!",
        reply_markup=main_menu_kb(),
    )


def make_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(on_what_nearby, F.text == "📍 Что рядом")
    dp.message.register(on_create, F.text == "➕ Создать")
    dp.message.register(on_share, F.text == "🤝 Поделиться")
    dp.message.register(on_location, F.location)
    dp.message.register(cmd_admin, Command("admin"))

    dp.message.register(fsm_title, CreateEventFSM.title)
    dp.message.register(fsm_time_local, CreateEventFSM.time_local)
    dp.message.register(fsm_location, CreateEventFSM.location)
    dp.message.register(fsm_description, CreateEventFSM.description)
    dp.message.register(fsm_max, CreateEventFSM.max_participants)
    
    return dp


async def run() -> None:
    settings = load_settings()
    bot = Bot(token=settings.telegram_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = make_dispatcher()
    
    print("🚀 Запуск локальной версии EventBot...")
    print("⚠️  База данных недоступна - это тестовая версия")
    print("📱 Бот готов к работе!")
    
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(run())

