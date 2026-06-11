#!/usr/bin/env python3
"""Админ-команды для Telegram Event Ingestion (тестовый/основной бот)."""

from __future__ import annotations

import logging
import re

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import load_settings
from database import get_engine
from utils.telegram_sources_service import TRUST_LEVELS, TelegramSourcesService

logger = logging.getLogger(__name__)

telegram_ingest_router = Router()
telegram_ingest_router.message.filter(F.chat.type == "private")


def _is_admin(user_id: int) -> bool:
    return user_id in load_settings().admin_ids


def _parse_add_source_args(text: str) -> tuple[str, str] | None:
    parts = (text or "").split(maxsplit=2)
    if len(parts) < 2:
        return None
    target = parts[1].strip()
    trust = (parts[2].strip().lower() if len(parts) > 2 else "moderated") or "moderated"
    if trust not in TRUST_LEVELS:
        return None
    return target, trust


@telegram_ingest_router.message(Command("add_source"))
async def cmd_add_source(message: types.Message, bot):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Команда только для админов.")
        return

    parsed = _parse_add_source_args(message.text or "")
    if not parsed:
        await message.answer(
            "Использование:\n"
            "/add_source @channel_username trusted\n"
            "/add_source -100123456789 moderated\n\n"
            "trust_level:\n"
            "• trusted — сразу open\n"
            "• moderated — draft + модерация\n\n"
            "Userbot (string session) должен быть участником канала/группы.\n"
            "Бот MyConductor в группе не обязателен, если указываешь chat_id."
        )
        return

    target, trust = parsed
    chat_id: int
    username: str | None = None
    title: str

    try:
        if target.lstrip("-").isdigit():
            chat_id = int(target)
            try:
                chat = await bot.get_chat(chat_id)
                username = getattr(chat, "username", None)
                title = getattr(chat, "title", None) or username or str(chat_id)
            except Exception as e:
                logger.info(
                    "add_source: get_chat(%s) недоступен (%s), регистрируем по chat_id",
                    chat_id,
                    e,
                )
                title = f"Chat {chat_id}"
        else:
            username = target if target.startswith("@") else f"@{target}"
            chat = await bot.get_chat(username)
            chat_id = chat.id
            username = getattr(chat, "username", None) or username.lstrip("@")
            title = getattr(chat, "title", None) or username or str(chat_id)
    except Exception as e:
        logger.warning("add_source: cannot resolve chat %s: %s", target, e)
        await message.answer(
            "Не удалось получить чат по @username.\n\n"
            "Проверь:\n"
            "• канал публичный и username верный\n"
            "• или укажи chat_id: /add_source -100123456789 moderated\n"
            "• userbot подписан на источник\n\n"
            f"Ошибка: {e}"
        )
        return

    engine = get_engine()
    service = TelegramSourcesService(engine)
    source = service.upsert_source(
        chat_id=chat_id,
        title=title,
        username=username,
        trust_level=trust,
    )

    await message.answer(
        f"✅ Источник добавлен\n"
        f"• ID: {source.id}\n"
        f"• chat_id: `{source.chat_id}`\n"
        f"• title: {source.title}\n"
        f"• trust: {source.trust_level}\n"
        f"• city: {source.default_city} ({source.timezone})\n\n"
        f"Userbot должен быть подписан на этот канал.",
        parse_mode="Markdown",
    )


def _format_sources_list(sources) -> tuple[str, InlineKeyboardMarkup | None]:
    if not sources:
        return (
            "Список источников пуст. Добавь: `/add_source @channel moderated`",
            None,
        )
    lines = ["📡 **Telegram sources:**\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for s in sources:
        status = "🟢" if s.is_active else "⚫"
        uname = f"@{s.username}" if s.username else "—"
        lines.append(f"{status} `{s.id}` | {s.title} | {uname} | {s.trust_level}")
        action = "off" if s.is_active else "on"
        label = "❌ Выкл" if s.is_active else "✅ Вкл"
        buttons.append([InlineKeyboardButton(text=f"{label} #{s.id}", callback_data=f"tgsrc:{action}:{s.id}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@telegram_ingest_router.message(Command("list_sources"))
async def cmd_list_sources(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Команда только для админов.")
        return

    engine = get_engine()
    service = TelegramSourcesService(engine)
    text, markup = _format_sources_list(service.list_sources())
    await message.answer(text, parse_mode="Markdown", reply_markup=markup)


@telegram_ingest_router.callback_query(F.data.startswith("tgsrc:"))
async def on_toggle_source(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    m = re.match(r"tgsrc:(on|off):(\d+)", callback.data or "")
    if not m:
        await callback.answer("Некорректные данные")
        return

    source_id = int(m.group(2))
    is_active = m.group(1) == "on"
    engine = get_engine()
    service = TelegramSourcesService(engine)
    ok = service.set_active(source_id, is_active)
    await callback.answer("Обновлено" if ok else "Не найдено", show_alert=not ok)
    if ok and callback.message:
        text, markup = _format_sources_list(service.list_sources())
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=markup)


@telegram_ingest_router.message(Command("ingest_stats"))
async def cmd_ingest_stats(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Команда только для админов.")
        return

    engine = get_engine()
    service = TelegramSourcesService(engine)
    try:
        stats = service.ingest_stats(days=7)
    except Exception as e:
        logger.exception("ingest_stats failed: %s", e)
        await message.answer(
            "Таблицы telegram_ingest ещё не созданы. Примени миграцию "
            "`migrations/050_create_telegram_ingest_tables.sql` на develop БД."
        )
        return

    lines = [f"📊 **Ingest stats ({stats['days']}d)**\n"]
    if not stats["by_stage"]:
        lines.append("_Нет записей в telegram_ingest_log_")
    else:
        lines.append("**Отсев по стадиям:**")
        for row in stats["by_stage"][:15]:
            lines.append(f"• {row['stage']} / {row['reason']}: {row['count']}")
    if stats["top_chats"]:
        lines.append("\n**Топ каналов:**")
        for row in stats["top_chats"]:
            lines.append(f"• {row['title']}: {row['count']}")
    await message.answer("\n".join(lines), parse_mode="Markdown")
