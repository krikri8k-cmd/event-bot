"""
Бэкфилл локализации Interesting Places (task_places).

ТЗ:
1. name_en — копирование из name (брендинг без перевода).
2. task_hint_en — перевод только task_hint через OpenAI (batch 5–10).
3. После цикла: лог [TASK-BACKFILL] Processed X places. Names mirrored, hints translated.
"""

import logging
from typing import Any

from sqlalchemy import text

from database import get_engine
from utils.event_translation import translate_task_hints_batch

logger = logging.getLogger(__name__)

# ТЗ: 5–10 записей за цикл
HINT_BATCH_SIZE = 8


def run_name_mirror() -> int:
    """
    Заполняет name_en копированием из name. Названия не переводятся (брендинг).
    Возвращает количество обновлённых строк.
    """
    engine = get_engine()
    if not engine:
        return 0
    with engine.begin() as conn:
        r = conn.execute(
            text(
                """
                UPDATE task_places
                SET name_en = name
                WHERE (name_en IS NULL OR TRIM(COALESCE(name_en, '')) = '')
                  AND name IS NOT NULL
                  AND TRIM(COALESCE(name, '')) != ''
                """
            )
        )
        count = r.rowcount
    if count:
        logger.info("[TASK-BACKFILL] Names mirrored: %s places (name -> name_en)", count)
    return count


def run_hint_backfill(
    batch_size: int = HINT_BATCH_SIZE,
    max_batches: int | None = None,
) -> tuple[int, int]:
    """
    Выбирает записи с task_hint_en IS NULL, переводит task_hint пачкой, пишет в task_hint_en.
    max_batches: если задан, после N пачек выходим (для одного цикла по 10 мест — batch_size=10, max_batches=1).
    Возвращает (processed, translated).
    """
    engine = get_engine()
    if not engine:
        return 0, 0
    processed = 0
    translated = 0
    batches_done = 0
    while True:
        if max_batches is not None and batches_done >= max_batches:
            break
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, task_hint
                    FROM task_places
                    WHERE (task_hint_en IS NULL OR TRIM(COALESCE(task_hint_en, '')) = '')
                      AND task_hint IS NOT NULL
                      AND TRIM(COALESCE(task_hint, '')) != ''
                    ORDER BY id
                    LIMIT :limit
                    """
                ),
                {"limit": batch_size},
            ).fetchall()
        if not rows:
            if batches_done == 0:
                logger.info("[TASK-GPT] Нет записей для перевода (task_hint_en пустой и task_hint задан).")
            break
        ids = [r[0] for r in rows]
        hints = [r[1] for r in rows]
        results = translate_task_hints_batch(hints)
        batch_translated = 0
        with engine.begin() as conn:
            for place_id, hint_en in zip(ids, results):
                processed += 1
                if hint_en:
                    conn.execute(
                        text("UPDATE task_places SET task_hint_en = :val WHERE id = :id"),
                        {"id": place_id, "val": hint_en},
                    )
                    translated += 1
                    batch_translated += 1
        if batch_translated > 0:
            logger.info(
                "[TASK-GPT] Переведено %s описаний квестов.",
                batch_translated,
            )
        batches_done += 1
    return processed, translated


def _count_places_needing_hint_translation() -> int:
    """Количество записей task_places с пустым task_hint_en и непустым task_hint."""
    engine = get_engine()
    if not engine:
        return 0
    with engine.connect() as conn:
        r = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM task_places
                WHERE (task_hint_en IS NULL OR TRIM(COALESCE(task_hint_en, '')) = '')
                  AND task_hint IS NOT NULL
                  AND TRIM(COALESCE(task_hint, '')) != ''
                """
            )
        ).scalar()
    return r or 0


def run_full_backfill(
    batch_size: int = HINT_BATCH_SIZE,
) -> dict[str, Any]:
    """
    Сначала зеркалирует name -> name_en, затем переводит task_hint -> task_hint_en.
    В лог: [TASK-BACKFILL] Processed X places. Names mirrored, hints translated.
    [GPT] Запущен перевод task_hint для X мест.
    """
    names_mirrored = run_name_mirror()
    places_to_translate = _count_places_needing_hint_translation()
    logger.info("[GPT] Запущен перевод task_hint для %s мест.", places_to_translate)
    processed, translated = run_hint_backfill(batch_size=batch_size)
    remaining = _count_places_needing_hint_translation()
    if remaining == 0:
        logger.info("[TASK-BACKFILL] В базе не осталось пустых task_hint_en.")
    else:
        logger.info("[TASK-BACKFILL] Осталось без перевода: %s мест.", remaining)
    total_places = names_mirrored + processed
    logger.info(
        "[TASK-BACKFILL] Processed %s places. Names mirrored, hints translated.",
        total_places or translated or names_mirrored or "0",
    )
    return {
        "names_mirrored": names_mirrored,
        "hints_processed": processed,
        "hints_translated": translated,
        "remaining_empty_hint_en": remaining,
    }
