#!/usr/bin/env python3
"""Найти TikTok /video/ для task_places; фильтр по релевантности (название + Bali + category).

Зависимость: pip install -e \".[scripts]\"  (пакет ddgs)

Пример:
  python scripts/fetch_tiktok_review_urls.py --region bali --category food --dry-run
  python scripts/fetch_tiktok_review_urls.py --region bali --category food --apply
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_TIKTOK_VIDEO_RE = re.compile(r"https?://(?:www\.)?tiktok\.com/@[^/]+/video/\d+", re.I)

_FOOD_SIGNALS = frozenset(
    {
        "bali",
        "canggu",
        "ubud",
        "seminyak",
        "berawa",
        "umalas",
        "denpasar",
        "badung",
        "uluwatu",
        "pecatu",
        "cafe",
        "coffee",
        "restaurant",
        "resto",
        "food",
        "warung",
        "bistro",
        "brunch",
        "breakfast",
        "dinner",
        "lunch",
        "eat",
        "eats",
        "kuliner",
        "makan",
        "review",
        "spot",
        "menu",
        "balifood",
        "balieats",
        "balirestaurant",
        "dining",
    }
)

_NEGATIVE = (
    "slavic roots🤣",
    "can't change our roots",
    "cannot change our roots",
    "change our roots",
    "ancestral tradition",
    "slavic parenting",
    "slavic pagan",
    "hotel ",
    "apartment",
    "apartemen",
    "resort ",
    "new bern",
    "taytay",
    "batangas",
    "khao yai",
    "chatelet",
    "san cataldo",
    "kuningan jaksel",
    "harmoni one",
    "minoa by kozystay",
    "travemunde",
    "travem",
    "monti di creta",
    "€",
    "fruhstuck",
    "frühstück",
    "germany",
    "deutschland",
    "italy",
    "italia",
    "manila",
    "batam",
)

_BALI_MARKERS = frozenset({"bali", "indonesia", "badung", "denpasar", "80361", "80353", "80571"})

_HEALTH_SIGNALS = frozenset(
    {
        "bali",
        "canggu",
        "ubud",
        "seminyak",
        "berawa",
        "umalas",
        "denpasar",
        "badung",
        "uluwatu",
        "pecatu",
        "gym",
        "fitness",
        "workout",
        "training",
        "crossfit",
        "hyrox",
        "pilates",
        "yoga",
        "spa",
        "massage",
        "wellness",
        "recovery",
        "studio",
        "club",
        "balispa",
        "balifitness",
        "review",
        "flower bath",
        "jacuzzi",
        "sauna",
        "facial",
        "treatment",
    }
)

_PLACES_SIGNALS = frozenset(
    {
        "bali",
        "canggu",
        "ubud",
        "seminyak",
        "berawa",
        "umalas",
        "denpasar",
        "badung",
        "uluwatu",
        "pecatu",
        "nusa",
        "penida",
        "temple",
        "pura",
        "kecak",
        "beach",
        "pantai",
        "cliff",
        "tebing",
        "sunset",
        "viewpoint",
        "view",
        "park",
        "garden",
        "gallery",
        "art",
        "museum",
        "culture",
        "hike",
        "trail",
        "travel",
        "tourist",
        "attraction",
        "hidden",
        "balitravel",
        "explorebali",
        "thingstodo",
        "vlog",
        "guide",
        "review",
        "spot",
        "visit",
    }
)

_ENTERTAINMENT_SIGNALS = frozenset(
    {
        "bali",
        "canggu",
        "ubud",
        "seminyak",
        "berawa",
        "umalas",
        "denpasar",
        "badung",
        "uluwatu",
        "pecatu",
        "jimbaran",
        "nusa",
        "beach",
        "club",
        "beachclub",
        "party",
        "pool",
        "dayclub",
        "nightlife",
        "rooftop",
        "bar",
        "lounge",
        "dj",
        "sunset",
        "drinks",
        "cocktail",
        "dayparty",
        "finns",
        "atlas",
        "brisa",
        "cliffhouse",
        "balinightlife",
        "baliparty",
        "baliclub",
        "review",
        "vlog",
        "spot",
    }
)

_CATEGORY_SIGNALS = {
    "food": _FOOD_SIGNALS,
    "health": _HEALTH_SIGNALS,
    "places": _PLACES_SIGNALS,
    "entertainment": _ENTERTAINMENT_SIGNALS,
}

_STOP = frozenset({"bali", "the", "and", "ubud", "canggu", "kerobokan"})

# Одно слово — только район; без уникального названия матч почти всегда ложный.
_GENERIC_ONLY = frozenset(
    {"bukit", "ubud", "canggu", "seminyak", "berawa", "umalas", "denpasar", "uluwatu", "pecatu", "kuta"}
)

# Одно слово — слишком общее для nightlife; без handle/сильного контекста не берём.
_WEAK_SINGLE_TOKENS = frozenset({"lawn", "pool", "zone", "bar", "club", "beach"})

MIN_SCORE = 35


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text.lower()).strip()


def _name_tokens(place_name: str) -> list[str]:
    short = place_name.split("(")[0].strip()
    raw = re.findall(r"[a-z0-9\u0080-\uFFFF]{3,}", short.lower())
    tokens: list[str] = []
    for part in raw:
        norm = _normalize(part)
        if len(norm) >= 3 and norm not in _STOP:
            tokens.append(norm)
    if not tokens:
        norm = _normalize(short)
        if len(norm) >= 3:
            tokens.append(norm)
    return tokens


def _area_hints(place_name: str) -> list[str]:
    hints: list[str] = []
    lower = place_name.lower()
    for area in (
        "canggu",
        "ubud",
        "umalas",
        "berawa",
        "seminyak",
        "denpasar",
        "uluwatu",
        "pecatu",
        "balangan",
        "bingin",
        "padang",
        "nyang",
        "nunggalan",
        "jimbaran",
        "regent",
    ):
        if area in lower:
            hints.append(area)
    if "ulu" in lower and "uluwatu" not in hints:
        hints.append("uluwatu")
    return hints


def _is_vague_place_name(name: str) -> bool:
    norm = _normalize(name)
    return any(
        v in norm
        for v in (
            "cliff overlooking",
            "overlooking the ocean",
        )
    )


def _places_kind(name: str) -> str:
    lower = name.lower()
    if any(k in lower for k in ("pura", "temple", "kecak")):
        return "temple"
    if any(k in lower for k in ("beach", "pantai", "kuakua")):
        return "beach"
    if any(k in lower for k in ("cliff", "tebing", "sunset", "camping", "tebing")):
        return "cliff"
    if any(k in lower for k in ("gallery", "art", "studio", "museum", "taman ujung")):
        return "culture"
    if any(k in lower for k in ("park", "garden", "dogville", "ganesha")):
        return "park"
    return "generic"


def _entertainment_kind(name: str) -> str:
    lower = name.lower()
    if "rooftop" in lower:
        return "rooftop"
    if any(k in lower for k in ("lounge", "chill", "movie", "cliffhouse")):
        return "lounge"
    if any(
        k in lower
        for k in (
            "beach",
            "club",
            "finns",
            "atlas",
            "brisa",
            "lawn",
            "lyma",
            "jungle",
            "ocean",
            "kubu",
        )
    ):
        return "beach_party"
    if "bar" in lower:
        return "bar"
    return "generic"


def _score_result(place_name: str, region: str, row: dict, category: str = "food") -> int:
    title = row.get("title") or ""
    body = row.get("body") or ""
    href = row.get("href") or ""
    text = _normalize(f"{title} {body} {href}")
    tokens = _name_tokens(place_name)

    if len(tokens) == 1 and tokens[0] in _GENERIC_ONLY:
        return 0

    if region.lower() == "bali" and not any(m in text for m in _BALI_MARKERS):
        return 0

    score = 0
    matched = sum(1 for t in tokens if t in text)
    if tokens:
        if len(tokens) >= 2:
            if matched < len(tokens):
                return 0
            score += 40
        elif matched >= 1:
            score += 35

    if region.lower() in text or "bali" in text:
        score += 18

    for area in _area_hints(place_name):
        if area in text:
            score += 10

    signals = _CATEGORY_SIGNALS.get(category, _FOOD_SIGNALS)
    signal_hits = sum(1 for sig in signals if sig in text)
    score += min(signal_hits * 4, 28)
    if category in _CATEGORY_SIGNALS and signal_hits == 0:
        return 0

    handle_m = re.search(r"tiktok\.com/@([^/]+)", href, re.I)
    handle_bonus = 0
    if handle_m:
        handle = _normalize(handle_m.group(1)).replace("_", "").replace(".", "")
        for t in tokens:
            compact = t.replace(" ", "")
            if compact in handle or handle in compact:
                handle_bonus = 22
                score += handle_bonus

    if (
        category == "entertainment"
        and len(tokens) == 1
        and tokens[0] in _WEAK_SINGLE_TOKENS
        and handle_bonus == 0
        and signal_hits < 2
    ):
        return 0

    for neg in _NEGATIVE:
        if neg in text:
            score -= 50

    place_norm = _normalize(place_name)
    if "cliffhouse" in text and "cliffhouse" not in place_norm:
        score -= 45
    if "ulu cliffhouse" in text and "cliffhouse" not in place_norm:
        score -= 45

    return score


def _pick_best_video(
    results: list[dict], place_name: str, region: str, category: str = "food"
) -> tuple[str | None, int]:
    best_url: str | None = None
    best_score = 0
    for row in results:
        href = (row.get("href") or "").split("?")[0].rstrip("/")
        if "/discover/" in href.lower():
            continue
        m = _TIKTOK_VIDEO_RE.match(href)
        if not m:
            continue
        score = _score_result(place_name, region, row, category)
        if score > best_score:
            best_score = score
            best_url = m.group(0)
    if best_score >= MIN_SCORE:
        return best_url, best_score
    return None, best_score


def _is_spa_place(name: str) -> bool:
    lower = name.lower()
    return any(k in lower for k in ("spa", "massage", "wellness", "senses")) and "gym" not in lower


def _build_queries(place_name: str, region: str, category: str = "food") -> list[str]:
    short = place_name.split("(")[0].strip()
    areas = _area_hints(place_name)
    area_part = f" {areas[0]}" if areas else " Canggu"

    if category == "health":
        if _is_spa_place(place_name):
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} spa massage',
                f'site:tiktok.com "{short}" {region.title()} spa #balispa',
                f'site:tiktok.com "{short}" Badung {region.title()} wellness',
                f"site:tiktok.com {short}{area_part} {region.title()} flower bath",
            ]
        return [
            f'site:tiktok.com "{short}"{area_part} {region.title()} gym fitness',
            f'site:tiktok.com "{short}" {region.title()} workout #balifitness',
            f'site:tiktok.com "{short}" Badung {region.title()} gym review',
            f"site:tiktok.com {short}{area_part} {region.title()} crossfit pilates",
        ]

    if category == "places":
        area_part = f" {areas[0]}" if areas else " Bali"
        kind = _places_kind(short)
        if kind == "temple":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} temple pura',
                f'site:tiktok.com "{short}" {region.title()} kecak sunset',
                f'site:tiktok.com "{short}" Badung {region.title()} temple visit',
                f"site:tiktok.com {short}{area_part} {region.title()} balitravel",
            ]
        if kind == "beach":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} beach pantai',
                f'site:tiktok.com "{short}" {region.title()} beach #explorebali',
                f'site:tiktok.com "{short}" Uluwatu {region.title()} hidden beach',
                f"site:tiktok.com {short}{area_part} {region.title()} bali beach vlog",
            ]
        if kind == "cliff":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} cliff sunset',
                f'site:tiktok.com "{short}" Uluwatu {region.title()} cliff jump',
                f'site:tiktok.com "{short}" {region.title()} viewpoint #balitravel',
                f"site:tiktok.com {short}{area_part} {region.title()} tebing bali",
            ]
        if kind == "culture":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} art gallery',
                f'site:tiktok.com "{short}" {region.title()} museum culture',
                f'site:tiktok.com "{short}" Ubud {region.title()} gallery visit',
                f"site:tiktok.com {short}{area_part} {region.title()} bali art",
            ]
        if kind == "park":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} park garden',
                f'site:tiktok.com "{short}" {region.title()} garden visit #explorebali',
                f'site:tiktok.com "{short}" Badung {region.title()} park vlog',
                f"site:tiktok.com {short}{area_part} {region.title()} bali hidden gem",
            ]
        return [
            f'site:tiktok.com "{short}"{area_part} {region.title()} travel vlog',
            f'site:tiktok.com "{short}" {region.title()} #explorebali #balitravel',
            f'site:tiktok.com "{short}" Badung {region.title()} things to do',
            f"site:tiktok.com {short}{area_part} {region.title()} bali guide",
        ]

    if category == "entertainment":
        area_part = f" {areas[0]}" if areas else " Canggu"
        kind = _entertainment_kind(short)
        if kind == "rooftop":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} rooftop bar',
                f'site:tiktok.com "{short}" {region.title()} sunset rooftop #balinightlife',
                f'site:tiktok.com "{short}" Berawa {region.title()} rooftop review',
                f"site:tiktok.com {short}{area_part} {region.title()} cocktail bar",
            ]
        if kind == "lounge":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} lounge bar',
                f'site:tiktok.com "{short}" Uluwatu {region.title()} cliff lounge',
                f'site:tiktok.com "{short}" {region.title()} chill lounge #baliclub',
                f"site:tiktok.com {short}{area_part} {region.title()} bali nightlife",
            ]
        if kind == "beach_party":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} beach club party',
                f'site:tiktok.com "{short}" {region.title()} day club pool #baliparty',
                f'site:tiktok.com "{short}" Canggu {region.title()} beach club review',
                f"site:tiktok.com {short}{area_part} {region.title()} fins atlas brisa",
            ]
        if kind == "bar":
            return [
                f'site:tiktok.com "{short}"{area_part} {region.title()} bar cocktail',
                f'site:tiktok.com "{short}" {region.title()} sunset bar #balinightlife',
                f'site:tiktok.com "{short}" Jimbaran {region.title()} bar review',
                f"site:tiktok.com {short}{area_part} {region.title()} bali bar vlog",
            ]
        return [
            f'site:tiktok.com "{short}"{area_part} {region.title()} nightlife club',
            f'site:tiktok.com "{short}" {region.title()} #balinightlife #baliclub',
            f'site:tiktok.com "{short}" Badung {region.title()} party review',
            f"site:tiktok.com {short}{area_part} {region.title()} bali vlog",
        ]

    return [
        f'site:tiktok.com "{short}"{area_part} {region.title()} cafe food',
        f'site:tiktok.com "{short}" {region.title()} restaurant #balifood',
        f'site:tiktok.com "{short}" Badung {region.title()}',
        f"site:tiktok.com {short}{area_part} {region.title()} balieats",
        f'site:tiktok.com "{short}" {region.title()} restaurant review',
    ]


def _search_tiktok(ddgs, place_name: str, region: str, category: str = "food") -> tuple[str | None, int]:
    best_url: str | None = None
    best_score = 0
    seen: set[str] = set()

    for q in _build_queries(place_name, region, category):
        try:
            results = list(ddgs.text(q, max_results=10))
        except Exception:
            continue
        for row in results:
            href = (row.get("href") or "").split("?")[0].rstrip("/")
            if href in seen:
                continue
            seen.add(href)
        url, score = _pick_best_video(results, place_name, region, category)
        if score > best_score:
            best_score = score
            best_url = url
        if best_score >= MIN_SCORE + 15:
            break
    return best_url, best_score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="bali")
    parser.add_argument("--category", default="food")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=0.8, help="pause between searches")
    parser.add_argument(
        "--out",
        default="",
        help="CSV path (default: scripts/tiktok_reviews_{category}_{region}.csv)",
    )
    parser.add_argument("--apply", action="store_true", help="write review_url to DB")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--refresh-tiktok",
        action="store_true",
        help="re-fetch for places that already have tiktok.com review_url",
    )
    parser.add_argument(
        "--clear-if-unmatched",
        action="store_true",
        help="set review_url=NULL when no video passes score threshold",
    )
    args = parser.parse_args()

    from ddgs import DDGS

    from config import load_settings
    from database import TaskPlace, get_session, init_engine

    init_engine(load_settings(require_bot=False).database_url)

    with get_session() as session:
        q = session.query(TaskPlace).filter(
            TaskPlace.is_active.is_(True),
            TaskPlace.region == args.region,
            TaskPlace.category == args.category,
        )
        places = q.order_by(TaskPlace.name).all()

        if args.refresh_tiktok:
            targets = [
                p
                for p in places
                if "tiktok.com" in (p.review_url or "").lower() and (p.name or "").strip() != "Место на карте"
            ]
        else:
            targets = [
                p
                for p in places
                if not (p.review_url or "").strip()
                and (p.name or "").strip() != "Место на карте"
                and not (args.category == "places" and _is_vague_place_name(p.name or ""))
            ]
        if args.limit:
            targets = targets[: args.limit]

        out_path = Path(args.out) if args.out else Path(f"scripts/tiktok_reviews_{args.category}_{args.region}.csv")
        if not out_path.is_absolute():
            out_path = PROJECT_ROOT / out_path

        rows: list[dict[str, str]] = []
        found = 0
        cleared = 0
        missed: list[str] = []

        with DDGS() as ddgs:
            for i, place in enumerate(targets, 1):
                old = (place.review_url or "").strip()
                url, score = _search_tiktok(ddgs, place.name, args.region, args.category)
                print(f"[{i}/{len(targets)}] id={place.id} | {place.name} | score={score}")
                if url:
                    changed = url != old
                    mark = "UPD" if changed else "same"
                    print(f"  -> [{mark}] {url}")
                    found += 1
                    rows.append(
                        {
                            "place_id": str(place.id),
                            "review_url": url,
                            "place_name": place.name,
                            "score": str(score),
                            "old_review_url": old,
                        }
                    )
                else:
                    print(f"  -> NOT FOUND (best score {score} < {MIN_SCORE})")
                    missed.append(f"{place.id}:{place.name}:{score}")
                    if args.clear_if_unmatched and old:
                        rows.append(
                            {
                                "place_id": str(place.id),
                                "review_url": "",
                                "place_name": place.name,
                                "score": str(score),
                                "old_review_url": old,
                            }
                        )
                if args.sleep and i < len(targets):
                    time.sleep(args.sleep)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["place_id", "review_url", "place_name", "score", "old_review_url"],
            )
            writer.writeheader()
            writer.writerows(rows)

        print(f"\nSaved -> {out_path}")
        print(f"Matched: {found}/{len(targets)}")
        if missed:
            print(f"Missed ({len(missed)}):")
            for line in missed[:25]:
                print(f"  - {line}")

        if args.apply and not args.dry_run:
            applied = 0
            for row in rows:
                place = session.get(TaskPlace, int(row["place_id"]))
                if not place:
                    continue
                new_url = (row.get("review_url") or "").strip()
                if new_url:
                    place.review_url = new_url
                    applied += 1
                elif args.clear_if_unmatched and (place.review_url or "").strip():
                    place.review_url = None
                    cleared += 1
            session.commit()
            print(f"Applied to DB: {applied}, cleared: {cleared}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
