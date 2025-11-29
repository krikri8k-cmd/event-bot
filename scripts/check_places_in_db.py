#!/usr/bin/env python3
"""
Скрипт для проверки наличия мест в базе данных
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Добавляем корень проекта в путь для импортов
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import TaskPlace, get_session, init_engine  # noqa: E402

# Загружаем переменные окружения
env_path = project_root / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)


def check_places():
    """Проверяет наличие мест в базе данных"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL не найден в переменных окружения")
        sys.exit(1)

    init_engine(db_url)

    with get_session() as session:
        # Проверяем все места
        all_places = session.query(TaskPlace).all()
        print(f"\n📊 Всего мест в базе: {len(all_places)}\n")

        # Проверяем места по регионам
        regions = ["moscow", "spb", "bali", "jakarta"]
        for region in regions:
            places = session.query(TaskPlace).filter(TaskPlace.region == region).all()
            print(f"📍 {region.upper()}: {len(places)} мест")
            if places:
                for place in places[:5]:  # Показываем первые 5
                    task_type = place.task_type or "не указан"
                    print(f"   - {place.name} ({place.category}, {place.place_type}, task_type={task_type})")
                if len(places) > 5:
                    print(f"   ... и еще {len(places) - 5} мест")

        # Проверяем места для Москвы с категорией body и типом urban
        print("\n🔍 Проверка мест для Москвы (body, urban):")
        moscow_body_places = (
            session.query(TaskPlace)
            .filter(
                TaskPlace.region == "moscow",
                TaskPlace.category == "body",
                TaskPlace.task_type == "urban",
                TaskPlace.is_active == True,  # noqa: E712
            )
            .all()
        )
        print(f"   Найдено: {len(moscow_body_places)} мест")
        if moscow_body_places:
            print("   Места:")
            for place in moscow_body_places:
                promo = f", промокод: {place.promo_code}" if place.promo_code else ""
                print(f"   - {place.name} ({place.place_type}){promo}")
        else:
            print("   ❌ Места не найдены!")

        # Проверяем места без task_type
        print("\n⚠️  Места без task_type:")
        places_without_task_type = session.query(TaskPlace).filter(TaskPlace.task_type.is_(None)).all()
        if places_without_task_type:
            print(f"   Найдено: {len(places_without_task_type)} мест")
            for place in places_without_task_type:
                print(f"   - {place.name} ({place.region}, {place.category})")
        else:
            print("   ✅ Все места имеют task_type")

        # Проверяем места с task_type != urban для Москвы
        print("\n🔍 Места Москвы с task_type != urban:")
        moscow_non_urban = (
            session.query(TaskPlace)
            .filter(
                TaskPlace.region == "moscow",
                TaskPlace.task_type != "urban",
            )
            .all()
        )
        if moscow_non_urban:
            print(f"   Найдено: {len(moscow_non_urban)} мест")
            for place in moscow_non_urban:
                print(f"   - {place.name} (task_type={place.task_type})")
        else:
            print("   ✅ Все места Москвы имеют task_type=urban")

        # Проверяем места по типам мест для body в Москве
        print("\n🔍 Места по типам для body в Москве:")
        place_types = ["cafe", "park", "gym"]
        for place_type in place_types:
            places = (
                session.query(TaskPlace)
                .filter(
                    TaskPlace.region == "moscow",
                    TaskPlace.category == "body",
                    TaskPlace.place_type == place_type,
                    TaskPlace.task_type == "urban",
                    TaskPlace.is_active == True,  # noqa: E712
                )
                .all()
            )
            print(f"   {place_type}: {len(places)} мест")
            if places:
                for place in places:
                    promo = f", промокод: {place.promo_code}" if place.promo_code else ""
                    print(f"      - {place.name}{promo}")


if __name__ == "__main__":
    check_places()
