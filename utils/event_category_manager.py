"""Определение системных категорий событий по данным источника."""

from __future__ import annotations

USER_COMMUNITY_SOURCES = frozenset({"user", "community"})
EXTERNAL_API_SOURCES = frozenset({"megatix", "savaya", "google_calendar"})

BALIFORUM_TAG_EN_MAP: dict[str, str] = {
    "искусство": "Art",
    "вечеринка": "Party",
    "еда": "Food",
    "семья": "Family",
    "йога": "Yoga",
    "кино": "Cinema",
    "игра": "Games",
    "напитки": "Drinks",
    "бизнес": "Business",
    "концерт": "Concert",
    "открытый микрофон": "Open mic",
    "медитация": "Meditation",
    "тренинг": "Training",
    "фестиваль": "Festival",
    "мастер-класс": "Workshop",
    "духовное": "Spiritual",
    "музыка": "Music",
    "танцы": "Dance",
    "дети": "Kids",
    "спорт": "Sport",
    "живая музыка": "Live music",
    "ремесло": "Crafts",
    "шоу": "Show",
    "стендап": "Stand-up",
}

TELEGRAM_CATEGORY_ALIASES: dict[str, str] = {
    "party": "Вечеринка",
    "вечеринка": "Вечеринка",
    "еда": "Еда",
    "food": "Еда",
    "йога": "Духовное",
    "yoga": "Духовное",
    "медитация": "Духовное",
    "концерт": "Концерт",
    "concert": "Концерт",
    "игра": "Игра",
    "games": "Игра",
    "game": "Игра",
    "спорт": "Спорт",
    "sport": "Спорт",
    "бизнес": "Бизнес",
    "business": "Бизнес",
    "выставка": "Выставка",
    "art": "Выставка",
    "искусство": "Выставка",
    "мастер-класс": "Мастер-класс",
    "workshop": "Мастер-класс",
    "фестиваль": "Фестиваль",
    "festival": "Фестиваль",
}


def normalize_tag(tag: str) -> str:
    return tag.strip().lower()


def dedupe_categories(categories: list[str]) -> list[str]:
    return list(dict.fromkeys(categories))


def parse_source_display_tags(event_data: dict) -> list[str]:
    """Теги источника для UI: tags или разбор raw_category."""
    tags = event_data.get("tags")
    if isinstance(tags, list):
        cleaned = [str(t).strip() for t in tags if str(t).strip()]
        if cleaned:
            return cleaned
    raw = event_data.get("raw_category")
    if raw:
        return [t.strip() for t in str(raw).split(",") if t.strip()]
    return []


def localize_baliforum_tags(tags: list[str], lang: str) -> list[str]:
    if lang != "en":
        return tags
    return [BALIFORUM_TAG_EN_MAP.get(normalize_tag(tag), tag) for tag in tags]


def format_source_display_tags(event_data: dict, lang: str = "ru") -> list[str]:
    tags = parse_source_display_tags(event_data)
    if not tags:
        return []
    source = (event_data.get("source") or "").strip().lower()
    if source == "baliforum":
        return localize_baliforum_tags(tags, lang)
    return tags


class EventCategoryManager:
    """Единая точка категоризации событий для ingest."""

    def assign_categories(self, event_data: dict, source: str) -> list[str]:
        if source == "telegram":
            return self._assign_telegram(event_data)
        if source in USER_COMMUNITY_SOURCES:
            return []
        if source in EXTERNAL_API_SOURCES:
            raw_api = event_data.get("raw_api_category")
            return [str(raw_api).strip()] if raw_api else []
        return []

    def resolve_raw_category(self, event_data: dict, source: str) -> str | None:
        if source == "telegram":
            cats = self._assign_telegram(event_data)
            return ", ".join(cats) if cats else None
        if source in EXTERNAL_API_SOURCES:
            raw_api = event_data.get("raw_api_category")
            return str(raw_api).strip() if raw_api else None
        return None

    def _assign_telegram(self, event_data: dict) -> list[str]:
        llm_categories = event_data.get("categories") or []
        default_categories = event_data.get("default_categories") or []
        source_list = llm_categories if llm_categories else default_categories

        result: list[str] = []
        for raw in source_list:
            text = str(raw).strip()
            if not text:
                continue
            mapped = TELEGRAM_CATEGORY_ALIASES.get(normalize_tag(text))
            result.append(mapped or text)
        return dedupe_categories(result)
