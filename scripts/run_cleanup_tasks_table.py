#!/usr/bin/env python3
"""
Применяет миграцию 042: удаление таблицы tasks и колонки user_tasks.task_id.
Выводит в консоль: [CLEANUP] Таблица tasks и связанные записи удалены.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main():
    from sqlalchemy import text

    from config import load_settings
    from database import get_engine, init_engine

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()
    if not engine:
        logger.error("Database engine not available")
        return 1

    with engine.begin() as conn:
        try:
            r = conn.execute(text("DELETE FROM user_tasks WHERE task_id IS NOT NULL"))
            _ = r.rowcount
        except Exception as e:
            logger.debug("DELETE (column may already be dropped): %s", e)
        try:
            conn.execute(text("ALTER TABLE user_tasks DROP CONSTRAINT IF EXISTS user_tasks_task_id_fkey"))
        except Exception as e:
            logger.debug("Drop constraint: %s", e)
        try:
            conn.execute(text("ALTER TABLE user_tasks DROP COLUMN IF EXISTS task_id"))
        except Exception as e:
            logger.debug("Drop column: %s", e)
        try:
            conn.execute(text("DROP TABLE IF EXISTS tasks"))
        except Exception as e:
            logger.warning("Drop table: %s", e)

    logger.info("[CLEANUP] Таблица tasks и связанные записи удалены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
