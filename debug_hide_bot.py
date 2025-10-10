#!/usr/bin/env python3
"""
Скрипт для диагностики проблем с функцией "Спрятать бота"
"""

import logging

from sqlalchemy import create_engine, text

from config import load_settings
from database import BotMessage, get_session

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_bot_messages(chat_id: int):
    """Проверяет что записано в bot_messages для чата"""
    print(f"\n🔍 Проверяем bot_messages для чата {chat_id}:")

    with get_session() as session:
        messages = (
            session.query(BotMessage)
            .filter(BotMessage.chat_id == chat_id)
            .order_by(BotMessage.created_at.desc())
            .limit(10)
            .all()
        )

        if not messages:
            print("❌ В таблице bot_messages нет записей для этого чата!")
            print("   Это означает что сообщения бота не трекаются.")
            return False

        print(f"✅ Найдено {len(messages)} записей:")
        for msg in messages:
            status = "🗑️ удалено" if msg.deleted else "✅ активно"
            print(f"   ID: {msg.message_id}, Tag: {msg.tag}, Status: {status}, Created: {msg.created_at}")

        active_count = len([m for m in messages if not m.deleted])
        print("\n📊 Статистика:")
        print(f"   Всего записей: {len(messages)}")
        print(f"   Активных (не удаленных): {active_count}")
        print(f"   Удаленных: {len(messages) - active_count}")

        return active_count > 0


def check_database_structure():
    """Проверяет структуру таблицы bot_messages"""
    print("\n🔍 Проверяем структуру таблицы bot_messages:")

    settings = load_settings()
    engine = create_engine(settings.database_url)

    with engine.connect() as conn:
        # Проверяем существование таблицы
        result = conn.execute(
            text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'bot_messages'
            );
        """)
        )
        exists = result.fetchone()[0]

        if not exists:
            print("❌ Таблица bot_messages не существует!")
            return False

        print("✅ Таблица bot_messages существует")

        # Проверяем структуру
        result = conn.execute(
            text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'bot_messages'
            ORDER BY ordinal_position;
        """)
        )

        print("📋 Структура таблицы:")
        for row in result:
            print(f"   {row[0]}: {row[1]} ({'NULL' if row[2] == 'YES' else 'NOT NULL'})")

        return True


async def simulate_hide_bot(chat_id: int):
    """Симулирует процесс скрытия бота"""
    print(f"\n🎭 Симуляция скрытия бота для чата {chat_id}:")

    from aiogram import Bot

    from utils.messaging_utils import delete_all_tracked

    # Создаем фиктивный бот для тестирования
    bot = Bot(token="dummy")  # Токен не нужен для этого теста

    with get_session() as session:
        try:
            deleted_count = await delete_all_tracked(bot, session, chat_id=chat_id)
            print(f"✅ Симуляция завершена. Удалено: {deleted_count} сообщений")
        except Exception as e:
            print(f"❌ Ошибка симуляции: {e}")


def main():
    """Главная функция диагностики"""
    print("🔧 Диагностика функции 'Спрятать бота'")
    print("=" * 50)

    # Проверяем структуру БД
    if not check_database_structure():
        print("\n❌ Проблемы с базой данных. Проверьте миграции.")
        return

    # Запрашиваем ID чата для проверки
    try:
        chat_id = int(input("\n📝 Введите ID группового чата для проверки: "))
    except ValueError:
        print("❌ Неверный ID чата")
        return

    # Проверяем записи в bot_messages
    has_messages = check_bot_messages(chat_id)

    if has_messages:
        print("\n✅ Диагностика завершена. Сообщения трекаются корректно.")
        print("\n💡 Рекомендации:")
        print("1. Убедитесь что бот - администратор группы")
        print("2. Убедитесь что у бота есть право 'Удаление сообщений'")
        print("3. Проверьте логи на ошибки TelegramForbiddenError")
    else:
        print("\n❌ Проблема найдена: сообщения бота не трекаются!")
        print("\n💡 Решения:")
        print("1. Проверьте что все отправки идут через send_tracked()")
        print("2. Убедитесь что ensure_panel() вызывается с await")
        print("3. Проверьте что в group_router используются правильные функции")


if __name__ == "__main__":
    main()
