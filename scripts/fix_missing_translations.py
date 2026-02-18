#!/usr/bin/env python3
"""
Временный скрипт «доперевода»: выбирает из БД все события с title_en IS NULL,
прогоняет через OpenAI и заполняет title_en, description_en, location_name_en.

Запуск из корня проекта:
  python -m scripts.fix_missing_translations
  python -m scripts.fix_missing_translations --batch 10 --dry-run
  python -m scripts.fix_missing_translations --limit 50
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from utils.event_translation import translate_event_to_english

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BATCH = 10

# Ограничение по умолчанию при вызове из планировщика (чтобы не грузить API надолго)
SCHEDULER_LIMIT = 50


def run_fix_missing_translations(
    batch: int = DEFAULT_BATCH,
    limit: int | None = None,
    engine=None,
    dry_run: bool = False,
):
    """
    Находит события с title_en IS NULL, переводит через OpenAI и обновляет БД.
    Можно вызывать из кода (например из modern_scheduler) или из CLI через main().

    :param batch: размер батча
    :param limit: макс. число событий (None = все)
    :param engine: SQLAlchemy engine (если None, используется get_engine())
    :param dry_run: только логировать, не писать в БД
    :return: (updated_count, errors_count)
    """
    if engine is None:
        engine = get_engine()

    with engine.connect() as conn:
        query = text("""
            SELECT id, title, description, location_name
            FROM events
            WHERE title_en IS NULL
              AND title IS NOT NULL
              AND TRIM(title) != ''
            ORDER BY id
        """)
        if limit:
            rows = conn.execute(query).fetchmany(limit)
        else:
            rows = conn.execute(query).fetchall()

    if not rows:
        logger.info("Нет событий без перевода (title_en везде заполнен или нет подходящих записей).")
        return 0, 0

    logger.info("Найдено событий для доперевода: %s (батч по %s)", len(rows), batch)
    updated = 0
    errors = 0

    for i in range(0, len(rows), batch):
        batch_rows = rows[i : i + batch]
        for row in batch_rows:
            event_id, title, description, location_name = row
            title = (title or "").strip()
            if not title:
                continue
            if dry_run:
                logger.info("[dry-run] id=%s title=%r", event_id, title[:50])
                updated += 1
                continue

            trans = translate_event_to_english(
                title=title,
                description=(description or "").strip() or None,
                location_name=(location_name or "").strip() or None,
            )
            title_en = trans.get("title_en")
            description_en = trans.get("description_en")
            location_name_en = trans.get("location_name_en")

            if not title_en:
                errors += 1
                logger.warning("id=%s: перевод не получен, пропуск", event_id)
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
                errors += 1
                logger.exception("id=%s: ошибка UPDATE: %s", event_id, e)

    logger.info("Готово. Обновлено: %s, ошибок/пропусков: %s", updated, errors)
    return updated, errors


def main():
    ap = argparse.ArgumentParser(description="Доперевод событий без title_en через OpenAI")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH, help="Размер батча (default %s)" % DEFAULT_BATCH)
    ap.add_argument("--limit", type=int, default=None, help="Макс. число событий (по умолчанию — все)")
    ap.add_argument("--dry-run", action="store_true", help="Только показать, что бы обновили")
    args = ap.parse_args()

    settings = load_settings()
    if not getattr(settings, "openai_api_key", None):
        logger.error("OPENAI_API_KEY не задан. Задайте в .env или app.local.env")
        sys.exit(1)
    init_engine(settings.database_url)
    engine = get_engine()

    run_fix_missing_translations(batch=args.batch, limit=args.limit, engine=engine, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
