# check_render.py
from __future__ import annotations

import html
import logging
from math import ceil
from urllib.parse import quote_plus, urlparse

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
log = logging.getLogger("check")

# ---------- URL helpers ----------
BLACKLIST_DOMAINS = {"example.com", "example.org", "example.net"}


def sanitize_url(u: str | None) -> str | None:
    if not u:
        return None
    try:
        p = urlparse(u)
    except Exception:
        return None
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = p.netloc.lower()
    if any(host == d or host.endswith("." + d) for d in BLACKLIST_DOMAINS):
        return None
    if "calendar.google.com" in host and "eid=" not in u:
        return None
    return u


def get_source_url(e: dict) -> str | None:
    t = e.get("type")
    candidates: list[str | None]
    if t == "source":
        candidates = [e.get("source_url")]
    elif t == "user":
        candidates = [e.get("author_url"), e.get("chat_url")]
    elif t in ("ai", "ai_generated"):
        candidates = [e.get("location_url")]  # может быть None
    else:
        candidates = [e.get("source_url")]
    for u in candidates:
        u = sanitize_url(u)
        if u:
            return u
    return None


# ---------- Location helpers ----------
def build_maps_url(e: dict) -> str:
    name = (e.get("venue_name") or "").strip()
    addr = (e.get("address") or "").strip()
    lat, lng = e.get("lat"), e.get("lng")
    if name:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(name)}"
    if addr:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(addr)}"
    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    return "https://www.google.com/maps"


def enrich_venue_name(e: dict) -> dict:
    # очень простой извлекатель из title/description
    import re

    if e.get("venue_name"):
        return e
    for fld in ("title", "description"):
        text = e.get(fld) or ""
        m = re.search(r"(?:в|at|@)\s*([A-Za-zА-Яа-я0-9''&\s.-]+)$", text)
        if m:
            e["venue_name"] = m.group(1).strip()
            break
    return e


# ---------- Pipeline ----------
def prepare_events_for_feed(events: list[dict]) -> list[dict]:
    out = []
    for e in events:
        if e.get("type") == "source":
            ok = sanitize_url(e.get("source_url"))
            if not ok:
                log.warning(
                    "skip source invalid | title=%s url=%s", e.get("title"), e.get("source_url")
                )
                continue
            e["source_url"] = ok
        out.append(enrich_venue_name(e))
    return out


def group_by_type(events: list[dict]):
    return {
        "moment": [e for e in events if e.get("type") == "moment"],
        "user": [e for e in events if e.get("type") == "user"],
        "source": [e for e in events if e.get("type") == "source"],
        "ai": [e for e in events if e.get("type") in ("ai", "ai_generated")],
    }


def make_counts(groups: dict) -> dict:
    total = sum(len(v) for v in groups.values())
    return {
        "all": total,
        "moments": len(groups["moment"]),
        "user": len(groups["user"]),
        "sources": len(groups["source"]),
        "ai": len(groups["ai"]),
    }


def render_header(counts: dict) -> str:
    rows = [f"🗺 Найдено рядом: <b>{counts['all']}</b>"]
    if counts["moments"]:
        rows.append(f"• ⚡ Мгновенные: {counts['moments']}")
    if counts["user"]:
        rows.append(f"• 👥 От пользователей: {counts['user']}")
    if counts["sources"]:
        rows.append(f"• 🌐 Из источников: {counts['sources']}")
    if counts["ai"]:
        rows.append(f"• 🤖 AI: {counts['ai']}")
    return "\n".join(rows)


def render_event_html(e: dict, idx: int) -> str:
    title = html.escape(e.get("title", "Событие"))
    when = e.get("when_str", "")
    dist = f"{e['distance_km']:.1f} км" if e.get("distance_km") is not None else ""
    venue = html.escape(e.get("venue_name") or e.get("address") or "Локация уточняется")
    src = get_source_url(e)
    src_part = f'🔗 <a href="{html.escape(src)}">Источник</a>' if src else "ℹ️ Источник не указан"
    map_part = f'<a href="{build_maps_url(e)}">Маршрут</a>'
    return f"{idx}) <b>{title}</b> — {when} ({dist})\n📍 {venue}\n{src_part}  🚗 {map_part}\n"


def render_page(events: list[dict], page: int, page_size: int = 5) -> tuple[str, int]:
    if not events:
        return "Поблизости пока ничего не нашли.", 1
    total_pages = max(1, ceil(len(events) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    parts = [render_event_html(e, idx) for idx, e in enumerate(events[start:end], start=start + 1)]
    return "\n".join(parts), total_pages


# ---------- Test data ----------
def sample_events() -> list[dict]:
    return [
        # валидный источник
        dict(
            type="source",
            title="Открытая лекция",
            when_str="2025-09-05 19:00",
            distance_km=1.2,
            venue_name="Dojo Bali",
            source_url="https://dojobali.org/events/open-lecture",
        ),
        # мусорный календарь (должен отфильтроваться)
        dict(
            type="source",
            title="Воркшоп",
            when_str="2025-09-05 12:00",
            distance_km=0.6,
            venue_name="Hub XYZ",
            source_url="https://calendar.google.com/",
        ),
        # example.com (должен отфильтроваться/не показывать «Источник»)
        dict(
            type="ai_generated",
            title="Йога на пляже",
            when_str="2025-09-05 07:00",
            distance_km=2.4,
            address="Sanur Beach",
            location_url="https://example.com/sanur",
        ),
        # пользовательский — ссылка на автора
        dict(
            type="user",
            title="Иду пить кофе",
            when_str="2025-09-05 16:00",
            distance_km=0.3,
            venue_name="Revolver Espresso",
            author_url="https://t.me/username",
        ),
        # без названия места → пойдёт по координатам
        dict(
            type="ai_generated",
            title="Концерт локальной музыки",
            when_str="2025-09-05 20:00",
            distance_km=3.8,
            lat=-8.67,
            lng=115.22,
        ),
    ]


# ---------- Run ----------
if __name__ == "__main__":
    raw = sample_events()
    prepared = prepare_events_for_feed(raw)
    groups = group_by_type(prepared)
    counts = make_counts(groups)
    header = render_header(counts)
    page_html, total = render_page(prepared, page=1, page_size=5)

    print("\n===== HEADER (HTML) =====")
    print(header)
    print("\n===== PAGE (HTML) =====")
    print(page_html)

    # быстрые проверки
    assert all("example.com" not in (get_source_url(e) or "") for e in prepared)
    assert "calendar.google.com" not in (prepared[0].get("source_url") or "")
    print("\n✅ Checks passed: no example.com, no blank calendar links.")
