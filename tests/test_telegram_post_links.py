"""Ссылки на посты Telegram для ingest."""

import pytest

from utils.telegram_post_links import build_telegram_post_url

pytestmark = pytest.mark.no_db


def test_public_channel_url():
    assert build_telegram_post_url(-100123, 42, "mychannel") == "https://t.me/mychannel/42"


def test_closed_supergroup_url():
    assert build_telegram_post_url(-1003958266496, 99, None) == "https://t.me/c/3958266496/99"


def test_basic_group_url():
    assert build_telegram_post_url(-5179811176, 286210, None) == "https://t.me/c/5179811176/286210"
