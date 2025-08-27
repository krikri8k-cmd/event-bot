from fastapi.testclient import TestClient

# пробуем оба варианта импорта
try:
    from api.app import create_app  # type: ignore
    app = create_app()
except Exception:
    from api.app import app  # type: ignore

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
