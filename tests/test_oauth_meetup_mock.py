import os

import pytest
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.api,
    pytest.mark.meetup,
    pytest.mark.skipif(os.getenv("MEETUP_ENABLED") != "1", reason="Meetup disabled"),
]


def test_meetup_callback_mock_ok(monkeypatch):
    # включаем мок-режим
    monkeypatch.setenv("MEETUP_MOCK", "1")

    from api.app import app  # импорт после установки env

    c = TestClient(app)
    r = c.get("/oauth/meetup/callback", params={"code": "demo", "state": "xyz"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "code": "demo", "state": "xyz", "mock": True}


def test_meetup_callback_missing_code(monkeypatch):
    # на всякий случай выключаем мок
    monkeypatch.delenv("MEETUP_MOCK", raising=False)

    from api.app import app

    c = TestClient(app)
    r = c.get("/oauth/meetup/callback")
    assert r.status_code == 400
    assert "Missing code" in r.text


def test_meetup_callback_with_error(monkeypatch):
    # включаем мок-режим
    monkeypatch.setenv("MEETUP_MOCK", "1")

    from api.app import app

    c = TestClient(app)
    r = c.get("/oauth/meetup/callback", params={"error": "access_denied"})
    assert r.status_code == 400
    assert "Meetup error: access_denied" in r.text


def test_meetup_callback_mock_without_state(monkeypatch):
    # включаем мок-режим
    monkeypatch.setenv("MEETUP_MOCK", "1")

    from api.app import app

    c = TestClient(app)
    r = c.get("/oauth/meetup/callback", params={"code": "demo"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["ok"] is True
    assert payload["code"] == "demo"
    assert payload["state"] is None
    assert payload["mock"] is True
