#!/usr/bin/env python3
"""Перенос партнёров и их привязок к местам с DEV-БД на PROD-БД.

Идемпотентно:
- Партнёры матчатся по lower(slug): существующие обновляются, новые вставляются.
- Привязки мест переносятся матчингом task_places по (name, region, category):
  на PROD проставляются partner_id, review_url и (если задан) promo_code.
- В конце пересчитываются денормализованные счётчики partners.*_count.

URL-ы берутся из app.local.env (DEV_DB_URL / PROD_DB_URL). PROD-данные мест НЕ удаляются.

Запуск:
    python scripts/transfer_partners_dev_to_prod.py            # выполнить перенос
    python scripts/transfer_partners_dev_to_prod.py --dry-run  # только показать план
"""

import argparse
import os
import sys

import psycopg2

PARTNER_FIELDS = (
    "slug",
    "display_name",
    "main_url",
    "telegram_contact",
    "telegram_user_id",
    "default_promo_code",
    "priority",
    "is_featured",
    "is_active",
    "notes",
    "list_in_blogger_choice",
)

# Колонки места, переносимые при вставке недостающего места на PROD (id/created_at_utc — на стороне PROD).
PLACE_FIELDS = (
    "name",
    "region",
    "category",
    "description",
    "lat",
    "lng",
    "google_maps_url",
    "is_active",
    "place_type",
    "task_type",
    "promo_code",
    "review_url",
    "task_hint",
    "name_en",
    "task_hint_en",
)


def _read_db_url(var_name: str) -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(here, "app.local.env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{var_name}="):
                return line.split("=", 1)[1].strip()
    raise SystemExit(f"{var_name} not found in app.local.env")


def _close_all(*resources) -> None:
    for r in resources:
        try:
            r.close()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dev_url = _read_db_url("DEV_DB_URL")
    prod_url = _read_db_url("PROD_DB_URL")

    dev = psycopg2.connect(dev_url, connect_timeout=20)
    prod = psycopg2.connect(prod_url, connect_timeout=20)
    dev.autocommit = True
    prod.autocommit = False  # одна транзакция на весь перенос
    dcur = dev.cursor()
    pcur = prod.cursor()

    # 1) Партнёры с DEV
    dcur.execute(f"SELECT {', '.join(PARTNER_FIELDS)} FROM partners ORDER BY slug")
    dev_partners = dcur.fetchall()
    print(f"DEV partners: {len(dev_partners)}")

    # 2) Привязки мест на DEV (полные данные места — чтобы при отсутствии на PROD вставить целиком)
    dcur.execute(
        f"""
        SELECT p.slug, {", ".join("tp." + c for c in PLACE_FIELDS)}
        FROM task_places tp
        JOIN partners p ON p.id = tp.partner_id
        WHERE tp.partner_id IS NOT NULL
        ORDER BY p.slug, tp.name
        """
    )
    dev_links = dcur.fetchall()
    print(f"DEV partner-linked places: {len(dev_links)}")

    if args.dry_run:
        print("\n[dry-run] Партнёры к upsert:")
        for r in dev_partners:
            print("  ", r[0], "-", r[1])
        print("\n[dry-run] Привязки к переносу:")
        for r in dev_links:
            place = dict(zip(PLACE_FIELDS, r[1:]))
            print("  ", r[0], "->", place["name"], f"({place['category']}/{place['region']})")
        _close_all(dcur, pcur, dev, prod)
        return 0

    # 3) Upsert партнёров на PROD, собираем slug -> prod_id
    slug_to_id: dict[str, int] = {}
    inserted = updated = 0
    for row in dev_partners:
        data = dict(zip(PARTNER_FIELDS, row))
        slug = data["slug"]
        pcur.execute("SELECT id FROM partners WHERE lower(slug) = lower(%s)", (slug,))
        found = pcur.fetchone()
        if found:
            pid = found[0]
            set_cols = [c for c in PARTNER_FIELDS if c != "slug"]
            pcur.execute(
                f"UPDATE partners SET {', '.join(c + ' = %s' for c in set_cols)}, updated_at_utc = NOW() WHERE id = %s",
                [data[c] for c in set_cols] + [pid],
            )
            updated += 1
        else:
            cols = list(PARTNER_FIELDS)
            pcur.execute(
                f"INSERT INTO partners ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                [data[c] for c in cols],
            )
            pid = pcur.fetchone()[0]
            inserted += 1
        slug_to_id[slug] = pid

    print(f"PROD partners upserted: +{inserted} new, ~{updated} updated")

    # 4) Привязки мест на PROD: UPDATE по совпадению (name, region, category),
    #    иначе INSERT недостающего места целиком из DEV с привязкой к партнёру.
    linked = 0
    inserted_places = 0
    for row in dev_links:
        slug = row[0]
        place = dict(zip(PLACE_FIELDS, row[1:]))
        pid = slug_to_id[slug]
        promo = place["promo_code"] if (place["promo_code"] and place["promo_code"].strip()) else None
        pcur.execute(
            """
            UPDATE task_places
            SET partner_id = %s,
                review_url = COALESCE(NULLIF(%s, ''), review_url),
                promo_code = COALESCE(%s, promo_code)
            WHERE name = %s AND region = %s AND category = %s
            """,
            (pid, place["review_url"], promo, place["name"], place["region"], place["category"]),
        )
        if pcur.rowcount and pcur.rowcount > 0:
            linked += pcur.rowcount
            continue
        # Места нет на PROD — вставляем целиком
        cols = list(PLACE_FIELDS) + ["partner_id"]
        vals = [place[c] for c in PLACE_FIELDS] + [pid]
        pcur.execute(
            f"INSERT INTO task_places ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
            vals,
        )
        inserted_places += 1

    print(f"PROD places linked (updated existing): {linked}")
    print(f"PROD places inserted (were missing on PROD): {inserted_places}")

    # 5) Пересчёт счётчиков партнёров
    pcur.execute(
        """
        UPDATE partners p SET
            linked_places_count = COALESCE(s.cnt, 0),
            active_places_count = COALESCE(s.active_cnt, 0),
            places_with_promo_count = COALESCE(s.promo_cnt, 0)
        FROM (
            SELECT pp.id,
                   COUNT(tp.id) AS cnt,
                   COUNT(tp.id) FILTER (WHERE tp.is_active IS TRUE) AS active_cnt,
                   COUNT(tp.id) FILTER (WHERE tp.promo_code IS NOT NULL AND btrim(tp.promo_code) <> '') AS promo_cnt
            FROM partners pp
            LEFT JOIN task_places tp ON tp.partner_id = pp.id
            GROUP BY pp.id
        ) s
        WHERE p.id = s.id
        """
    )

    prod.commit()
    print("Counters recalculated. COMMIT done.")

    # Итоговая сводка
    pcur.execute("SELECT slug, display_name, list_in_blogger_choice, linked_places_count FROM partners ORDER BY slug")
    print("\n--- PROD partners after transfer ---")
    for r in pcur.fetchall():
        print(f"  {r[0]:14} blogger_choice={r[2]!s:5} linked_places={r[3]}  ({r[1]})")

    _close_all(dcur, pcur, dev, prod)
    return 0


if __name__ == "__main__":
    sys.exit(main())
