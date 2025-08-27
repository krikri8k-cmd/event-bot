import os

import pytest

pytestmark = pytest.mark.api  # помечаем файл целиком

# В лёгком CI пропускаем модуль целиком, чтобы не импортировать fastapi/sqlalchemy
if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping API tests in light CI", allow_module_level=True)


def test_health_ok():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)

    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_db_ping_ok():
    from fastapi.testclient import TestClient

    from api.app import app

    client = TestClient(app)

    r = client.get("/db/ping")
    assert r.status_code == 200
    body = r.json()
    assert body.get("db") == "ok"
    assert int(body.get("value", 0)) == 1
