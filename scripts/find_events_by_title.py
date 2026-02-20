#!/usr/bin/env python3
"""
Поиск событий в БД по подстроке названия (title).
Выводит id, source, external_id, title, title_en — для диагностики перевода.
Запуск: python -m scripts.find_events_by_title "ЛИЛА" "Мафия"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def main():
    parser = argparse.ArgumentParser(description="Найти события по подстроке title")
    parser.add_argument("queries", nargs="+", help="Подстроки для поиска (ILIKE)")
    parser.add_argument("--limit", type=int, default=20, help="Макс. событий на запрос (по умолч. 20)")
    args = parser.parse_args()

    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        for q in args.queries:
            pattern = f"%{q}%"
            rows = conn.execute(
                text("""
                    SELECT id, source, external_id, title, title_en
                    FROM events
                    WHERE title ILIKE :pattern
                    ORDER BY id DESC
                    LIMIT :limit
                """),
                {"pattern": pattern, "limit": args.limit},
            ).fetchall()

            print(f"\n=== События по запросу «{q}» (id, source, external_id, title, title_en) ===")
            if not rows:
                print("  Не найдено.")
                continue
            for row in rows:
                eid, source, ext_id, title_ru, title_en = row
                tr = (title_ru or "")[:60]
                te = (title_en or "")[:60]
                print(f"  id={eid} source={source!r} external_id={ext_id!r}")
                print(f"    title:    {tr or 'None'}")
                print(f"    title_en: {te or 'None'}")
                print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
