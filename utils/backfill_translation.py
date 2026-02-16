"""
Догоняющий перевод событий (title_en, description_en, location_name_en).
Полный режим: один вызов GPT на событие — заполняются все три поля для качества EN.
"""

import logging
from typing import Any

from sqlalchemy import text

from database import get_engine
from utils.event_translation import translate_event_to_english, translate_titles_batch

logger = logging.getLogger(__name__)

BACKFILL_BATCH_SIZE = 25


def run_backfill(
    batch_size: int = BACKFILL_BATCH_SIZE,
    full: bool = True,
) -> dict[str, Any]:
    """
    События без title_en: перевести и записать в БД.
    full=True (по умолчанию): один вызов translate_event_to_english на событие —
      заполняются title_en, description_en, location_name_en (качественный EN).
    full=False: только заголовки батчем (быстрее, меньше вызовов API).
    Возвращает {"processed": N, "translated": M, "skipped": K}.
    """
    engine = get_engine()
    processed = 0
    translated = 0
    skipped = 0

    while True:
        with engine.connect() as conn:
            if full:
                rows = conn.execute(
                    text("""
                        SELECT id, title, description, location_name
                        FROM events
                        WHERE (title_en IS NULL OR title_en = '')
                          AND title IS NOT NULL
                          AND TRIM(COALESCE(title, '')) != ''
                        ORDER BY id
                        LIMIT :limit
                    """),
                    {"limit": batch_size},
                ).fetchall()
            else:
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

        logger.info("[BACKFILL] Found %s events without EN (full=%s)", len(rows), full)

        if full:
            updated_this_batch = 0
            for row in rows:
                processed += 1
                event_id = row[0]
                title_ru = (row[1] or "").strip()
                description_ru = (row[2] if len(row) > 2 else None) or None
                location_ru = (row[3] if len(row) > 3 else None) or None
                try:
                    trans = translate_event_to_english(
                        title=title_ru,
                        description=description_ru,
                        location_name=location_ru,
                    )
                    title_en = (trans.get("title_en") or "").strip() if trans.get("title_en") else None
                    desc = trans.get("description_en")
                    description_en = (desc or "").strip() if desc else None
                    loc = trans.get("location_name_en")
                    location_en = (loc or "").strip() if loc else None
                    if not title_en:
                        skipped += 1
                        continue
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
                                "description_en": description_en or None,
                                "location_name_en": location_en or None,
                            },
                        )
                    updated_this_batch += 1
                    translated += 1
                except Exception as e:
                    logger.warning("[BACKFILL] Event id=%s: %s", event_id, e)
                    skipped += 1
            logger.info("[BACKFILL] Batch translated %s (full)", updated_this_batch)
            if updated_this_batch == 0:
                logger.warning("[BACKFILL] No progress (API failed?), stopping")
                break
        else:
            ids = [r[0] for r in rows]
            titles = [(r[1] or "").strip() for r in rows]
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
            logger.info("[BACKFILL] Batch translated %s (titles only)", updated_this_batch)

        if len(rows) < batch_size:
            break
        if not full and updated_this_batch == 0:
            logger.warning("[BACKFILL] No progress (API failed?), stopping to avoid infinite loop")
            break

    logger.info("[BACKFILL] Completed. processed=%s translated=%s skipped=%s", processed, translated, skipped)
    return {"processed": processed, "translated": translated, "skipped": skipped}
