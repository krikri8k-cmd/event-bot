import os

import pytest
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.api,
    pytest.mark.meetup,
    pytest.mark.skipif(os.getenv("MEETUP_ENABLED") != "1", reason="Meetup disabled"),
]


def test_meetup_login_returns_url(monkeypatch):
    if os.environ.get("FULL_TESTS") != "1":
        pytest.skip("skip in light CI", allow_module_level=False)

    from api.app import app

    monkeypatch.setenv("MEETUP_CLIENT_ID", "dummy")
    monkeypatch.setenv("MEETUP_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MEETUP_REDIRECT_URI", "http://localhost:8000/oauth/meetup/callback")

    c = TestClient(app)
    r = c.get("/oauth/meetup/login")
    assert r.status_code == 200
    url = r.json()["authorize_url"]
    assert "client_id=dummy" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Foauth%2Fmeetup%2Fcallback" in url


def test_meetup_login_no_client_id(monkeypatch):
    if os.environ.get("FULL_TESTS") != "1":
        pytest.skip("skip in light CI", allow_module_level=False)

    from api.app import app

    # Убираем MEETUP_CLIENT_ID
    monkeypatch.delenv("MEETUP_CLIENT_ID", raising=False)

    c = TestClient(app)
    r = c.get("/oauth/meetup/login")
    assert r.status_code == 500
    assert "MEETUP_CLIENT_ID is not configured" in r.json()["detail"]


def test_meetup_callback_missing_code():
    if os.environ.get("FULL_TESTS") != "1":
        pytest.skip("skip in light CI", allow_module_level=False)

    from api.app import app

    c = TestClient(app)
    r = c.get("/oauth/meetup/callback")
    assert r.status_code == 422  # Validation error - missing required parameter


def test_oauth_meetup_manager():
    """Тест OAuth менеджера без сетевых запросов"""
    if os.environ.get("FULL_TESTS") != "1":
        pytest.skip("skip in light CI", allow_module_level=False)

    from api.oauth_meetup import MeetupOAuth, TokenBundle

    # Тест маскирования токенов
    bundle = TokenBundle(
        access_token="abcdef123456789",
        refresh_token="xyz789abcdef",
        expires_in=3600,
        token_type="bearer",
    )

    preview = MeetupOAuth.mask_preview(bundle)
    assert preview["access"] == "abcdef…89"
    assert preview["refresh"] == "xyz789…ef"
    assert preview["expires_in"] == 3600

    # Тест headers без токенов
    oauth = MeetupOAuth()
    assert oauth.headers() == {}

    # Тест authorize_url
    url = oauth.authorize_url()
    assert "secure.meetup.com/oauth2/authorize" in url
    assert "response_type=code" in url
