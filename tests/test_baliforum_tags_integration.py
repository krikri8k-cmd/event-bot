import pytest
from bs4 import BeautifulSoup

from sources.baliforum import _extract_tags_from_card
from utils.event_category_manager import EventCategoryManager

BALIFORUM_CARD_HTML = """
<div class="event-card events__card">
  <a href="/events/festival-photo">Фотофестиваль Бали</a>
  <a href="/places/labyrinth">Labyrinth Dome Bali</a>
  <div class="event-card__types-wrap">
    <div class="event-types event-card__types">
      <a class="event-types__item linked" href="/events?types=1">Фестиваль</a>
      <a class="event-types__item linked" href="/events?types=2">Искусство</a>
    </div>
  </div>
</div>
"""


@pytest.mark.no_db
def test_baliforum_card_tags_to_categories_pipeline():
    card = BeautifulSoup(BALIFORUM_CARD_HTML, "html.parser").select_one("div.event-card")
    tags = _extract_tags_from_card(card)
    assert tags == ["Фестиваль", "Искусство"]

    manager = EventCategoryManager()
    categories = manager.assign_categories({"tags": tags}, "baliforum")
    raw_category = manager.resolve_raw_category({"tags": tags}, "baliforum")

    assert categories == ["Выставка"]
    assert raw_category == "Фестиваль, Искусство"
