#!/usr/bin/env python3
"""
Скрипт для загрузки шаблонов заданий и мест в БД
"""

import json
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent.parent))

from config import load_settings
from database import TaskPlace, TaskTemplate, get_session, init_engine


def load_task_templates():
    """Загрузить шаблоны заданий из JSON"""
    templates_path = Path(__file__).parent.parent / "seeds" / "task_templates.json"

    if not templates_path.exists():
        print(f"❌ Файл {templates_path} не найден")
        return False

    with open(templates_path, encoding="utf-8") as f:
        templates_data = json.load(f)

    with get_session() as session:
        # Очищаем существующие шаблоны
        session.query(TaskTemplate).delete()

        for template_data in templates_data:
            template = TaskTemplate(
                category=template_data["category"],
                place_type=template_data["place_type"],
                title=template_data["title"],
                description=template_data["description"],
                rocket_value=template_data["rocket_value"],
            )
            session.add(template)

        session.commit()
        print(f"✅ Загружено {len(templates_data)} шаблонов заданий")

    return True


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

        session.commit()
        print(f"✅ Загружено {len(places_data)} мест")

    return True


def main():
    """Основная функция"""
    print("🚀 Загрузка данных для функции 'Цель на Районе'")

    # Инициализируем БД
    settings = load_settings()
    init_engine(settings.database_url)

    # Загружаем данные
    success = True
    success &= load_task_templates()
    success &= load_task_places()

    if success:
        print("🎉 Все данные успешно загружены!")
    else:
        print("❌ Произошли ошибки при загрузке данных")
        sys.exit(1)


if __name__ == "__main__":
    main()
