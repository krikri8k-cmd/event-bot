"""Определение системных категорий событий по данным источника."""

from __future__ import annotations

# Источники пользовательских / community-событий — классификация позже.
USER_COMMUNITY_SOURCES = frozenset({"user", "community"})

# Источники с категорией из API (маппинг добавится позже).
EXTERNAL_API_SOURCES = frozenset({"megatix", "savaya", "google_calendar"})

# Отображение тегов BaliForum в карточке для lang=en (UI only, не internal categories).
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

BALIFORUM_TAG_MAP: dict[str, str] = {
    "выставка": "Выставка",
    "искусство": "Выставка",
    "фестиваль": "Выставка",
    "йога": "Духовное",
    "духовное": "Духовное",
    "медитация": "Духовное",
    "бизнес": "Бизнес",
    "it": "IT",
    "вечеринка": "Вечеринка",
    "еда": "Еда",
}


def normalize_tag(tag: str) -> str:
    return tag.strip().lower()


def dedupe_categories(categories: list[str]) -> list[str]:
    return list(dict.fromkeys(categories))


def parse_source_display_tags(event_data: dict) -> list[str]:
    """Теги источника для UI: tags или разбор raw_category (не internal categories)."""
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
    """Переводит теги BaliForum для отображения; неизвестные теги остаются как есть."""
    if lang != "en":
        return tags
    return [BALIFORUM_TAG_EN_MAP.get(normalize_tag(tag), tag) for tag in tags]


def format_source_display_tags(event_data: dict, lang: str = "ru") -> list[str]:
    """Теги для строки 🎭 в карточке с учётом языка пользователя."""
    tags = parse_source_display_tags(event_data)
    if not tags:
        return []
    source = (event_data.get("source") or "").strip().lower()
    if source == "baliforum":
        return localize_baliforum_tags(tags, lang)
    return tags


class EventCategoryManager:
    """Единая точка категоризации событий для ingest и backfill."""

    def assign_categories(self, event_data: dict, source: str) -> list[str]:
        if source == "baliforum":
            return self._assign_baliforum(event_data)
        if source in USER_COMMUNITY_SOURCES:
            return []
        if source in EXTERNAL_API_SOURCES:
            raw_api = event_data.get("raw_api_category")
            return [str(raw_api).strip()] if raw_api else []
        return []

    def resolve_raw_category(self, event_data: dict, source: str) -> str | None:
        if source == "baliforum":
            tags = event_data.get("tags") or []
            if not tags:
                return None
            return ", ".join(str(t).strip() for t in tags if str(t).strip())
        if source in EXTERNAL_API_SOURCES:
            raw_api = event_data.get("raw_api_category")
            return str(raw_api).strip() if raw_api else None
        return None

    def _assign_baliforum(self, event_data: dict) -> list[str]:
        tags = event_data.get("tags") or []
        categories: list[str] = []
        for tag in tags:
            mapped = BALIFORUM_TAG_MAP.get(normalize_tag(str(tag)))
            if mapped:
                categories.append(mapped)
        return dedupe_categories(categories)
