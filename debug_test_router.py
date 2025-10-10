#!/usr/bin/env python3
"""
Временный роутер для диагностики проблем с удалением сообщений
"""

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import Message

diag_router = Router()
diag_router.message.filter(F.chat.type.in_({"group", "supergroup"}))


@diag_router.message(Command("__deltest"))
async def __deltest(m: Message, bot: Bot):
    """Быстрый тест удаления сообщений"""
    chat_id = m.chat.id
    bot_id = (await bot.get_me()).id

    # 1) Проверяем права бота
    try:
        member = await bot.get_chat_member(chat_id, bot_id)
        status = member.status
        can_delete = getattr(member, "can_delete_messages", None)
        await m.reply(f"🔍 Права бота:\nstatus={status}\ncan_delete_messages={can_delete}")
    except Exception as e:
        await m.reply(f"❌ Ошибка проверки прав: {e}")
        return

    # 2) Отправляем тестовое сообщение и пытаемся его удалить
    try:
        test_msg = await bot.send_message(chat_id, "🧪 ТЕСТ УДАЛЕНИЯ - это сообщение должно исчезнуть")
        await m.reply(f"✅ Тестовое сообщение отправлено, ID: {test_msg.message_id}")

        # Ждем немного и удаляем
        import asyncio

        await asyncio.sleep(2)

        try:
            await bot.delete_message(chat_id, test_msg.message_id)
            await m.reply("✅ delete_message() сработал на свежем сообщении!")
        except TelegramForbiddenError as e:
            await m.reply(f"⛔ Нет прав на удаление: {e}")
        except TelegramBadRequest as e:
            await m.reply(f"⚠️ BadRequest при удалении: {e}")
        except Exception as e:
            await m.reply(f"❗ Неожиданная ошибка при удалении: {e}")

    except Exception as e:
        await m.reply(f"❌ Ошибка отправки тестового сообщения: {e}")


@diag_router.message(Command("__checkdb"))
async def __checkdb(m: Message):
    """Проверяем что в БД для этого чата"""
    chat_id = m.chat.id

    try:
        from database import BotMessage, get_async_session

        session = await get_async_session()
        messages = (
            session.query(BotMessage)
            .filter(BotMessage.chat_id == chat_id)
            .order_by(BotMessage.created_at.desc())
            .limit(10)
            .all()
        )

        if not messages:
            await m.reply("❌ В bot_messages нет записей для этого чата!\nЭто означает что сообщения не трекаются.")
            return

        result = f"📊 Найдено {len(messages)} записей в bot_messages:\n\n"

        for msg in messages:
            status = "🗑️ удалено" if msg.deleted else "✅ активно"
            result += f"ID: {msg.message_id}, Tag: {msg.tag}, Status: {status}\n"

        active_count = len([m for m in messages if not m.deleted])
        result += f"\nАктивных: {active_count}, Удаленных: {len(messages) - active_count}"

        await m.reply(result)

    except Exception as e:
        await m.reply(f"❌ Ошибка проверки БД: {e}")


@diag_router.message(Command("__tracktest"))
async def __tracktest(m: Message, bot: Bot):
    """Тестируем трекинг сообщений"""
    chat_id = m.chat.id

    try:
        from database import get_async_session
        from utils.messaging_utils import send_tracked

        session = await get_async_session()
        # Отправляем сообщение через send_tracked
        tracked_msg = await send_tracked(
            bot,
            session,
            chat_id=chat_id,
            text="🧪 ТЕСТ ТРЕКИНГА - это сообщение должно быть записано в БД",
            tag="test",
        )

        await m.reply(f"✅ Сообщение отправлено через send_tracked, ID: {tracked_msg.message_id}")

        # Проверяем что записалось в БД
        from database import BotMessage

        db_msg = session.query(BotMessage).filter(BotMessage.message_id == tracked_msg.message_id).first()

        if db_msg:
            await m.reply(
                f"✅ Сообщение записалось в БД:\n"
                f"chat_id: {db_msg.chat_id}\n"
                f"tag: {db_msg.tag}\n"
                f"deleted: {db_msg.deleted}"
            )
        else:
            await m.reply("❌ Сообщение НЕ записалось в БД!")

    except Exception as e:
        await m.reply(f"❌ Ошибка тестирования трекинга: {e}")
