"""Тесты admin_delete_event (парсинг community external_id)."""

import pytest

from utils.sync_community_world_events import _parse_community_external_id


@pytest.mark.no_db
def test_parse_community_external_id_valid():
    assert _parse_community_external_id("community:-100123:42") == (-100123, 42)


@pytest.mark.no_db
def test_parse_community_external_id_invalid():
    assert _parse_community_external_id("telegram:abc") is None
    assert _parse_community_external_id("") is None
    assert _parse_community_external_id("community:1") is None
