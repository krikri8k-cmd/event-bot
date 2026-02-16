#!/usr/bin/env python3
"""
Аудит БД: статистика по title_en (сколько событий без перевода, по источникам).
Без изменения кода/данных. Запуск: python -m scripts.audit_title_en
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main():
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) AS c FROM events")).scalar()
        missing = conn.execute(
            text("SELECT COUNT(*) AS c FROM events WHERE title_en IS NULL OR title_en = ''")
        ).scalar()
        with_en = conn.execute(
            text("SELECT COUNT(*) AS c FROM events WHERE title_en IS NOT NULL AND title_en != ''")
        ).scalar()

        rows = conn.execute(
            text("""
                SELECT source,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE title_en IS NULL OR title_en = '') AS missing_en
                FROM events
                GROUP BY source
            """)
        ).fetchall()

    # Отчёт (ASCII для консоли Windows)
    logger.info("=" * 60)
    logger.info("AUDIT: title_en in events table")
    logger.info("=" * 60)
    logger.info("Total events:     %s", total)
    logger.info("Missing EN (NULL): %s", missing)
    logger.info("With EN:           %s", with_en)
    logger.info("By source:")
    logger.info("-" * 60)
    for r in rows:
        src, tot, miss = r[0], r[1], r[2]
        logger.info("  %s  total=%s  missing_en=%s", (src or "(NULL)"), tot, miss)
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
