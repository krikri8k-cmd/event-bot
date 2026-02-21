#!/usr/bin/env python3
"""
Ручной запуск бэкфилла локализации Interesting Places:
1. name_en = name (копирование, без перевода).
2. task_hint -> task_hint_en через OpenAI (batch 5–10).
"""

import logging
import os
import sys

# Добавляем корень проекта в path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    from database import init_engine
    from utils.backfill_task_places_translation import run_full_backfill

    init_engine()
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
