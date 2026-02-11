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
from utils.event_translation import translate_event_to_english

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
        rows = conn.execute(
            text("""
                SELECT id, source, external_id, title, description, location_name
                FROM events
                WHERE source IN ('baliforum', 'kudago', 'ai')
                  AND title_en IS NULL
                  AND title IS NOT NULL
                  AND TRIM(title) != ''
                ORDER BY id
                LIMIT :limit
            """),
            {"limit": args.batch * 5},
        ).fetchall()

    if not rows:
        logger.info("Нет событий для перевода (title_en уже заполнен или нет парсерных событий).")
        return

    logger.info("Найдено событий для перевода: %s (обрабатываем батчами по %s)", len(rows), args.batch)
    updated = 0
    errors = 0

    for i in range(0, len(rows), args.batch):
        batch = rows[i : i + args.batch]
        for row in batch:
            event_id, source, external_id, title, description, location_name = row
            title = (title or "").strip()
            if not title:
                continue
            trans = translate_event_to_english(
                title=title,
                description=description,
                location_name=location_name,
            )
            if args.dry_run:
                logger.info(
                    "[dry-run] id=%s title=%r -> title_en=%r",
                    event_id,
                    title[:50],
                    (trans.get("title_en") or "")[:50],
                )
                updated += 1
                continue
            title_en = trans.get("title_en")
            description_en = trans.get("description_en")
            location_name_en = trans.get("location_name_en")
            if not title_en and not description_en and not location_name_en:
                logger.warning("Пропуск id=%s: перевод не получен", event_id)
                errors += 1
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("""
                            UPDATE events
                            SET title_en = COALESCE(:title_en, title_en),
                                description_en = COALESCE(:description_en, description_en),
                                location_name_en = COALESCE(:location_name_en, location_name_en)
                            WHERE id = :id
                        """),
                        {
                            "id": event_id,
                            "title_en": title_en,
                            "description_en": description_en,
                            "location_name_en": location_name_en,
                        },
                    )
                updated += 1
                logger.info(
                    "id=%s title=%r -> title_en=%r",
                    event_id,
                    title[:40],
                    (title_en or "")[:40],
                )
            except Exception as e:
                logger.warning("Ошибка обновления id=%s: %s", event_id, e)
                errors += 1

    logger.info("Готово: обновлено=%s, ошибок=%s", updated, errors)


if __name__ == "__main__":
    main()
