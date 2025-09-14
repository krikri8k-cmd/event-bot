#!/usr/bin/env python3
"""
Анализ структуры базы данных
"""

import asyncio
import logging

from sqlalchemy import inspect, text

from config import load_settings
from database import get_engine, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def analyze_db_structure():
    """Анализируем структуру БД"""
    print("🗄️ АНАЛИЗ СТРУКТУРЫ БАЗЫ ДАННЫХ")
    print("=" * 60)

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    inspector = inspect(engine)

    print("📊 ТАБЛИЦЫ В БАЗЕ ДАННЫХ:")
    print("-" * 40)

    # Получаем все таблицы
    tables = inspector.get_table_names()
    views = inspector.get_view_names()

    print(f"📋 Всего таблиц: {len(tables)}")
    print(f"👁️ Всего VIEW: {len(views)}")
    print()

    # Анализируем каждую таблицу
    for table_name in sorted(tables):
        print(f"🗂️ ТАБЛИЦА: {table_name.upper()}")
        print("-" * 30)

        try:
            # Получаем колонки
            columns = inspector.get_columns(table_name)

            print(f"📝 Колонки ({len(columns)}):")
            for col in columns:
                nullable = "NULL" if col["nullable"] else "NOT NULL"
                default = f" DEFAULT {col['default']}" if col["default"] else ""
                print(f"   • {col['name']}: {col['type']} {nullable}{default}")

            # Получаем индексы
            indexes = inspector.get_indexes(table_name)
            if indexes:
                print(f"🔍 Индексы ({len(indexes)}):")
                for idx in indexes:
                    cols = ", ".join(idx["column_names"])
                    unique = " UNIQUE" if idx["unique"] else ""
                    print(f"   • {idx['name']}: ({cols}){unique}")

            # Получаем внешние ключи
            foreign_keys = inspector.get_foreign_keys(table_name)
            if foreign_keys:
                print(f"🔗 Внешние ключи ({len(foreign_keys)}):")
                for fk in foreign_keys:
                    ref_table = fk["referred_table"]
                    ref_cols = ", ".join(fk["referred_columns"])
                    cols = ", ".join(fk["constrained_columns"])
                    print(f"   • {cols} → {ref_table}({ref_cols})")

            # Получаем статистику
            with engine.connect() as conn:
                count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).fetchone()
                count = count_result[0] if count_result else 0
                print(f"📊 Записей: {count}")

            print()

        except Exception as e:
            print(f"❌ Ошибка при анализе таблицы {table_name}: {e}")
            print()

    # Анализируем VIEW
    if views:
        print("👁️ VIEW В БАЗЕ ДАННЫХ:")
        print("-" * 40)

        for view_name in sorted(views):
            print(f"🔍 VIEW: {view_name.upper()}")
            print("-" * 20)

            try:
                # Получаем колонки VIEW
                columns = inspector.get_columns(view_name)

                print(f"📝 Колонки ({len(columns)}):")
                for col in columns:
                    print(f"   • {col['name']}: {col['type']}")

                # Получаем статистику
                with engine.connect() as conn:
                    count_result = conn.execute(text(f"SELECT COUNT(*) FROM {view_name}")).fetchone()
                    count = count_result[0] if count_result else 0
                    print(f"📊 Записей: {count}")

                print()

            except Exception as e:
                print(f"❌ Ошибка при анализе VIEW {view_name}: {e}")
                print()

    # Анализируем связи между таблицами
    print("🔗 СВЯЗИ МЕЖДУ ТАБЛИЦАМИ:")
    print("-" * 40)

    for table_name in sorted(tables):
        foreign_keys = inspector.get_foreign_keys(table_name)
        if foreign_keys:
            print(f"📋 {table_name}:")
            for fk in foreign_keys:
                ref_table = fk["referred_table"]
                print(f"   → {ref_table}")

    print()

    # Функциональное описание
    print("🎯 ФУНКЦИОНАЛЬНОЕ ОПИСАНИЕ ТАБЛИЦ:")
    print("-" * 40)

    functional_descriptions = {
        "users": {
            "purpose": "Пользователи Telegram бота",
            "key_fields": "id, username, full_name, user_tz, last_lat, last_lng",
            "functionality": "Хранение профилей пользователей, геолокации, настроек радиуса",
        },
        "events": {
            "purpose": "Объединенная таблица всех событий",
            "key_fields": "id, title, starts_at, lat, lng, source",
            "functionality": "Единая точка доступа ко всем событиям (пользовательские + парсерные)",
        },
        "events_user": {
            "purpose": "События созданные пользователями",
            "key_fields": "id, title, starts_at, lat, lng, organizer_id",
            "functionality": "Хранение событий созданных через бота пользователями",
        },
        "events_parser": {
            "purpose": "События полученные парсерами",
            "key_fields": "id, title, starts_at, lat, lng, source, external_id",
            "functionality": "Хранение событий из внешних источников (BaliForum, KudaGo, Meetup)",
        },
        "moments": {
            "purpose": "Моментальные события (краткосрочные)",
            "key_fields": "id, title, expires_at, lat, lng, creator_id",
            "functionality": "Временные события с TTL, исчезают автоматически",
        },
    }

    for table_name, desc in functional_descriptions.items():
        if table_name in tables:
            print(f"📋 {table_name.upper()}:")
            print(f"   🎯 Назначение: {desc['purpose']}")
            print(f"   🔑 Ключевые поля: {desc['key_fields']}")
            print(f"   ⚙️ Функционал: {desc['functionality']}")
            print()

    # VIEW функциональность
    print("👁️ ФУНКЦИОНАЛЬНОСТЬ VIEW:")
    print("-" * 40)

    view_descriptions = {
        "events_all_bali": "Объединяет события пользователей и парсера для Бали",
        "events_all_msk": "Объединяет события пользователей и парсера для Москвы",
        "events_all_spb": "Объединяет события пользователей и парсера для СПб",
    }

    for view_name, desc in view_descriptions.items():
        if view_name in views:
            print(f"🔍 {view_name.upper()}:")
            print(f"   📝 Описание: {desc}")
            print()


async def main():
    """Основная функция"""
    try:
        await analyze_db_structure()
        return True
    except Exception as e:
        logger.error(f"Ошибка анализа: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
