"""Определение системных категорий событий по данным источника."""

from __future__ import annotations

# Источники пользовательских / community-событий — классификация позже.
USER_COMMUNITY_SOURCES = frozenset({"user", "community"})

# Источники с категорией из API (маппинг добавится позже).
EXTERNAL_API_SOURCES = frozenset({"megatix", "savaya", "google_calendar"})

BALIFORUM_TAG_MAP: dict[str, str] = {
    "выставка": "Выставка",
    "искусство": "Выставка",
    "фестиваль": "Выставка",
    "йога": "Духовное",
    "бизнес": "Бизнес",
    "it": "IT",
    "вечеринка": "Вечеринка",
    "еда": "Еда",
}


def normalize_tag(tag: str) -> str:
    return tag.strip().lower()


def dedupe_categories(categories: list[str]) -> list[str]:
    return list(dict.fromkeys(categories))


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
