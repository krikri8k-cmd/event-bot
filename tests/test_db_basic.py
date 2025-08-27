import os

import pytest

# Лёгкий CI: пропускаем модуль сразу
if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping DB tests in light CI", allow_module_level=True)

# В full-запуске, если SQLAlchemy не установлена — мягко skip
pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed")
from sqlalchemy import create_engine, text


@pytest.mark.timeout(10)
def test_db_select_one():
    url = os.getenv("DATABASE_URL")
    assert url and url.startswith("postgresql+psycopg2://")
    engine = create_engine(url, future=True, pool_pre_ping=True)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
