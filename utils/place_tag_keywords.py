"""Эвристики для предложения доп. place_tags (только extras, не place_type)."""

from __future__ import annotations

import re
from typing import Any

from utils.place_tags import PLACE_TAGS_BY_CATEGORY, _parse_place_tags_raw, get_place_tag_slugs, normalize_tag_slug

# tag -> keywords (RU/EN, lower-case matching)
TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sauna": ("сауна", "сауну", "баня", "баню", "хамам", "hamam", "sauna", "banya", "steam room", "банный"),
    "yoga": ("йога", "медитация", "yoga", "meditation", "pranayama", "breathwork", "sound healing"),
    "coffee_shop": (
        "кофейня",
        "coffee shop",
        "specialty coffee",
        "спешелти",
        "espresso bar",
        "roastery",
        "обжарка",
        "coffee",
        "кофе",
    ),
    "coworking": ("коворкинг", "coworking", "workspace", "work space", "hot desk", "ноутбук", "розетк"),
    "waterfall": ("водопад", "waterfall", "air terjun", "curug"),
    "trekking_trail": ("трекинг", "тропа", "хайкинг", "trekking", "hiking", "trail", "поход"),
    "street_food": ("стритфуд", "street food", "warung", "фудкорт", "food court", "night market"),
    "beach_club": ("beach club", "пляжный клуб", "beachclub"),
    "spa": ("спа", " spa ", "spa day", "massage", "массаж"),
    "temple": ("храм", "temple", " pura", "pura ", "пура"),
    "cliff": ("утес", "утёс", "cliff", "скал", "скала"),
    "culture_art": ("галерея", "gallery", "museum", "музей", "art space", "выставк", "art center"),
    "rooftop": ("rooftop", "roof top", "на крыше", "sky bar"),
    "lounge": ("lounge", "лаунж"),
    "workshop": ("мастер-класс", "masterclass", "workshop", "воркшоп"),
    "bar": ("бар", "cocktail", "коктейль", "mixology"),
    "restaurant": ("ресторан", "restaurant", "restaur", "fine dining", "degustation", "borscht", "ramen", "steakhouse"),
    "gym": ("фитнес", "fitness", "тренажер", "тренажёр", "crossfit", "gym"),
    "beach": ("пляж", " beach", "beachfront"),
    "club": ("nightclub", "night club", "клуб", " dj ", "dance floor"),
    "park": ("парк", " park", "rice terrace", "рисовые террасы", "сад"),
    "acoustic_music": (
        "acoustic",
        "акустик",
        "live music",
        "живая музыка",
        "unplugged",
        "singer-songwriter",
        "jazz night",
        "open mic",
    ),
    "dance": (
        "salsa",
        "bachata",
        "social dance",
        "dance class",
        "dance floor",
        "танц",
        "танцы",
        "dancing",
    ),
    "activity": (
        "зарядк",
        "упражнен",
        "workout",
        "exercise",
        "active day",
        "активн",
        "спортивн",
        "after workout",
        "после тренировки",
        "outdoor exercise",
        "на свежем воздухе",
        "group workout",
        "группов",
        "тренировк",
    ),
    "river_club": ("river club", "riverclub", "речк", "river view", "на реке", "by the river"),
}

# Короткие токены — только по границе слова, чтобы не ловить espresso → spa и т.п.
_WORD_BOUNDARY_TAGS = frozenset({"spa", "bar", "club", "park", "gym"})


def _collect_place_text(place) -> str:
    parts = [
        getattr(place, "name", None),
        getattr(place, "name_en", None),
        getattr(place, "description", None),
        getattr(place, "task_hint", None),
        getattr(place, "task_hint_en", None),
    ]
    text = " ".join(str(p).strip() for p in parts if p and str(p).strip())
    return f" {text.lower()} "


def _keyword_matches(text: str, keyword: str, tag: str) -> bool:
    kw = keyword.lower().strip()
    if not kw:
        return False
    if tag in _WORD_BOUNDARY_TAGS and " " not in kw:
        return re.search(rf"(?<![a-zа-яё0-9]){re.escape(kw)}(?![a-zа-яё0-9])", text, re.I) is not None
    return kw in text


def _allowed_tags_for_category(category: str) -> frozenset[str]:
    return PLACE_TAGS_BY_CATEGORY.get((category or "").strip(), frozenset())


# Не предлагать extra, если display уже покрыт «родительским» тегом.
SKIP_EXTRA_IF_DISPLAY_HAS: dict[str, frozenset[str]] = {
    "beach": frozenset({"beach_club", "beach"}),
}

# place_type → extras, которые не предлагать без явного упоминания в названии.
PLACE_TYPE_EXTRA_BLOCKLIST: dict[str, frozenset[str]] = {
    "coworking": frozenset({"bar"}),
    "cafe": frozenset({"gym", "yoga", "spa", "sauna"}),
    "park": frozenset({"gym", "yoga", "spa", "sauna"}),
    "restaurant": frozenset({"gym", "yoga", "spa", "sauna"}),
    "temple": frozenset({"gym", "yoga", "spa", "sauna", "park"}),
    "culture": frozenset({"gym", "yoga", "spa", "sauna"}),
    "beach": frozenset({"gym", "yoga", "spa", "sauna"}),
    "gym": frozenset({"activity"}),
    "pilates": frozenset({"activity"}),
    "spa": frozenset({"activity"}),
    "sauna": frozenset({"activity"}),
    "yoga_studio": frozenset({"activity"}),
}

