#!/usr/bin/env python3
"""Админ-команды для Telegram Event Ingestion (тестовый/основной бот)."""

from __future__ import annotations

import html
import logging
import re

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import load_settings
from database import get_engine
from utils.telegram_sources_service import TRUST_LEVELS, TelegramSourcesService

logger = logging.getLogger(__name__)

telegram_ingest_router = Router()
telegram_ingest_router.message.filter(F.chat.type == "private")


class IngestAdminSetup(StatesGroup):
    waiting_source_target = State()


def _is_admin(user_id: int) -> bool:
    return user_id in load_settings().admin_ids


def _parse_source_line(line: str) -> tuple[str, str] | None:
    """@channel trusted | -100123 moderated | @channel (default moderated)."""
    raw = (line or "").strip()
    if not raw:
        return None
    parts = raw.split()
    if len(parts) >= 2 and parts[-1].lower() in TRUST_LEVELS:
        return parts[0], parts[-1].lower()
    if len(parts) == 1:
        return parts[0], "moderated"
    return None


def _parse_add_source_args(text: str) -> tuple[str, str] | None:
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    return _parse_source_line(parts[1])


def _add_source_usage_text() -> str:
    return (
        "Использование:\n"
        "• Нажми /add_source и отправь @username или chat_id\n"
        "• Или одной строкой: /add_source @channel trusted\n\n"
        "trust_level:\n"
        "• trusted — сразу open\n"
        "• moderated — draft + модерация (по умолчанию)\n\n"
        "Userbot (string session) должен быть участником канала/группы."
    )


async def _register_ingest_source(message: types.Message, bot, target: str, trust: str) -> None:
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
            "• или укажи chat_id: `-100123456789 moderated`\n"
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
        f"• chat_id: <code>{source.chat_id}</code>\n"
        f"• title: {html.escape(source.title or '—')}\n"
        f"• trust: {html.escape(source.trust_level or '—')}\n"
        f"• city: {html.escape(source.default_city or '—')} ({html.escape(source.timezone or '—')})\n\n"
        f"Userbot должен быть подписан на этот канал.",
        parse_mode="HTML",
    )


def _format_sources_list(sources) -> tuple[str, InlineKeyboardMarkup | None]:
    if not sources:
        return (
            "Список источников пуст. Добавь: <code>/add_source @channel moderated</code>",
            None,
        )
    lines = ["📡 <b>Telegram sources:</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for s in sources:
        status = "🟢" if s.is_active else "⚫"
        uname = f"@{s.username}" if s.username else "—"
        title = html.escape(s.title or "—")
        trust = html.escape(s.trust_level or "—")
        lines.append(f"{status} <code>{s.id}</code> | {title} | {html.escape(uname)} | {trust}")
        action = "off" if s.is_active else "on"
        label = "❌ Выкл" if s.is_active else "✅ Вкл"
        buttons.append([InlineKeyboardButton(text=f"{label} #{s.id}", callback_data=f"tgsrc:{action}:{s.id}")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


@telegram_ingest_router.message(Command("add_source"))
async def cmd_add_source(message: types.Message, bot, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Команда только для админов.")
        return

    parsed = _parse_add_source_args(message.text or "")
    if not parsed:
        await state.set_state(IngestAdminSetup.waiting_source_target)
        await message.answer(
            "📡 Введите @username или chat_id.\n\n"
            "Можно сразу указать trust:\n"
            "• `@channel moderated`\n"
            "• `-100123456789 trusted`\n\n"
            "По умолчанию: moderated\n"
            "Отмена: /cancel"
        )
        return

    target, trust = parsed
    await _register_ingest_source(message, bot, target, trust)


@telegram_ingest_router.message(IngestAdminSetup.waiting_source_target)
async def cmd_add_source_target_input(message: types.Message, bot, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear()
        await message.answer("⛔ Команда только для админов.")
        return

    text = (message.text or "").strip()
    if text.lower().startswith("/cancel"):
        await state.clear()
        await message.answer("Отменено.")
        return
    if text.startswith("/"):
        await state.clear()
        return

    parsed = _parse_source_line(text)
    if not parsed:
        await message.answer(_add_source_usage_text())
        return

    target, trust = parsed
    await state.clear()
    await _register_ingest_source(message, bot, target, trust)


@telegram_ingest_router.message(Command("list_sources"))
async def cmd_list_sources(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ Команда только для админов.")
        return

    engine = get_engine()
    service = TelegramSourcesService(engine)
    text, markup = _format_sources_list(service.list_sources())
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


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
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)


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

    days = stats["days"]
    lines = [f"📊 <b>Ingest stats ({days}d)</b>\n"]
    if not stats["by_stage"]:
        lines.append("Нет записей в telegram_ingest_log")
    else:
        lines.append("<b>Отсев по стадиям:</b>")
        for row in stats["by_stage"][:15]:
            stage = html.escape(str(row["stage"]))
            reason = html.escape(str(row["reason"]))
            lines.append(f"• {stage} / {reason}: {row['count']}")
    if stats["top_chats"]:
        lines.append("\n<b>Топ каналов:</b>")
        for row in stats["top_chats"]:
            title = html.escape(str(row["title"]))
            lines.append(f"• {title}: {row['count']}")
    await message.answer("\n".join(lines), parse_mode="HTML")


# Модерация ingest — callbacks в группе MODERATION_CHAT_ID (не только private)
telegram_ingest_mod_router = Router()


def _can_moderate_ingest(user_id: int, chat_id: int) -> bool:
    if user_id not in load_settings().admin_ids:
        return False
    mod_chat = load_settings().moderation_chat_id
    if mod_chat and chat_id != mod_chat:
        return False
    return True


@telegram_ingest_mod_router.callback_query(F.data.startswith("tgingest:"))
async def on_ingest_moderation(callback: types.CallbackQuery):
    if not callback.message or not callback.from_user:
        await callback.answer("Нет данных", show_alert=True)
        return

    if not _can_moderate_ingest(callback.from_user.id, callback.message.chat.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    m = re.match(r"tgingest:(approve|reject):(\d+)", callback.data or "")
    if not m:
        await callback.answer("Некорректные данные")
        return

    action, event_id_s = m.group(1), m.group(2)
    event_id = int(event_id_s)
    new_status = "open" if action == "approve" else "canceled"

    from utils.telegram_moderation_service import set_telegram_event_status

    engine = get_engine()
    ok = set_telegram_event_status(engine, event_id, new_status)
    if not ok:
        await callback.answer("Событие не найдено или уже обработано", show_alert=True)
        return

    label = "✅ Опубликовано" if action == "approve" else "❌ Отклонено"
    await callback.answer(label)

    base = callback.message.html_text or callback.message.text or ""
    if base:
        suffix = f"\n\n<b>{html.escape(label)}</b> · admin {callback.from_user.id}"
        try:
            await callback.message.edit_text(
                base + suffix,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            logger.exception("Failed to edit moderation card event_id=%s", event_id)
