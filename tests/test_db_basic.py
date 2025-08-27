import os

import pytest

if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping DB tests in light CI", allow_module_level=True)


@pytest.mark.timeout(10)
def test_db_basic(api_engine, db_clean):
    # импорт только внутри теста
    from sqlalchemy import text

    # проверяем, что БД отвечает
    with api_engine.begin() as c:
        c.execute(text("SELECT 1"))
