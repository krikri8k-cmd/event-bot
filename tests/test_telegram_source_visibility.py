"""Публичный vs закрытый telegram-источник."""

import pytest

from utils.telegram_source_visibility import is_public_telegram_event, is_public_telegram_source

pytestmark = pytest.mark.no_db


def test_public_source_has_username():
    assert is_public_telegram_source("mychannel") is True
    assert is_public_telegram_source("@mychannel") is True


def test_private_source_no_username():
    assert is_public_telegram_source(None) is False
    assert is_public_telegram_source("") is False


def test_public_event_has_community_link():
    assert is_public_telegram_event({"source": "telegram", "community_link": "https://t.me/mychannel"}) is True


def test_private_event_no_community_link():
    assert is_public_telegram_event({"source": "telegram", "community_link": None}) is False
    assert is_public_telegram_event({"source": "baliforum", "community_link": "x"}) is False
