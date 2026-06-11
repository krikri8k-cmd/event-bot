#!/usr/bin/env python3
"""Применить миграцию telegram_sources / telegram_ingest_log к БД."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "050_create_telegram_ingest_tables.sql"


def main() -> int:
    from config import load_settings
    from sqlalchemy import create_engine, text

    settings = load_settings()
    if not settings.database_url:
        print("DATABASE_URL не задан.", file=sys.stderr)
        return 1

    sql = MIGRATION.read_text(encoding="utf-8")
    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as conn:
        conn.execute(text(sql))
    print(f"OK: applied {MIGRATION.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
