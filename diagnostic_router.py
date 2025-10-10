"""
Диагностические команды для тестирования трекинга сообщений
"""

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import BotMessage
from utils.messaging_utils import delete_all_tracked, ensure_panel, send_tracked

diag = Router()
diag.message.filter(F.chat.type.in_({"group", "supergroup"}))
diag.callback_query.filter(F.message.chat.type.in_({"group", "supergroup"}))


@diag.message(Command("__seedpanel"))
async def __seedpanel(m: Message, bot: Bot, session: AsyncSession):
    """1) Создаём/редактируем ПАНЕЛЬ (и она обязательно попадёт в bot_messages)"""
    await ensure_panel(bot, session, chat_id=m.chat.id, text="Панель для теста", kb=None)
    await m.reply("✅ Панель создана/обновлена (записана в bot_messages).")


@diag.message(Command("__checkdb"))
async def __checkdb(m: Message, session: AsyncSession):
    """2) Проверяем, что в bot_messages есть записи для этого чата"""
    rows = (
        await session.execute(
            select(BotMessage.message_id, BotMessage.tag, BotMessage.deleted)
            .where(BotMessage.chat_id == m.chat.id)
            .order_by(BotMessage.id.desc())
            .limit(10)
        )
    ).all()

    if not rows:
        await m.reply("⚠️ В bot_messages нет ни одной записи для этого чата.")
    else:
        lines = [f"{mid} | {tag} | deleted={deleted}" for (mid, tag, deleted) in rows]
        await m.reply("Последние записи bot_messages:\n" + "\n".join(lines))


@diag.message(Command("__wipe"))
async def __wipe(m: Message, bot: Bot, session: AsyncSession):
    """3) Жёстко проверяем удаление (без кнопки)"""
    cnt = await delete_all_tracked(bot, session, chat_id=m.chat.id)
    await m.reply(f"🧹 Удалено сообщений: {cnt}")


@diag.message(Command("__tracktest"))
async def __tracktest(m: Message, bot: Bot, session: AsyncSession):
    """Тестируем отправку через send_tracked"""
    tracked_msg = await send_tracked(
        bot,
        session,
        chat_id=m.chat.id,
        text="🧪 ТЕСТ ТРЕКИНГА - это сообщение должно быть записано в БД",
        tag="test",
    )

    await m.reply(f"✅ Сообщение отправлено через send_tracked, ID: {tracked_msg.message_id}")

    # Проверяем что записалось в БД
    db_msg = (
        await session.execute(select(BotMessage).where(BotMessage.message_id == tracked_msg.message_id))
    ).scalar_one_or_none()

    if db_msg:
        await m.reply(
            f"✅ Сообщение записалось в БД:\n"
            f"chat_id: {db_msg.chat_id}\n"
            f"tag: {db_msg.tag}\n"
            f"deleted: {db_msg.deleted}"
        )
    else:
        await m.reply("❌ Сообщение НЕ записалось в БД!")
