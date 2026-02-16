"""
Догоняющий перевод title_en для событий, у которых перевод отсутствует.
Использует translate_titles_batch, не трогает уже переведённые.
"""

import logging
from typing import Any

from sqlalchemy import text

from database import get_engine
from utils.event_translation import translate_titles_batch

logger = logging.getLogger(__name__)

BACKFILL_BATCH_SIZE = 25


def run_backfill(batch_size: int = BACKFILL_BATCH_SIZE) -> dict[str, Any]:
    """
    Выбрать события с title_en IS NULL, перевести заголовки батчем, обновить БД.
    Возвращает {"processed": N, "translated": M, "skipped": K}.
    """
    engine = get_engine()
    processed = 0
    translated = 0
    skipped = 0

    while True:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, title
                    FROM events
                    WHERE (title_en IS NULL OR title_en = '')
                      AND title IS NOT NULL
                      AND TRIM(COALESCE(title, '')) != ''
                    ORDER BY id
                    LIMIT :limit
                """),
                {"limit": batch_size},
            ).fetchall()

        if not rows:
            break

        ids = [r[0] for r in rows]
        titles = [(r[1] or "").strip() for r in rows]
        logger.info("[BACKFILL] Found %s events without EN", len(rows))

        results = translate_titles_batch(titles)
        if not results:
            logger.warning("[BACKFILL] translate_titles_batch returned empty")
            skipped += len(rows)
            processed += len(rows)
            break

        updated_this_batch = 0
        with engine.begin() as conn:
            for i, (event_id, title_ru) in enumerate(zip(ids, titles)):
                processed += 1
                title_en = results[i] if i < len(results) else None
                if not title_en or not title_en.strip():
                    skipped += 1
                    continue
                conn.execute(
                    text("UPDATE events SET title_en = :title_en WHERE id = :id"),
                    {"id": event_id, "title_en": title_en.strip()},
                )
                updated_this_batch += 1
                translated += 1

        logger.info("[BACKFILL] Batch translated %s", updated_this_batch)
        if len(rows) < batch_size:
            break
        if updated_this_batch == 0:
            logger.warning("[BACKFILL] No progress (API failed?), stopping to avoid infinite loop")
            break

    logger.info("[BACKFILL] Completed. processed=%s translated=%s skipped=%s", processed, translated, skipped)
    return {"processed": processed, "translated": translated, "skipped": skipped}
