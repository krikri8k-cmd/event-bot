#!/usr/bin/env python3
"""
Скрипт для проверки корректности работы bot_status и bot_removed_at
"""

import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import load_settings


def check_bot_status():
    """Проверяет состояние bot_status и bot_removed_at"""
    print("🔍 Проверка работы bot_status и bot_removed_at\n")

    # Загружаем настройки
    settings = load_settings()
    if not settings.database_url:
        print("❌ DATABASE_URL не настроен")
        sys.exit(1)

    # Создаём engine
    print("📡 Подключение к базе данных...")
    try:
        engine = create_engine(settings.database_url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Подключение к БД успешно\n")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        sys.exit(1)

    with engine.connect() as conn:
        # Проверяем структуру таблицы
        print("📊 Структура таблицы chat_settings:")
        result = conn.execute(
            text("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'chat_settings'
            AND column_name IN ('bot_status', 'bot_removed_at')
            ORDER BY column_name
        """)
        )

        columns = result.fetchall()
        for col in columns:
            print(f"   {col[0]}: {col[1]} (nullable={col[2]}, default={col[3]})")

        print("\n📈 Текущее состояние:")

        # Статистика по статусам
        result = conn.execute(
            text("""
            SELECT 
                bot_status,
                COUNT(*) as count,
                COUNT(bot_removed_at) as with_removed_at
            FROM chat_settings
            GROUP BY bot_status
            ORDER BY bot_status
        """)
        )

        stats = result.fetchall()
        print("\nСтатистика по статусам:")
        for stat in stats:
            status = stat[0] or "NULL"
            count = stat[1]
            with_date = stat[2]
            print(f"   {status}: {count} чатов (из них {with_date} с bot_removed_at)")

        # Детальная информация
        result = conn.execute(
            text("""
            SELECT 
                chat_id,
                chat_number,
                bot_status,
                bot_removed_at,
                CASE 
                    WHEN bot_status = 'removed' AND bot_removed_at IS NULL THEN '⚠️ ОШИБКА: статус removed, но дата NULL'
                    WHEN bot_status = 'active' AND bot_removed_at IS NOT NULL THEN '⚠️ ОШИБКА: статус active, но дата установлена'
                    WHEN bot_status IS NULL THEN '⚠️ ОШИБКА: статус NULL'
                    ELSE '✅ OK'
                END as validation
            FROM chat_settings
            ORDER BY chat_number NULLS LAST
        """)
        )

        chats = result.fetchall()
        print("\n📋 Детальная информация по чатам:")
        errors_found = False
        for chat in chats:
            chat_id = chat[0]
            chat_number = chat[1] or "NULL"
            status = chat[2] or "NULL"
            removed_at = chat[3]
            validation = chat[4]

            if "⚠️ ОШИБКА" in validation:
                errors_found = True
                print(f"   ❌ Chat {chat_number} (ID: {chat_id}): {validation}")
                print(f"      Статус: {status}, bot_removed_at: {removed_at}")
            else:
                print(f"   ✅ Chat {chat_number} (ID: {chat_id}): статус={status}, removed_at={removed_at}")

        if errors_found:
            print("\n⚠️ Найдены проблемы с согласованностью данных!")
            print("   Рекомендуется запустить скрипт исправления.")
        else:
            print("\n✅ Все данные согласованы!")

        # Проверяем наличие индексов
        print("\n🔍 Проверка индексов:")
        result = conn.execute(
            text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'chat_settings'
            AND indexname LIKE '%bot_status%'
        """)
        )

        indexes = result.fetchall()
        if indexes:
            for idx in indexes:
                print(f"   ✅ {idx[0]}")
        else:
            print("   ⚠️ Индекс для bot_status не найден")


if __name__ == "__main__":
    check_bot_status()
