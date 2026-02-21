"""
Догоняющий перевод событий (title_en, description_en, location_name_en).
ТЗ: две очереди — User (retry 30 сек) и Parser (пауза 10 мин при ошибке).
"""

import logging
import time
from typing import Any

from sqlalchemy import text

from database import get_engine
from utils.event_translation import translate_event_to_english, translate_titles_batch

logger = logging.getLogger(__name__)

BACKFILL_BATCH_SIZE = 8
OPENAI_ERROR_PAUSE_SEC_USER = 30  # User (Create): повторить через 30 сек
OPENAI_ERROR_PAUSE_SEC_PARSER = 600  # Parser/Backfill: пауза 10 мин
MAX_TRANSLATION_RETRIES = 3

# Ошибки OpenAI по очереди: user — короткое окно, parser — длинное
_last_openai_error_at: dict[str, float | None] = {"user": None, "parser": None}

WHERE_TAIL = """
    AND (translation_failed IS NULL OR translation_failed = false)
    AND (translation_retry_count IS NULL OR translation_retry_count < :max_retries)
"""


def run_backfill(
    batch_size: int = BACKFILL_BATCH_SIZE,
    full: bool = True,
) -> dict[str, Any]:
    """
    Две очереди: сначала user (event_source='user', пауза 30 сек при ошибке),
    затем parser (event_source IS NULL OR 'parser', пауза 10 мин).
    """
    global _last_openai_error_at
    engine = get_engine()
    total_processed = 0
    total_translated = 0
    total_skipped = 0

    now = time.time()

    # 1) Очередь User — приоритет, короткое окно повтора
    if _last_openai_error_at["user"] is None or (now - _last_openai_error_at["user"]) >= OPENAI_ERROR_PAUSE_SEC_USER:
        p, t, s = _process_queue(engine, batch_size, full, "user", "event_source = 'user'", "user")
        total_processed += p
        total_translated += t
        total_skipped += s
    else:
        logger.debug("[BACKFILL] User queue paused (30 sec after error)")

    # 2) Очередь Parser — пауза 10 мин при ошибке
    if (
        _last_openai_error_at["parser"] is None
        or (now - _last_openai_error_at["parser"]) >= OPENAI_ERROR_PAUSE_SEC_PARSER
    ):
        p, t, s = _process_queue(
            engine,
            batch_size,
            full,
            "parser",
            "(event_source IS NULL OR event_source = 'parser')",
            "parser",
        )
        total_processed += p
        total_translated += t
        total_skipped += s
    else:
        logger.info("[BACKFILL] Parser queue paused (10 min after error)")

    if total_translated > 0:
        logger.info(
            "[BACKFILL] ✓ Цикл завершён: переведено %s событий (пачка без рестарта контейнера)",
            total_translated,
        )
    return {"processed": total_processed, "translated": total_translated, "skipped": total_skipped}


def _process_queue(
    engine,
    batch_size: int,
    full: bool,
    queue_name: str,
    event_source_condition: str,
    error_key: str,
) -> tuple[int, int, int]:
    """Обрабатывает одну очередь (user или parser). Возвращает (processed, translated, skipped)."""
    global _last_openai_error_at
    processed = 0
    translated = 0
    skipped = 0

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
                          AND """
                        + event_source_condition
                        + WHERE_TAIL
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
                          AND """
                        + event_source_condition
                        + WHERE_TAIL
                        + """
                        ORDER BY id
                        LIMIT :limit
                    """
                    ),
                    {"limit": batch_size, "max_retries": MAX_TRANSLATION_RETRIES},
                ).fetchall()

        if not rows:
            break

        logger.info("[BACKFILL] [%s] Found %s events without EN (full=%s)", queue_name, len(rows), full)

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
                    logger.warning("[BACKFILL] [%s] Event id=%s: %s", queue_name, event_id, e)
                    skipped += 1
                    if "connection" in str(e).lower() or "timeout" in str(e).lower():
                        _last_openai_error_at[error_key] = time.time()
                        logger.warning("[BACKFILL] [%s] Ошибка соединения/таймаут, пауза", queue_name)
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
                logger.warning("[BACKFILL] [%s] translate_titles_batch empty (API error?), пауза", queue_name)
                _last_openai_error_at[error_key] = time.time()
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
            logger.info(
                "[BACKFILL] [%s] Batch translated %s (titles only)%s",
                queue_name,
                updated_this_batch,
                " — пачка успешно переведена без рестарта" if updated_this_batch > 0 else "",
            )

        if len(rows) < batch_size:
            break
        if not full and updated_this_batch == 0:
            logger.warning("[BACKFILL] [%s] No progress, stop", queue_name)
            break

    logger.info(
        "[BACKFILL] [%s] Completed. processed=%s translated=%s skipped=%s",
        queue_name,
        processed,
        translated,
        skipped,
    )
    return (processed, translated, skipped)
