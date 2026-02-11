#!/usr/bin/env python3
"""
Проверка мультиязычности событий в БД.
Находит последние события от baliforum и выводит id, title (RU), title_en.
Запуск: python -m scripts.check_db_events_i18n
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine


def main():
    settings = load_settings()
    init_engine(settings.database_url)
    engine = get_engine()

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, source, title, title_en, description_en, location_name_en
                FROM events
                WHERE source = 'baliforum'
                ORDER BY id DESC
                LIMIT 5
            """)
        ).fetchall()

    lines = ["=== Last 5 baliforum events (id, title RU, title_en) ===\n"]
    for row in rows:
        eid, source, title_ru, title_en, desc_en, loc_en = row
        tr = (title_ru or "")[:80]
        te = (title_en or "")[:80]
        lines.append(f"ID: {eid}")
        lines.append(f"  title (RU): {tr or 'None'}")
        lines.append(f"  title_en:   {te or 'None'}")
        lines.append(f"  desc_en:    {(desc_en or '')[:50]}")
        lines.append(f"  loc_en:     {(loc_en or '')[:50]}")
        lines.append("")
    if not rows:
        lines.append("No baliforum events found.")
    out = "\n".join(lines)
    out_path = Path(__file__).resolve().parent.parent / "check_db_events_i18n_result.txt"
    out_path.write_text(out, encoding="utf-8")
    print(out_path)
    print("Result written to check_db_events_i18n_result.txt (UTF-8)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
