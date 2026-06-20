#!/usr/bin/env python3
"""
Pre-check перед удалением legacy-таблицы task_templates.
Возвращает exit code 0, если миграция безопасна; 1 — если есть блокеры.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _table_exists(conn, table_name: str) -> bool:
    from sqlalchemy import text

    row = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    ).scalar()
    return bool(row)


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    from sqlalchemy import text

    row = conn.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar()
    return bool(row)


def run_pre_check(conn) -> tuple[bool, list[str]]:
    from sqlalchemy import text

    issues: list[str] = []
    warnings: list[str] = []

    if not _table_exists(conn, "task_templates"):
        logger.info("✅ task_templates уже отсутствует — миграция не нужна или уже применена")
        return True, []

    templates_count = conn.execute(text("SELECT COUNT(*) FROM task_templates")).scalar() or 0
    logger.info("ℹ️  task_templates rows: %s", templates_count)
    if templates_count:
        warnings.append(f"task_templates содержит {templates_count} строк (legacy, будут удалены)")

    if _column_exists(conn, "user_tasks", "template_id"):
        linked = conn.execute(text("SELECT COUNT(*) FROM user_tasks WHERE template_id IS NOT NULL")).scalar() or 0
        logger.info("ℹ️  user_tasks with template_id: %s", linked)
        if linked:
            issues.append(f"user_tasks содержит {linked} записей с template_id — нужен ручной разбор")
    else:
        logger.info("✅ user_tasks.template_id отсутствует")

    if _table_exists(conn, "daily_views_tasks"):
        template_views = (
            conn.execute(text("SELECT COUNT(*) FROM daily_views_tasks WHERE view_type = 'template'")).scalar() or 0
        )
        logger.info("ℹ️  daily_views_tasks (view_type=template): %s", template_views)
        if template_views:
            warnings.append(f"daily_views_tasks содержит {template_views} template-записей (будут удалены миграцией)")

    fk_rows = conn.execute(
        text(
            """
            SELECT tc.table_name, tc.constraint_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.constraint_type = 'FOREIGN KEY'
              AND tc.constraint_name ILIKE '%task_template%'
            ORDER BY tc.table_name, tc.constraint_name
            """
        )
    ).fetchall()
    if fk_rows:
        for table_name, constraint_name, column_name in fk_rows:
            logger.info("ℹ️  FK %s on %s.%s (будет снят миграцией)", constraint_name, table_name, column_name)
    else:
        logger.info("✅ FK на task_templates не найдены")

    for warning in warnings:
        logger.warning("⚠️  %s", warning)

    if issues:
        for issue in issues:
            logger.error("❌ %s", issue)
        return False, issues

    logger.info("✅ Pre-check пройден — migrations/053_drop_task_templates.sql можно применять")
    return True, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-check перед удалением task_templates")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_PUBLIC_URL"),
        help="Postgres URL (по умолчанию DATABASE_URL / DATABASE_PUBLIC_URL)",
    )
    args = parser.parse_args()

    if not args.database_url:
        logger.error("❌ DATABASE_URL не задан")
        return 2

    from config import load_settings
    from database import get_engine, init_engine

    settings = load_settings()
    init_engine(args.database_url or settings.database_url)
    engine = get_engine()
    if not engine:
        logger.error("❌ Database engine not available")
        return 2

    with engine.connect() as conn:
        ok, _ = run_pre_check(conn)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
