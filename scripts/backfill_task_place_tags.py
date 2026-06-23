#!/usr/bin/env python3
"""
Предложить и (опционально) записать доп. place_tags в task_places.

Только extras в place_tags — place_type не меняется.
По умолчанию dry-run (без записи).

Develop:
  python -m scripts.backfill_task_place_tags
  python -m scripts.backfill_task_place_tags --apply --only-empty
  python -m scripts.backfill_task_place_tags --use-llm --only-empty --export-csv llm_dryrun.csv

Production (только по явной просьбе):
  TASK_PLACES_ALLOW_PRODUCTION_WRITE=1 railway run -e production -s event-bot \\
    python -m scripts.backfill_task_place_tags --production
  ... --apply --only-empty --use-llm
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402
from utils.place_tag_keywords import merge_place_tags, place_tags_is_empty, propose_extra_tags  # noqa: E402
from utils.place_tag_llm import propose_extra_tags_llm  # noqa: E402
from utils.place_tags import _parse_place_tags_raw, get_place_tag_slugs  # noqa: E402
from utils.task_places_export_db import database_host_hint, resolve_task_places_database_url  # noqa: E402
from utils.task_places_safety import is_production_database_context  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class PlannedUpdate:
    place_id: int
    name: str
    category: str
    place_type: str
    current_tags: list[str]
    display_before: list[str]
    proposed_extras: list[str]
    new_place_tags: list[str]
    display_after: list[str]
    reasons: list[str]
    source: str
    task_hint_preview: str


def _refuse_unsafe_apply(*, production: bool, apply: bool) -> None:
    if not apply:
        return
    if production and os.getenv("TASK_PLACES_ALLOW_PRODUCTION_WRITE") != "1":
        logger.error(
            "Запись в production task_places заблокирована.\n"
            "  TASK_PLACES_ALLOW_PRODUCTION_WRITE=1 railway run -e production -s event-bot \\\n"
            "    python -m scripts.backfill_task_place_tags --production --apply ..."
        )
        raise SystemExit(1)


def _parse_ids(raw: str | None) -> set[int] | None:
    if not raw:
        return None
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


def _hint_preview(place: TaskPlace, limit: int = 80) -> str:
    hint = (place.task_hint or place.task_hint_en or place.description or "").strip()
    if len(hint) <= limit:
        return hint
    return hint[: limit - 3] + "..."


def _propose_for_place(
    place,
    *,
    use_llm: bool,
    llm_delay: float,
) -> tuple[list[str], list[str], str, bool]:
    """Возвращает (extras, reasons, source, llm_was_called)."""
    proposed, reasons = propose_extra_tags(place)
    if proposed:
        return proposed, reasons, "keywords", False

    if not use_llm:
        return [], [], "", False

    proposed, reasons = propose_extra_tags_llm(place)
    if llm_delay > 0:
        time.sleep(llm_delay)
    if proposed:
        return proposed, reasons, "llm", True
    return [], reasons, "llm", True


def _plan_updates(
    places: list[TaskPlace],
    *,
    only_empty: bool,
    use_llm: bool,
    llm_delay: float,
) -> list[PlannedUpdate]:
    planned: list[PlannedUpdate] = []
    llm_calls = 0

    for place in places:
        if only_empty and not place_tags_is_empty(place.place_tags):
            continue

        proposed, reasons, source, llm_called = _propose_for_place(place, use_llm=use_llm, llm_delay=llm_delay)
        if llm_called:
            llm_calls += 1

        if not proposed:
            continue

        current_extras = _parse_place_tags_raw(place.place_tags)
        new_place_tags = merge_place_tags(place, proposed)
        if new_place_tags == current_extras:
            continue

        display_after = get_place_tag_slugs(
            type(
                "Preview",
                (),
                {"place_type": place.place_type, "place_tags": new_place_tags},
            )()
        )

        planned.append(
            PlannedUpdate(
                place_id=place.id,
                name=(place.name or "").strip(),
                category=(place.category or "").strip(),
                place_type=(place.place_type or "").strip(),
                current_tags=current_extras,
                display_before=get_place_tag_slugs(place),
                proposed_extras=proposed,
                new_place_tags=new_place_tags,
                display_after=display_after,
                reasons=reasons,
                source=source,
                task_hint_preview=_hint_preview(place),
            )
        )

    if use_llm:
        logger.info("LLM вызовов: %s", llm_calls)

    return planned


def _write_csv(path: Path, rows: list[PlannedUpdate]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "id",
                "name",
                "category",
                "place_type",
                "display_before",
                "proposed_extras",
                "new_place_tags",
                "display_after",
                "source",
                "reasons",
                "task_hint_preview",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.place_id,
                    row.name,
                    row.category,
                    row.place_type,
                    ", ".join(row.display_before),
                    ", ".join(row.proposed_extras),
                    ", ".join(row.new_place_tags),
                    ", ".join(row.display_after),
                    row.source,
                    "; ".join(row.reasons),
                    row.task_hint_preview,
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill доп. place_tags в task_places (keywords + optional GPT)")
    parser.add_argument("--production", action="store_true", help="production Postgres (@MyGuide)")
    parser.add_argument("--apply", action="store_true", help="Записать в БД (иначе dry-run)")
    parser.add_argument("--only-empty", action="store_true", help="Только строки с пустым place_tags")
    parser.add_argument("--use-llm", action="store_true", help="GPT для мест без keyword-предложений")
    parser.add_argument("--category", choices=("food", "health", "places", "entertainment"), help="Фильтр category")
    parser.add_argument("--ids", help="Точечно: id через запятую")
    parser.add_argument("--export-csv", metavar="PATH", help="Сохранить отчёт в CSV")
    parser.add_argument("--include-inactive", action="store_true", help="Включить is_active=false")
    parser.add_argument("--limit", type=int, help="Обработать не более N мест (для тестового прогона)")
    parser.add_argument("--delay", type=float, default=0.3, help="Пауза между LLM-запросами, сек (default: 0.3)")
    args = parser.parse_args()

    _refuse_unsafe_apply(production=args.production, apply=args.apply)

    db_url = resolve_task_places_database_url(production=args.production)
    tier = "production" if args.production else "develop/local"
    logger.info("БД (%s): %s", tier, database_host_hint(db_url))
    if args.apply and is_production_database_context():
        logger.warning("Контекст production — убедитесь, что это осознанный запуск.")

    init_engine(db_url)
    id_filter = _parse_ids(args.ids)

    with get_session() as session:
        query = session.query(TaskPlace).order_by(TaskPlace.id)
        if not args.include_inactive:
            query = query.filter(TaskPlace.is_active.is_(True))
        if args.category:
            query = query.filter(TaskPlace.category == args.category)
        if id_filter:
            query = query.filter(TaskPlace.id.in_(id_filter))
        if args.limit:
            query = query.limit(args.limit)
        places = query.all()

        planned = _plan_updates(
            places,
            only_empty=args.only_empty,
            use_llm=args.use_llm,
            llm_delay=args.delay if args.use_llm else 0,
        )
        logger.info(
            "Проанalyzed %s мест, предложено обновить %s%s%s",
            len(places),
            len(planned),
            " (only-empty)" if args.only_empty else "",
            " +llm" if args.use_llm else "",
        )

        for row in planned:
            logger.info(
                "id=%s «%s» [%s/%s] %s -> +%s (%s) => place_tags=%s | display: %s -> %s | %s",
                row.place_id,
                row.name[:60],
                row.category,
                row.place_type or "?",
                row.current_tags or "[]",
                row.proposed_extras,
                row.source,
                row.new_place_tags,
                " / ".join(row.display_before),
                " / ".join(row.display_after),
                "; ".join(row.reasons),
            )

        if args.export_csv:
            out = Path(args.export_csv)
            _write_csv(out, planned)
            logger.info("CSV: %s (%s строк)", out.resolve(), len(planned))

        if not args.apply:
            logger.info("DRY-RUN — БД не изменена. Для записи: --apply")
            return 0

        updated = 0
        for row in planned:
            session.query(TaskPlace).filter(TaskPlace.id == row.place_id).update(
                {"place_tags": row.new_place_tags},
                synchronize_session=False,
            )
            updated += 1
        session.commit()
        logger.info("OK — обновлено %s строк place_tags", updated)

    return 0


if __name__ == "__main__":
    sys.exit(main())
