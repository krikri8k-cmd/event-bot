"""Подкатегории мест (place_tags + legacy place_type) для карточек 🎭."""

from __future__ import annotations

import html
import json
import re
from typing import Any

# Канон по категориям (для справки / валидации; фильтр списка — по category).
PLACE_TAGS_BY_CATEGORY: dict[str, frozenset[str]] = {
    "food": frozenset(
        {
            "restaurant",
            "cafe",
            "coffee_shop",
            "street_food",
            "bar",
            "coworking",
            "acoustic_music",
            "dance",
            "activity",
        }
    ),
    "health": frozenset({"gym", "yoga", "spa", "sauna", "activity", "pilates"}),
    "places": frozenset({"cliff", "waterfall", "temple", "park", "trekking_trail", "culture_art", "activity"}),
    "entertainment": frozenset(
        {
            "beach_club",
            "beach",
            "club",
            "rooftop",
            "lounge",
            "workshop",
            "culture_art",
            "acoustic_music",
            "dance",
            "activity",
            "river_club",
        }
    ),
}

# Старые place_type в БД → slug подкатегории для отображения.
LEGACY_PLACE_TYPE_TO_TAG: dict[str, str] = {
    "street_food": "street_food",
    "market": "street_food",
    "bakery": "cafe",
    "coffee_shop": "coffee_shop",
    "yoga_studio": "yoga",
    "nature": "park",
    "lab": "spa",
    "clinic": "spa",
    "exhibition": "culture_art",
    "culture": "culture_art",
    "trail": "trekking_trail",
    "viewpoint": "cliff",
    "beach_party": "beach_club",
    "nightclub": "club",
    "live_music": "club",
    "show_event": "workshop",
    "workshop_trip": "workshop",
    "karaoke": "club",
}


def normalize_tag_slug(raw: str) -> str:
    slug = (raw or "").strip().lower().replace("-", "_")
    slug = re.sub(r"[^a-z0-9_]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


def _parse_place_tags_raw(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [normalize_tag_slug(str(x)) for x in raw if str(x).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [normalize_tag_slug(str(x)) for x in parsed if str(x).strip()]
            except json.JSONDecodeError:
                pass
        return [normalize_tag_slug(x) for x in text.split(",") if x.strip()]
    return []


def get_place_tag_slugs(place) -> list[str]:
    """Уникальные slug подкатегорий: сначала place_type, затем place_tags."""
    seen: set[str] = set()
    out: list[str] = []

    def add(raw: str) -> None:
        slug = normalize_tag_slug(raw)
        if not slug or slug in seen:
            return
        seen.add(slug)
        out.append(slug)

    place_type = (getattr(place, "place_type", None) or "").strip()
    if place_type:
        add(LEGACY_PLACE_TYPE_TO_TAG.get(place_type, place_type))

    for slug in _parse_place_tags_raw(getattr(place, "place_tags", None)):
        add(slug)

    return out


def format_place_tag_label(slug: str, lang: str) -> str:
    from utils.i18n import t

    key = f"tasks.place_tag.{slug}"
    label = t(key, lang)
    if label == key:
        return slug.replace("_", " ").title()
    return label


def format_place_categories_line_html(place, lang: str) -> str:
    """Строка карточки: 🎭 Tag1 / Tag2 (как у событий)."""
    slugs = get_place_tag_slugs(place)
    if not slugs:
        return ""
    labels = [html.escape(format_place_tag_label(s, lang)) for s in slugs]
    return f"🎭 {' / '.join(labels)}"


def parse_tags_comment_line(line: str) -> list[str] | None:
    """Парсит `# tags gym, cafe` из mirror-файла."""
    m = re.match(r"^\s*#\s*tags?\s+(.+)\s*$", line.strip(), re.I)
    if not m:
        return None
    return [normalize_tag_slug(x) for x in m.group(1).split(",") if x.strip()]
