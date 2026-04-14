#!/usr/bin/env python3
"""
Быстрое добавление/обновление конкретных мест без прогона всего файла.
Использование: python scripts/quick_patch.py
Требует DATABASE_URL в app.local.env (Public URL, не .internal).
Для генерации task_hint (RU) и task_hint_en — OPENAI_API_KEY в env (как у бота).
"""

import os
import sys

# UTF-8 для консоли (Windows)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(project_root / "app.local.env")

from database import TaskPlace, get_session, init_engine  # noqa: E402
from tasks.ai_hints_generator import generate_hint_for_place  # noqa: E402
from utils.event_translation import translate_task_hints_batch  # noqa: E402

# Данные для патча: название, короткая ссылка (без |промо), промокод
PLACES = [
    {
        "name": "Bali Dacha",
        "url": "https://maps.app.goo.gl/mmgJ4eRMFe3PnEmQ8",
        "promo_code": "Jungle26 Club day 50.000 IDR , private rent 10%",
    },
]

CATEGORY = "health"
PLACE_TYPE = "spa"
REGION = "bali"


# Суффикс ссылки для поиска по LIKE (на случай если в БД хранится расширенный URL)
def _url_key(url: str) -> str:
    s = url.strip().rstrip("/")
    if "goo.gl/" in s:
        return s.split("goo.gl/")[-1].split("?")[0].strip()
    if "maps.app.goo.gl/" in s:
        return s.split("maps.app.goo.gl/")[-1].split("?")[0].strip()
    return s


def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден. Задай в app.local.env или переменной окружения.")
        sys.exit(1)

    host = "?"
    try:
        rest = db_url.split("@", 1)[1]
        host = rest.split("/")[0].rsplit(":", 1)[0] if ":" in rest.split("/")[0] else rest.split("/")[0]
    except IndexError:
        pass
    print(f"Connecting to host: {host}")
    if ".internal" in host:
        print("⚠️  ВНИМАНИЕ: хост .internal с компа недоступен. Используй Public URL (interchange.proxy.rlwy.net).")
        sys.exit(1)

    init_engine(db_url)

    with get_session() as session:
        for p in PLACES:
            name = p["name"]
            url = p["url"].strip()
            promo_code = p["promo_code"]
            key = _url_key(url)

            # Найти запись по ссылке (точное совпадение или по суффиксу)
            row = (
                session.query(TaskPlace)
                .filter((TaskPlace.google_maps_url == url) | (TaskPlace.google_maps_url.like(f"%{key}%")))
                .first()
            )

            if row:
                row.name = name
                row.promo_code = promo_code
                row.is_active = True
                row.category = CATEGORY
                row.place_type = PLACE_TYPE
                row.region = REGION
                action = "обновлён"
            else:
                row = TaskPlace(
                    category=CATEGORY,
                    place_type=PLACE_TYPE,
                    task_type="island",
                    name=name,
                    lat=0.0,
                    lng=0.0,
                    google_maps_url=url,
                    promo_code=promo_code,
                    is_active=True,
                    region=REGION,
                )
                session.add(row)
                action = "создан (координаты 0,0 — при необходимости обнови полным импортом)"

            # Задание RU + зеркало названия EN; перевод подсказки EN (как run_backfill_task_places_i18n)
            row.name_en = name
            row.task_hint = None
            row.task_hint_en = None
            session.flush()

            if generate_hint_for_place(row):
                hints_en = translate_task_hints_batch([row.task_hint])
                if hints_en and hints_en[0]:
                    row.task_hint_en = hints_en[0]
                print(f"ID [{row.id}] {action}: {name}")
                task_hint_preview = row.task_hint[:120] if row.task_hint else ""
                task_hint_suffix = "..." if len(row.task_hint or "") > 120 else ""
                print(f"    task_hint: {task_hint_preview}{task_hint_suffix}")
                if row.task_hint_en:
                    print(f"    task_hint_en: {row.task_hint_en[:120]}{'...' if len(row.task_hint_en) > 120 else ''}")
                else:
                    backfill_cmd = "scripts/run_backfill_task_places_i18n.py"
                    print(f"    task_hint_en: (нет — проверь OPENAI_API_KEY или запусти {backfill_cmd})")
            else:
                print(f"ID [{row.id}] {action}: {name}")
                print("    task_hint: (не сгенерирован — проверь OPENAI_API_KEY)")

            session.commit()


if __name__ == "__main__":
    main()
