#!/usr/bin/env python3
"""
Pre-check + применение migrations/053_drop_task_templates.sql
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MIGRATION_SQL = ROOT / "migrations" / "053_drop_task_templates.sql"


def main() -> int:
    from pre_check_drop_task_templates import run_pre_check
    from sqlalchemy import text

    from config import load_settings
    from database import get_engine, init_engine

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL")
    settings = load_settings()
    init_engine(db_url or settings.database_url)
    engine = get_engine()
    if not engine:
        logger.error("❌ Database engine not available")
        return 2

    with engine.connect() as conn:
        ok, issues = run_pre_check(conn)
        if not ok:
            logger.error("❌ Pre-check не пройден, миграция не применена")
            for issue in issues:
                logger.error("   • %s", issue)
            return 1

    if not MIGRATION_SQL.exists():
        logger.error("❌ Файл миграции не найден: %s", MIGRATION_SQL)
        return 2

    sql = MIGRATION_SQL.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))

    logger.info("[CLEANUP] task_templates и связанные legacy-ссылки удалены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
