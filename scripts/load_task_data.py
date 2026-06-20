#!/usr/bin/env python3
"""
Скрипт для загрузки мест (task_places) в БД.
"""

import json
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from config import load_settings
from database import TaskPlace, get_session, init_engine


def load_task_places():
    """Загрузить места из JSON"""
    places_path = Path(__file__).parent.parent / "seeds" / "bali_places.json"

    if not places_path.exists():
        print(f"❌ Файл {places_path} не найден")
        return False

    with open(places_path, encoding="utf-8") as f:
        places_data = json.load(f)

    with get_session() as session:
        # Очищаем существующие места
        session.query(TaskPlace).delete()

        from tasks.ai_hints_generator import generate_hint_for_place

        for place_data in places_data:
            place = TaskPlace(
                category=place_data["category"],
                name=place_data["name"],
                description=place_data["description"],
                lat=place_data["lat"],
                lng=place_data["lng"],
                google_maps_url=place_data["google_maps_url"],
                is_active=True,
            )
            session.add(place)
            session.flush()  # Получаем ID места для генерации подсказки

            # Генерируем подсказку с помощью AI
            try:
                if generate_hint_for_place(place):
                    print(f"   🤖 {place.name}: {place.task_hint[:50]}...")
            except Exception as e:
                print(f"   ⚠️ Ошибка генерации для {place.name}: {e}")

        session.commit()
        print(f"✅ Загружено {len(places_data)} мест")

    return True


def main():
    """Основная функция"""
    print("🚀 Загрузка мест для квестов (task_places)")

    settings = load_settings()
    init_engine(settings.database_url)

    if load_task_places():
        print("🎉 Данные успешно загружены!")
    else:
        print("❌ Произошли ошибки при загрузке данных")
        sys.exit(1)


if __name__ == "__main__":
    main()
