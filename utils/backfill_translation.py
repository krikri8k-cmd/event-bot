"""
Догоняющий перевод событий (title_en, description_en, location_name_en).
Полный режим: один вызов GPT на событие — заполняются все три поля для качества EN.
ТЗ: batch 5–10, пауза 10 мин при ошибке OpenAI, после 3 неудач — translation_failed.
"""

import logging
import time
from typing import Any

from sqlalchemy import text

from database import get_engine
from utils.event_translation import translate_event_to_english, translate_titles_batch

logger = logging.getLogger(__name__)

BACKFILL_BATCH_SIZE = 8  # ТЗ: 5–10 событий за раз, чтобы не было таймаутов и рестартов
OPENAI_ERROR_PAUSE_SEC = 600  # 10 минут не вызывать API после ошибки соединения/таймаута
MAX_TRANSLATION_RETRIES = 3

# Время последней ошибки OpenAI (соединение/таймаут) — не вызывать API 10 мин
_last_openai_error_at: float | None = None


def run_backfill(
    batch_size: int = BACKFILL_BATCH_SIZE,
    full: bool = True,
) -> dict[str, Any]:
    """
    События без title_en: перевести и записать в БД.
    full=True: один вызов translate_event_to_english на событие.
    full=False: только заголовки батчем.
    После ошибки соединения/таймаута не вызываем API 10 минут.
    События с translation_retry_count >= 3 пропускаем (translation_failed).
    """
    global _last_openai_error_at
    engine = get_engine()
    processed = 0
    translated = 0
    skipped = 0

    # ТЗ: пауза 10 мин после ошибки OpenAI
    if _last_openai_error_at is not None and (time.time() - _last_openai_error_at) < OPENAI_ERROR_PAUSE_SEC:
        logger.info("[BACKFILL] Paused after OpenAI error, skip this run (next in 10 min)")
        return {"processed": 0, "translated": 0, "skipped": 0, "paused": True}

    where_tail = """
        AND (translation_failed IS NULL OR translation_failed = false)
        AND (translation_retry_count IS NULL OR translation_retry_count < :max_retries)
    """
    while True:
        with engine.connect() as conn:
            if full:
                rows = conn.execute(
                    text(
                        """
                        SELECT id, title, description, location_name
                        FROM events
                        WHERE (title_en IS NULL OR title_en = '')
                          AND title IS NOT NULL
                          AND TRIM(COALESCE(title, '')) != ''
                        """
                        + where_tail
                        + """
                        ORDER BY id
                        LIMIT :limit
                    """
                    ),
                    {"limit": batch_size, "max_retries": MAX_TRANSLATION_RETRIES},
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT id, title
                        FROM events
                        WHERE (title_en IS NULL OR title_en = '')
                          AND title IS NOT NULL
                          AND TRIM(COALESCE(title, '')) != ''
                        """
                        + where_tail
                        + """
                        ORDER BY id
                        LIMIT :limit
                    """
                    ),
                    {"limit": batch_size, "max_retries": MAX_TRANSLATION_RETRIES},
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
                    title_en = (trans.get("title_en") or "").strip() if trans and trans.get("title_en") else None
                    desc = trans.get("description_en") if trans else None
                    description_en = (desc or "").strip() if desc else None
                    loc = trans.get("location_name_en") if trans else None
                    location_en = (loc or "").strip() if loc else None
                    if not title_en:
                        skipped += 1
                        with engine.begin() as conn2:
                            conn2.execute(
                                text("""
                                    UPDATE events
                                    SET translation_retry_count = COALESCE(translation_retry_count, 0) + 1,
                                        translation_failed = (COALESCE(translation_retry_count, 0) + 1 >= :max_r)
                                    WHERE id = :id
                                """),
                                {"id": event_id, "max_r": MAX_TRANSLATION_RETRIES},
                            )
                        continue
                    with engine.begin() as conn2:
                        conn2.execute(
                            text("""
                                UPDATE events
                                SET title_en = COALESCE(:title_en, title_en),
                                    description_en = COALESCE(:description_en, description_en),
                                    location_name_en = COALESCE(:location_name_en, location_name_en),
                                    translation_retry_count = 0
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
                    if "connection" in str(e).lower() or "timeout" in str(e).lower():
                        _last_openai_error_at = time.time()
                        break
                    with engine.begin() as conn2:
                        conn2.execute(
                            text("""
                                UPDATE events
                                SET translation_retry_count = COALESCE(translation_retry_count, 0) + 1,
                                    translation_failed = (COALESCE(translation_retry_count, 0) + 1 >= :max_r)
                                WHERE id = :id
                            """),
                            {"id": event_id, "max_r": MAX_TRANSLATION_RETRIES},
                        )
            logger.info("[BACKFILL] Batch translated %s (full)", updated_this_batch)
            if updated_this_batch == 0:
                logger.warning("[BACKFILL] No progress (API failed?), stopping")
                break
        else:
            ids = [r[0] for r in rows]
            titles = [(r[1] or "").strip() for r in rows]
            results = translate_titles_batch(titles)
            if not results:
                logger.warning("[BACKFILL] translate_titles_batch returned empty (API error?), pause 10 min")
                _last_openai_error_at = time.time()
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
