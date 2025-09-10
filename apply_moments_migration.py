#!/usr/bin/env python3
"""
Скрипт для применения миграции moments schema fix
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy import text

# Добавляем корневую папку проекта в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Импорты после добавления пути
from config import load_settings  # noqa: E402
from database import get_engine, init_engine  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def apply_migration():
    """Применяет миграцию moments schema fix"""
    try:
        # Читаем SQL миграцию
        migration_file = project_root / "migrations" / "003_moments_schema_fix.sql"

        if not migration_file.exists():
            logger.error(f"❌ Файл миграции не найден: {migration_file}")
            return False

        with open(migration_file, encoding="utf-8") as f:
            migration_sql = f.read()

        logger.info("📄 Читаем миграцию moments schema fix...")

        # Инициализируем и подключаемся к БД
        settings = load_settings()
        init_engine(settings.database_url)
        engine = get_engine()

        with engine.connect() as conn:
            # Выполняем миграцию
            logger.info("🔧 Применяем миграцию moments schema fix...")
            conn.execute(text(migration_sql))
            conn.commit()

        logger.info("✅ Миграция moments schema fix успешно применена!")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка применения миграции: {e}")
        return False


def check_moments_table():
    """Проверяет структуру таблицы moments"""
    try:
        settings = load_settings()
        init_engine(settings.database_url)
        engine = get_engine()

        with engine.connect() as conn:
            # Проверяем существование таблицы
            result = conn.execute(
                text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'moments'
                );
            """)
            )

            table_exists = result.scalar()

            if not table_exists:
                logger.warning("⚠️ Таблица moments не существует")
                return False

            # Проверяем структуру таблицы
            result = conn.execute(
                text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'moments'
                ORDER BY ordinal_position;
            """)
            )

            columns = result.fetchall()

            logger.info("📋 Структура таблицы moments:")
            for col in columns:
                logger.info(
                    f"  - {col[0]}: {col[1]} {'NULL' if col[2] == 'YES' else 'NOT NULL'} {f'DEFAULT {col[3]}' if col[3] else ''}"
                )

            # Проверяем индексы
            result = conn.execute(
                text("""
                SELECT indexname, indexdef
                FROM pg_indexes 
                WHERE tablename = 'moments'
                ORDER BY indexname;
            """)
            )

            indexes = result.fetchall()

            logger.info("🔍 Индексы таблицы moments:")
            for idx in indexes:
                logger.info(f"  - {idx[0]}")

            return True

    except Exception as e:
        logger.error(f"❌ Ошибка проверки таблицы moments: {e}")
        return False


if __name__ == "__main__":
    logger.info("🚀 Запуск применения миграции moments schema fix...")

    # Применяем миграцию
    if apply_migration():
        logger.info("✅ Миграция применена успешно!")

        # Проверяем результат
        logger.info("🔍 Проверяем структуру таблицы...")
        check_moments_table()

    else:
        logger.error("❌ Не удалось применить миграцию")
        sys.exit(1)
