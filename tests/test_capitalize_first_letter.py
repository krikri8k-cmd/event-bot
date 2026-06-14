"""Заголовок события: первая буква всегда заглавная, остальной регистр не трогаем."""

import pytest

from bot_enhanced_v3 import _capitalize_first_letter

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("женская трансформационная игра", "Женская трансформационная игра"),
        ("коллекция Эрмитажа", "Коллекция Эрмитажа"),
        ("Family First в Le Bajo", "Family First в Le Bajo"),  # уже заглавная — без изменений
        ("«антарктика» в музее", "«Антарктика» в музее"),  # пропускаем ведущую кавычку
        ("yoga retreat", "Yoga retreat"),
        ("A", "A"),
        ("я", "Я"),
        ("", ""),
        ("123 событие", "123 событие"),  # нет ведущей буквы — без изменений
    ],
)
def test_capitalize_first_letter(raw, expected):
    assert _capitalize_first_letter(raw) == expected


def test_rest_of_string_unchanged():
    """Меняется только первая буква, внутренний регистр сохраняется."""
    assert _capitalize_first_letter("iPhone meetup") == "IPhone meetup"
    assert _capitalize_first_letter("eDM party") == "EDM party"
