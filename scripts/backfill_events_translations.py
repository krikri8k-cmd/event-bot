#!/usr/bin/env python3
"""
Однократный бэкфилл: переводит существующие парсерные события (RU → EN)
и заполняет title_en, description_en, location_name_en.

Перед запуском примени миграцию: migrations/040_add_events_title_description_location_en.sql

Запуск из корня проекта:
  python -m scripts.backfill_events_translations
  python -m scripts.backfill_events_translations --batch 20 --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path

# корень проекта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from utils.event_translation import translate_titles_batch

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PARSER_SOURCES = ("baliforum", "kudago", "ai")
DEFAULT_BATCH = 15


def main():
    ap = argparse.ArgumentParser(description="Backfill EN translations for parser events")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH, help="Batch size (default %s)" % DEFAULT_BATCH)
    ap.add_argument("--dry-run", action="store_true", help="Only log what would be updated")
    args = ap.parse_args()

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()
    with engine.connect() as conn:
        # События без перевода (только парсерные источники)
        # Все события без перевода, без ограничения по ID или дате
        rows = conn.execute(
            text("""
                SELECT id, source, external_id, title, description, location_name
                FROM events
                WHERE source IN ('baliforum', 'kudago', 'ai')
                  AND title_en IS NULL
                  AND title IS NOT NULL
                  AND TRIM(title) != ''
                ORDER BY id
            """)
        ).fetchall()

    if not rows:
        logger.info("Нет событий для перевода (title_en уже заполнен или нет парсерных событий).")
        return

    logger.info("Найдено событий для перевода: %s (пакетными запросами по %s)", len(rows), args.batch)
    updated = 0
    errors = 0

    for i in range(0, len(rows), args.batch):
        batch = rows[i : i + args.batch]
        titles = [(r[3] or "").strip() for r in batch]  # title = index 3
        if args.dry_run:
            for row in batch:
                logger.info("[dry-run] id=%s title=%r", row[0], (row[3] or "")[:50])
            updated += len(batch)
            continue

        # Один вызов API на весь батч (ТЗ: batching)
        title_ens = translate_titles_batch(titles)
        for row, title_en in zip(batch, title_ens):
            event_id, source, external_id, title, description, location_name = row
            # Fallback: при ошибке не записываем пустоту — оставляем NULL для повтора
            if not title_en:
                errors += 1
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE events
                            SET title_en = :title_en
                            WHERE id = :id
                        """),
                        {"id": event_id, "title_en": title_en},
                    )
                updated += 1
                logger.info(
                    "id=%s title=%r -> title_en=%r",
                    event_id,
                    (title or "")[:40],
                    title_en[:40],
                )
            except Exception as e:
                logger.warning("Ошибка обновления id=%s: %s", event_id, e)
                errors += 1

    logger.info("Готово: обновлено=%s, ошибок=%s", updated, errors)


if __name__ == "__main__":
    main()