# place_type заведения ≠ фитнес-локация; workout в hint → activity, не gym/yoga/spa.
NON_FITNESS_PLACE_TYPES: frozenset[str] = frozenset(
    {
        "cafe",
        "park",
        "restaurant",
        "temple",
        "culture",
        "beach",
        "coworking",
        "street_food",
        "market",
        "bakery",
        "nature",
        "viewpoint",
        "lounge",
        "rooftop",
    }
)

MISAPPLIED_FITNESS_TAGS: frozenset[str] = frozenset({"gym", "yoga", "spa", "sauna"})


def propose_extra_tags(place) -> tuple[list[str], list[str]]:
    """
    Предложить доп. slug для place_tags.

    Возвращает (новые_теги, причины). Не включает place_type и уже отображаемые теги.
    """
    category = (getattr(place, "category", None) or "").strip()
    allowed = _allowed_tags_for_category(category)
    if not allowed:
        return [], []

    already = set(get_place_tag_slugs(place))
    current_extras = set(_parse_place_tags_raw(getattr(place, "place_tags", None)))
    text = _collect_place_text(place)
    place_type = (getattr(place, "place_type", None) or "").strip()
    name_lower = (getattr(place, "name", None) or "").lower()

    proposed: list[str] = []
    reasons: list[str] = []

    for tag in sorted(TAG_KEYWORDS):
        if tag not in allowed:
            continue
        if tag in already or tag in current_extras:
            continue
        blocked = SKIP_EXTRA_IF_DISPLAY_HAS.get(tag)
        if blocked and already.intersection(blocked):
            continue
        blocked_for_type = PLACE_TYPE_EXTRA_BLOCKLIST.get(place_type)
        if blocked_for_type and tag in blocked_for_type and tag not in name_lower:
            continue
        hits = [kw for kw in TAG_KEYWORDS[tag] if _keyword_matches(text, kw, tag)]
        if hits:
            proposed.append(tag)
            reasons.append(f"{tag}: «{hits[0]}»")

    # Явные маркеры в названии (name / name_en)
    name_text = f" {(getattr(place, 'name', None) or '')} {(getattr(place, 'name_en', None) or '')} ".lower()
    for tag, needles, label in (
        ("bar", ("& bar", " bar", "bar ", "cocktail bar", "wine bar"), "name"),
        ("restaurant", ("restaurant", "restaur", "reštaur", "steakhouse"), "name"),
        ("street_food", ("warung",), "name"),
        ("lounge", ("lounge",), "name"),
        ("coworking", ("coworking", "co-working", "коворкинг"), "name"),
        ("beach_club", ("beach club", "beachclub"), "name"),
    ):
        if tag not in allowed or tag in proposed or tag in already or tag in current_extras:
            continue
        blocked = SKIP_EXTRA_IF_DISPLAY_HAS.get(tag)
        if blocked and already.intersection(blocked):
            continue
        if any(n in name_text for n in needles):
            proposed.append(tag)
            reasons.append(f"{tag}: {label}")

    # workout в hint у кафе/парка и т.п. → activity, не gym/yoga/spa
    if place_type in NON_FITNESS_PLACE_TYPES and "activity" in allowed:
        fitness_blocked = [t for t in proposed if t in MISAPPLIED_FITNESS_TAGS]
        if fitness_blocked or (
            not proposed and any(_keyword_matches(text, kw, "activity") for kw in TAG_KEYWORDS["activity"])
        ):
            if fitness_blocked:
                proposed = [t for t in proposed if t not in MISAPPLIED_FITNESS_TAGS]
                reasons = [r for r in reasons if r.split(":")[0] not in MISAPPLIED_FITNESS_TAGS]
            if "activity" not in proposed and "activity" not in already and "activity" not in current_extras:
                hits = [kw for kw in TAG_KEYWORDS["activity"] if _keyword_matches(text, kw, "activity")]
                if hits:
                    proposed.append("activity")
                    reasons.append(f"activity: «{hits[0]}» (not gym/yoga at {place_type})")

    return proposed, reasons


def merge_place_tags(place, extra_slugs: list[str]) -> list[str]:
    """Объединить текущие place_tags с новыми extras (без дублей)."""
    merged: list[str] = []
    seen: set[str] = set()

    for raw in _parse_place_tags_raw(getattr(place, "place_tags", None)):
        slug = normalize_tag_slug(raw)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        merged.append(slug)

    already = set(get_place_tag_slugs(place))
    for raw in extra_slugs:
        slug = normalize_tag_slug(raw)
        if not slug or slug in seen or slug in already:
            continue
        seen.add(slug)
        merged.append(slug)

    return merged


def place_tags_is_empty(raw: Any) -> bool:
    return len(_parse_place_tags_raw(raw)) == 0
