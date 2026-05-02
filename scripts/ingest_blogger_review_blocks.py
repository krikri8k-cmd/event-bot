#!/usr/bin/env python3
"""
Загрузка блоков «блогер + обзор + место» без дубликатов partners.

Формат одного блока (строки подряд, между блоками — пустая строка):

    # @v.d_fitness | review https://www.instagram.com/reels/XXXX/
    Tropical Temptation
    https://maps.app.goo.gl/xxxxx

Строка 1: # @handle | review <url>  (Instagram / TikTok / другое)
Строка 2: подсказка названия места (для поиска, если URL не совпал один в один)
Строка 3: ссылка Google Maps (как в task_places.google_maps_url)

Действия:
  - partner: один партнёр на slug (из @handle). Уже есть — не создаём дубликат.
    Новому: display_name из ника, main_url NULL — дозаполнишь в БД позже.
    list_in_blogger_choice не трогаем (платная витрина отдельно).
  - place: точный google_maps_url, затем вхождение short-id, затем однозначный ILIKE name,
    затем ближайшее по координатам из ссылки (~350 м).
  - task_places: partner_id, review_url; опционально task_hint RU и зеркало name_en.

Пример:
  python scripts/ingest_blogger_review_blocks.py blogger_place_reviews.txt
  python scripts/ingest_blogger_review_blocks.py blogger_place_reviews.txt --dry-run
  python scripts/ingest_blogger_review_blocks.py blogger_place_reviews.txt --set-task-hint-ru --translate-hint
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import func

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_HEADER_RE = re.compile(
    r"^\s*#\s*@?([\w.\-]+)\s*\|\s*review\s+(\S+)\s*$",
    re.IGNORECASE,
)


def _normalize_slug(raw: str) -> str:
    slug = (raw or "").strip().lower().lstrip("@")
    slug = re.sub(r"[^a-z0-9_]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        raise ValueError("Invalid slug after normalization")
    return slug


def _display_from_handle(handle: str) -> str:
    h = handle.strip().lstrip("@")
    return h.replace("_", " ").replace(".", " ").strip().title() or h


def _extract_maps_short_id(url: str) -> str | None:
    m = re.search(r"(?:goo\.gl|maps\.app\.goo\.gl)/([^/?#]+)", url, re.I)
    return m.group(1) if m else None


def _coords_from_maps_url(maps_url: str) -> tuple[float, float] | None:
    import asyncio

    from utils.geo_utils import parse_google_maps_link

    async def inner() -> tuple[float, float] | None:
        r = await parse_google_maps_link(maps_url)
        if r and r.get("lat") is not None and r.get("lng") is not None:
            return float(r["lat"]), float(r["lng"])
        return None

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(inner())
    finally:
        loop.close()


def _find_place(session, maps_url: str, name_hint: str):
    from database import TaskPlace
    from utils.geo_utils import haversine_km

    u = (maps_url or "").strip()
    if not u.startswith("http"):
        return None

    q = session.query(TaskPlace).filter(TaskPlace.is_active == True)  # noqa: E712

    p = q.filter(TaskPlace.google_maps_url == u).first()
    if p:
        return p

    sid = _extract_maps_short_id(u)
    if sid:
        p = q.filter(TaskPlace.google_maps_url.ilike(f"%{sid}%")).first()
        if p:
            return p

    hint = (name_hint or "").strip()
    if len(hint) >= 3:
        candidates = q.filter(TaskPlace.name.ilike(f"%{hint}%")).order_by(TaskPlace.id.asc()).limit(25).all()
        if len(candidates) == 1:
            return candidates[0]

    coords = _coords_from_maps_url(u)
    if coords:
        lat0, lng0 = coords
        best = None
        best_km = 999.0
        for row in q.all():
            try:
                d = haversine_km(lat0, lng0, float(row.lat), float(row.lng))
            except (TypeError, ValueError):
                continue
            if d < best_km:
                best_km = d
                best = row
        if best is not None and best_km <= 0.35:
            return best

    return None


def _parse_blocks(text: str) -> list[tuple[str, str, str, str]]:
    """(handle, review_url, maps_url, name_hint)."""
    raw_blocks = re.split(r"\n\s*\n", text.strip())
    out: list[tuple[str, str, str, str]] = []
    for block in raw_blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].startswith("#") and not _HEADER_RE.match(lines[0]):
            continue
        m = _HEADER_RE.match(lines[0])
        if not m or len(lines) < 3:
            raise ValueError(f"Bad block (need 3 lines, header # @x | review URL):\n{block!r}")
        handle, review_url = m.group(1), m.group(2)
        name_hint, maps_url = lines[1], lines[2]
        if not maps_url.startswith("http"):
            raise ValueError(f"Line 3 must be maps URL, got: {maps_url!r}")
        out.append((handle, review_url, maps_url, name_hint))
    return out


def _maybe_translate_hints(place_ids: list[int]) -> None:
    from database import TaskPlace, get_session
    from utils.event_translation import translate_task_hints_batch

    if not place_ids:
        return
    with get_session() as session:
        rows = (
            session.query(TaskPlace.id, TaskPlace.task_hint)
            .filter(
                TaskPlace.id.in_(place_ids),
                TaskPlace.task_hint.isnot(None),
                func.trim(TaskPlace.task_hint) != "",
            )
            .all()
        )
        todo: list[tuple[int, str]] = []
        for pid, th in rows:
            full = session.query(TaskPlace).filter(TaskPlace.id == pid).first()
            if not full:
                continue
            ten = (full.task_hint_en or "").strip()
            if not ten:
                todo.append((pid, th))
    if not todo:
        print("  (translate-hint: nothing to translate)")
        return
    hints = [t[1] for t in todo]
    outs = translate_task_hints_batch(hints)
    with get_session() as session:
        for (pid, _h), en in zip(todo, outs):
            if en:
                p = session.query(TaskPlace).filter(TaskPlace.id == pid).first()
                if p:
                    p.task_hint_en = en
                    print(f"  translated task_hint_en for place_id={pid}")
        session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest blogger review blocks -> partners + task_places.")
    parser.add_argument(
        "file",
        nargs="?",
        default="blogger_place_reviews.txt",
        help="Text file with blocks (default: blogger_place_reviews.txt in project root)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions, do not commit")
    parser.add_argument(
        "--translate-hint",
        action="store_true",
        help="After commit, translate task_hint -> task_hint_en (OpenAI) for updated rows",
    )
    parser.add_argument(
        "--set-task-hint-ru",
        action="store_true",
        help="If place has empty task_hint, set short RU hint about video review",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        print(f"File not found: {path}")
        return 1

    raw_text = path.read_text(encoding="utf-8-sig")
    try:
        blocks = _parse_blocks(raw_text)
    except ValueError as e:
        print(f"Parse error: {e}")
        return 1

    if not blocks:
        print("No blocks parsed.")
        return 0

    from config import load_settings
    from database import Partner, get_session, init_engine

    settings = load_settings(require_bot=False)
    init_engine(settings.database_url)

    updated_place_ids: list[int] = []

    with get_session() as session:
        for handle, review_url, maps_url, name_hint in blocks:
            slug = _normalize_slug(handle)
            display = _display_from_handle(handle)

            partner = session.query(Partner).filter(func.lower(Partner.slug) == slug.lower()).first()
            if not partner:
                partner = Partner(
                    slug=slug,
                    display_name=display,
                    main_url=None,
                    is_active=True,
                    list_in_blogger_choice=False,
                    notes=f"[ingest_blogger_review_blocks] @{handle}",
                )
                session.add(partner)
                session.flush()
                print(f"partner CREATED slug={slug} id={partner.id}")
            else:
                print(f"partner EXISTS slug={slug} id={partner.id}")

            place = _find_place(session, maps_url, name_hint)
            if not place:
                print(f"  ERROR: place not found for maps={maps_url!r} hint={name_hint!r}")
                if not args.dry_run:
                    session.rollback()
                    return 2
                continue

            print(f"  place id={place.id} name={place.name!r}")

            if args.dry_run:
                print(f"  DRY would set partner_id={partner.id} review_url={review_url[:72]}...")
                continue

            place.partner_id = partner.id
            place.review_url = review_url.strip()

            if args.set_task_hint_ru and (not place.task_hint or not str(place.task_hint).strip()):
                base = review_url.split("?")[0].strip()
                if len(base) > 100:
                    base = base[:97] + "..."
                place.task_hint = f"Посмотри видеообзор и загляни в это место. Ссылка: {base}"

            if not place.name_en or not str(place.name_en).strip():
                place.name_en = place.name

            updated_place_ids.append(place.id)

        if args.dry_run:
            session.rollback()
            print("DRY RUN — no DB changes.")
            return 0

        session.commit()
        print("OK committed.")

    if args.translate_hint and updated_place_ids:
        _maybe_translate_hints(updated_place_ids)

    return 0


if __name__ == "__main__":
    sys.exit(main())
