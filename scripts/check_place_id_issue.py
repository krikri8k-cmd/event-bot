#!/usr/bin/env python3
"""
Диагностический скрипт для проверки проблемы с place_id в заданиях
Проверяет по чек-листу консультанта:
1. Сохраняется ли place_id в user_tasks
2. Используется ли place_id для генерации URL
3. Не затирается ли place_id при обновлениях
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import TaskPlace, UserTask, get_session
from utils.geo_utils import _extract_place_id, to_google_maps_link

print("=" * 60)
print("🔍 ДИАГНОСТИКА ПРОБЛЕМЫ С place_id В ЗАДАНИЯХ")
print("=" * 60)
print()

with get_session() as session:
    # 1. Проверяем, есть ли place_id в user_tasks
    print("1️⃣ ПРОВЕРКА: place_id в user_tasks")
    print("-" * 60)

    active_tasks = (
        session.query(UserTask)
        .filter(UserTask.status == "active")
        .order_by(UserTask.accepted_at.desc())
        .limit(10)
        .all()
    )

    tasks_with_place_id = 0
    tasks_without_place_id = 0

    for task in active_tasks:
        if task.place_id:
            tasks_with_place_id += 1
            place = session.get(TaskPlace, task.place_id)
            if place:
                print(f"✅ UserTask {task.id}: place_id={task.place_id}, место='{place.name}'")
                print(f"   place_url в UserTask: {task.place_url[:80] if task.place_url else 'None'}...")
                print(
                    f"   google_maps_url в TaskPlace: {place.google_maps_url[:80] if place.google_maps_url else 'None'}..."
                )

                # Проверяем, есть ли place_id в URL
                if place.google_maps_url:
                    extracted_place_id = _extract_place_id(place.google_maps_url)
                    if extracted_place_id:
                        print(f"   ✅ В URL найден place_id: {extracted_place_id}")
                        # Генерируем правильную ссылку с place_id
                        correct_url = to_google_maps_link(place.lat, place.lng, extracted_place_id)
                        print(f"   ✅ Правильная ссылка с place_id: {correct_url[:80]}...")
                    else:
                        print("   ❌ В URL НЕТ place_id (только координаты)")
                        # Генерируем ссылку без place_id
                        fallback_url = to_google_maps_link(place.lat, place.lng, None)
                        print(f"   ⚠️ Текущая ссылка (без place_id): {fallback_url[:80]}...")
            else:
                print(f"⚠️ UserTask {task.id}: place_id={task.place_id}, но место не найдено в БД")
        else:
            tasks_without_place_id += 1
            print(f"❌ UserTask {task.id}: place_id IS NULL")

    print()
    print("📊 Статистика:")
    print(f"   - С place_id: {tasks_with_place_id}")
    print(f"   - Без place_id: {tasks_without_place_id}")
    print()

    # 2. Проверяем формат URL в task_places
    print("2️⃣ ПРОВЕРКА: формат URL в task_places")
    print("-" * 60)

    places = (
        session.query(TaskPlace)
        .filter(TaskPlace.is_active == True)  # noqa: E712
        .limit(20)
        .all()
    )

    places_with_place_id = 0
    places_without_place_id = 0

    for place in places:
        if place.google_maps_url:
            extracted_place_id = _extract_place_id(place.google_maps_url)
            if extracted_place_id:
                places_with_place_id += 1
                print(f"✅ {place.name}: URL содержит place_id={extracted_place_id[:30]}...")
            else:
                places_without_place_id += 1
                print(f"❌ {place.name}: URL БЕЗ place_id (только координаты)")
                print(f"   URL: {place.google_maps_url[:80]}...")
        else:
            places_without_place_id += 1
            print(f"❌ {place.name}: google_maps_url IS NULL")

    print()
    print("📊 Статистика:")
    print(f"   - URL с place_id: {places_with_place_id}")
    print(f"   - URL без place_id: {places_without_place_id}")
    print()

    # 3. Проверяем, используется ли place_id при генерации ссылок
    print("3️⃣ ПРОВЕРКА: используется ли place_id при генерации ссылок")
    print("-" * 60)

    # Берем пример задания с place_id
    example_task = session.query(UserTask).filter(UserTask.status == "active", UserTask.place_id.isnot(None)).first()

    if example_task:
        place = session.get(TaskPlace, example_task.place_id)
        if place and place.google_maps_url:
            extracted_place_id = _extract_place_id(place.google_maps_url)
            if extracted_place_id:
                # Генерируем правильную ссылку
                correct_url = to_google_maps_link(place.lat, place.lng, extracted_place_id)
                current_url = place.google_maps_url

                print(f"Пример: {place.name}")
                print(f"   Текущий URL: {current_url[:80]}...")
                print(f"   Правильный URL с place_id: {correct_url[:80]}...")
                print(f"   Совпадают: {'✅' if current_url == correct_url else '❌ НЕТ'}")
            else:
                print(f"⚠️ У места {place.name} нет place_id в URL")
    else:
        print("⚠️ Нет активных заданий с place_id для проверки")

    print()
    print("=" * 60)
    print("✅ ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 60)
    print()
    print("📋 РЕКОМЕНДАЦИИ:")
    print()

    if tasks_without_place_id > 0:
        print(f"❌ Найдено {tasks_without_place_id} заданий без place_id")
        print("   → Нужно проверить create_task_from_place() - сохраняется ли place_id")
        print()

    if places_without_place_id > 0:
        print(f"❌ Найдено {places_without_place_id} мест без place_id в URL")
        print("   → Нужно:")
        print("     1. Извлечь place_id из существующих URL (если есть)")
        print("     2. Или получить place_id через Places API")
        print("     3. Или добавить поле google_place_id в TaskPlace")
        print()

    print("💡 Если проблема в том, что название места не показывается в Google Maps:")
    print("   → Используйте to_google_maps_link(lat, lng, place_id) вместо прямого URL")
    print("   → Формат: https://www.google.com/maps/place/?q=place_id:XXX")
