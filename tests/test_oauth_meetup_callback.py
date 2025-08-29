import os

import pytest

pytestmark = [
    pytest.mark.api,
    pytest.mark.meetup,
    pytest.mark.skipif(os.getenv("MEETUP_ENABLED") != "1", reason="Meetup disabled"),
]


def test_meetup_callback_ok(api_client):
    r = api_client.get("/oauth/meetup/callback", params={"code": "demo", "state": "xyz"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["ok"] is True
    assert payload["code"] == "demo"
    assert payload["state"] == "xyz"


def test_meetup_callback_missing_code(api_client):
    r = api_client.get("/oauth/meetup/callback")
    assert r.status_code == 400
