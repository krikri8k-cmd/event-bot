import os
from unittest.mock import patch

import pytest

# Защита от отсутствия fastapi
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = [
    pytest.mark.api,
    pytest.mark.meetup,
    pytest.mark.skipif(os.getenv("MEETUP_ENABLED") != "1", reason="Meetup disabled"),
]


def test_meetup_callback_ok():
    from api.app import app

    client = TestClient(app)

    r = client.get("/oauth/meetup/callback", params={"code": "demo", "state": "xyz"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["ok"] is True
    assert payload["code"] == "demo"
    assert payload["state"] == "xyz"


def test_meetup_callback_missing_code():
    from api.app import app

    client = TestClient(app)

    r = client.get("/oauth/meetup/callback")
    assert r.status_code == 400


# Простой тест без skip_light для проверки
@patch.dict("os.environ", {"DATABASE_URL": "sqlite:///:memory:", "MEETUP_MOCK": "1"})
def test_meetup_callback_simple():
    """Простой тест без зависимости от FULL_TESTS"""
    from api.app import app

    client = TestClient(app)

    r = client.get("/oauth/meetup/callback", params={"code": "demo", "state": "xyz"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["ok"] is True
    assert payload["code"] == "demo"
    assert payload["state"] == "xyz"
    assert payload["mock"] is True
