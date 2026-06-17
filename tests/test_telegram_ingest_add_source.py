"""Тесты парсинга /add_source (двухшаговый ввод)."""

import pytest

from telegram_ingest_handlers import _parse_add_source_args, _parse_source_line

pytestmark = pytest.mark.no_db


def test_parse_source_line_default_moderated():
    assert _parse_source_line("@mychannel") == ("@mychannel", "moderated")
    assert _parse_source_line("-100123456789") == ("-100123456789", "moderated")


def test_parse_source_line_with_trust():
    assert _parse_source_line("@mychannel trusted") == ("@mychannel", "trusted")
    assert _parse_source_line("-100123 moderated") == ("-100123", "moderated")


def test_parse_add_source_args_one_line():
    assert _parse_add_source_args("/add_source @foo trusted") == ("@foo", "trusted")
    assert _parse_add_source_args("/add_source -100999") == ("-100999", "moderated")


def test_parse_source_line_invalid():
    assert _parse_source_line("") is None
    assert _parse_source_line("foo bar baz") is None
