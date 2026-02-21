#!/usr/bin/env python3
"""
Ручной запуск бэкфилла локализации Interesting Places:
1. name_en = name (копирование, без перевода).
2. task_hint -> task_hint_en через OpenAI (batch 5–10).

Один цикл по 10 квестам: python scripts/run_backfill_task_places_i18n.py --hint-only --limit 10
"""

import argparse
import logging
import os
import sys

# Добавляем корень проекта в path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Backfill task_places name_en / task_hint_en")
    parser.add_argument("--hint-only", action="store_true", help="Только перевод task_hint -> task_hint_en")
    parser.add_argument("--limit", type=int, default=None, help="Макс. число мест за один запуск")
    args = parser.parse_args()

    from config import load_settings
    from database import init_engine
    from utils.backfill_task_places_translation import run_full_backfill, run_hint_backfill

    settings = load_settings()
    init_engine(settings.database_url)

    if args.hint_only:
        batch_size = args.limit or 10
        max_batches = 1 if args.limit else None
        processed, translated = run_hint_backfill(batch_size=batch_size, max_batches=max_batches)
        logger.info("Done. hints_processed=%s, hints_translated=%s", processed, translated)
        return 0

    result = run_full_backfill()
    logger.info(
        "Done. names_mirrored=%s, hints_processed=%s, hints_translated=%s",
        result["names_mirrored"],
        result["hints_processed"],
        result["hints_translated"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
