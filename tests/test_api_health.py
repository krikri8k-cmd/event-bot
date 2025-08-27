import os

import pytest

# В лёгком CI пропускаем модуль целиком, чтобы не импортировать fastapi/sqlalchemy
if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping API tests in light CI", allow_module_level=True)

# Доп. защита: если full-запуск, но пакета нет — помечаем как skipped, а не error
pytest.importorskip("fastapi", reason="fastapi not installed")
pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed")

from fastapi.testclient import TestClient

# если у проекта фабрика приложения, используй её:
# from api.app import create_app; app = create_app()
from api.app import app  # адаптируй под свой код

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_db_ping_ok():
    r = client.get("/db/ping")
    assert r.status_code == 200
    body = r.json()
    assert body.get("db") == "ok"
    assert int(body.get("value", 0)) == 1
