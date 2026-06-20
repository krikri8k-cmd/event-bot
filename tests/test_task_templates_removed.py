"""Проверки удаления legacy task_templates."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.no_db


def test_task_templates_migration_files_exist():
    migration = ROOT / "migrations" / "053_drop_task_templates.sql"
    pre_check = ROOT / "migrations" / "053_pre_check_task_templates.sql"
    assert migration.exists(), "053_drop_task_templates.sql missing"
    assert pre_check.exists(), "053_pre_check_task_templates.sql missing"

    sql = migration.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS task_templates" in sql
    assert "DELETE FROM daily_views_tasks WHERE view_type = 'template'" in sql
    assert "DROP COLUMN IF EXISTS template_id" in sql


def test_task_template_model_removed_from_database():
    database_py = (ROOT / "database.py").read_text(encoding="utf-8")
    assert "class TaskTemplate" not in database_py
    assert "task_templates" not in database_py


def test_legacy_task_service_removed():
    assert not (ROOT / "tasks" / "task_service.py").exists()


def test_active_tasks_service_does_not_use_templates():
    tasks_service_py = (ROOT / "tasks_service.py").read_text(encoding="utf-8")
    assert "TaskTemplate" not in tasks_service_py
    assert "task_templates" not in tasks_service_py
    assert "create_task_from_place" in tasks_service_py


def test_load_task_data_does_not_reference_templates():
    load_script = (ROOT / "scripts" / "load_task_data.py").read_text(encoding="utf-8")
    assert "TaskTemplate" not in load_script
    assert "task_templates" not in load_script
