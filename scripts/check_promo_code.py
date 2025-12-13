"""Скрипт для проверки промокода для места nüde cafe Pererenan"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402

# Загружаем переменные окружения
env_path = project_root / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

# Используем DATABASE_URL из окружения (Railway)
database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("ERROR: DATABASE_URL not found in environment variables")
    sys.exit(1)

# Инициализируем engine
init_engine(database_url)

print("Checking promo code for 'nude cafe Pererenan'...")
print(f"Database connection: {database_url[:50]}...\n")

with get_session() as session:
    # Ищем место по названию (частичное совпадение)
    places = session.query(TaskPlace).filter(TaskPlace.name.ilike("%nüde cafe%Pererenan%")).all()

    if not places:
        print("ERROR: Place 'nude cafe Pererenan' not found in DB")
        print("\nSearching for all places with 'nude' in name:")
        all_nude = session.query(TaskPlace).filter(TaskPlace.name.ilike("%nude%")).all()
        for p in all_nude:
            print(f"  - {p.name} (id={p.id}, promo_code={p.promo_code})")
    else:
        for place in places:
            print("FOUND place:")
            print(f"   ID: {place.id}")
            print(f"   Name: {place.name}")
            print(f"   Promo code: {place.promo_code if place.promo_code else 'NOT SET'}")
            print(f"   Category: {place.category}")
            print(f"   Place type: {place.place_type}")
            print(f"   Region: {place.region}")
            print(f"   Google Maps: {place.google_maps_url}")
            print(f"   Active: {place.is_active}")
            print()

            if place.promo_code:
                print(f"OK: Promo code '{place.promo_code}' found and should be displayed in bot!")
                print("\nWhere promo code is displayed:")
                print(f"   1. In places list (category {place.category})")
                print("   2. In task details after adding to quests")
            else:
                print("WARNING: Promo code NOT set for this place!")
                print("\nTo add promo code, run SQL:")
                print(f"   UPDATE task_places SET promo_code = 'YOUR_CODE' WHERE id = {place.id};")
