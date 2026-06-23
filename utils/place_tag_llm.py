"""GPT-предложения доп. place_tags (разовый offline backfill)."""

from __future__ import annotations

import json
import logging
from typing import Any

from ai_utils import _make_client
from utils.place_tag_keywords import MISAPPLIED_FITNESS_TAGS, NON_FITNESS_PLACE_TYPES
from utils.place_tags import PLACE_TAGS_BY_CATEGORY, get_place_tag_slugs, normalize_tag_slug

logger = logging.getLogger(__name__)

MAX_LLM_EXTRAS = 2

_TAG_HINTS: dict[str, str] = {
    "acoustic_music": "live acoustic, singer-songwriter, jazz trio, unplugged — not a DJ nightclub",
    "dance": "dance floor, salsa/bachata/social dance lessons or parties — not yoga or gym",
    "club": "nightclub, DJ, late-night party venue",
    "bar": "cocktails, wine bar, mixology",
    "coffee_shop": "specialty coffee, roastery, espresso bar",
    "restaurant": "sit-down dining, fine dining",
    "street_food": "warung, food court, casual street eats",
    "beach_club": "beach club with pool/daybeds",
    "rooftop": "rooftop bar or restaurant",
    "lounge": "lounge seating, relaxed drinks",
    "workshop": "masterclass, hands-on creative session",
    "culture_art": "gallery, museum, art space",
    "yoga": "yoga, meditation, breathwork",
    "spa": "massage, spa treatments",
    "sauna": "sauna, banya, steam room",
    "gym": "fitness, weights, crossfit",
    "temple": "temple, pura",
    "waterfall": "waterfall hike destination",
    "cliff": "cliff viewpoint, rocks",
    "park": "park, rice terraces, garden walk",
    "trekking_trail": "hiking trail, trekking route",
    "beach": "beach (not beach club)",
    "activity": "quest involves exercise/workout AT this place — not that the venue IS a gym/spa/yoga studio",
}


def _collect_place_context(place) -> str:
    parts: list[str] = []
    for label, value in (
        ("name", getattr(place, "name", None)),
        ("name_en", getattr(place, "name_en", None)),
        ("description", getattr(place, "description", None)),
        ("task_hint", getattr(place, "task_hint", None)),
        ("task_hint_en", getattr(place, "task_hint_en", None)),
    ):
        text = (value or "").strip()
        if text:
            parts.append(f"{label}: {text}")
    return "\n".join(parts)


def _allowed_tags_for_category(category: str) -> frozenset[str]:
    return PLACE_TAGS_BY_CATEGORY.get((category or "").strip(), frozenset())


def _filter_llm_extras(place, raw_extras: Any, allowed: frozenset[str]) -> list[str]:
    already = set(get_place_tag_slugs(place))
    place_type = (getattr(place, "place_type", None) or "").strip()
    out: list[str] = []
    if not isinstance(raw_extras, list):
        return out
    for item in raw_extras:
        slug = normalize_tag_slug(str(item))
        if not slug:
            continue
        if place_type in NON_FITNESS_PLACE_TYPES and slug in MISAPPLIED_FITNESS_TAGS:
            slug = "activity"
        if not slug or slug not in allowed or slug in already or slug in out:
            continue
        out.append(slug)
        if len(out) >= MAX_LLM_EXTRAS:
            break
    return out


def _build_prompt(place, allowed: frozenset[str]) -> str:
    category = (getattr(place, "category", None) or "").strip()
    place_type = (getattr(place, "place_type", None) or "").strip() or "unknown"
    display = get_place_tag_slugs(place)
    tag_lines = []
    for slug in sorted(allowed):
        hint = _TAG_HINTS.get(slug)
        tag_lines.append(f"- {slug}" + (f" — {hint}" if hint else ""))

    return f"""Classify extra sub-tags for a quest bot place card.

Category: {category}
Primary place_type (already shown — do NOT repeat): {place_type}
Already displayed tags: {", ".join(display) if display else "(none)"}

Allowed extra slugs (pick 0–2 ONLY if clearly supported by the text):
{chr(10).join(tag_lines)}

Place data:
{_collect_place_context(place)}

Rules:
- Return ONLY extras not already covered by place_type or displayed tags.
- If one tag is enough, return an empty extras list.
- Prefer precision over coverage; when unsure, return [].
- acoustic_music: live/unplugged music, not DJ nightclub.
- dance: dancing/social dance/DJ dance floor; do not confuse with yoga or gym.
- club: nightclub/DJ venue; do not add club just because music is mentioned.
- activity: use when the QUEST asks for exercise/workout at a cafe/park/etc.;
  NEVER use gym/yoga/spa/sauna extras for non-fitness place_types — use activity instead.
- Never add bar to coworking unless bar is in the name.

Respond with JSON only: {{"extras": ["slug1"], "reason": "short explanation"}}"""


def propose_extra_tags_llm(place) -> tuple[list[str], list[str]]:
    """
    Предложить доп. slug через GPT-4o-mini.

    Возвращает (extras, reasons). Пустой список при ошибке или если модель не уверена.
    """
    category = (getattr(place, "category", None) or "").strip()
    allowed = _allowed_tags_for_category(category)
    if not allowed:
        return [], []

    client = _make_client()
    if not client:
        logger.warning("OPENAI_API_KEY не настроен — LLM place_tags пропущен")
        return [], []

    prompt = _build_prompt(place, allowed)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You assign place sub-tags for a travel quest bot. "
                        'Reply with valid JSON only: {"extras": [...], "reason": "..."}.'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=120,
            response_format={"type": "json_object"},
            timeout=20,
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("LLM place_tags для «%s»: %s", getattr(place, "name", "?"), exc)
        return [], []

    extras = _filter_llm_extras(place, parsed.get("extras"), allowed)
    reason = str(parsed.get("reason") or "").strip()
    if not extras:
        return [], [reason] if reason else []

    reasons = [f"llm: {reason or extras[0]}"]
    return extras, reasons
