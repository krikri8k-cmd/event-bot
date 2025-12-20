# Как добавить места категории FOOD вручную

## 📋 Структура данных для food мест

### Категория: `food`
### Подклассы (place_type):
- `cafe` - Кафе
- `restaurant` - Рестораны  
- `street_food` - Уличная еда
- `market` - Рынки/фуд-корты
- `bakery` - Пекарни/кондитерские
- `coworking` - Коворкинг-кафе

## 🎯 Способ 1: Через простой текстовый файл (РЕКОМЕНДУЕТСЯ)

### Шаг 1: Создайте файл `food_places.txt` в папке проекта

Формат файла (каждая строка - одно место):
```
category|place_type|region|google_maps_url|promo_code(опционально)
```

### Примеры:

```
food|cafe|moscow|https://maps.google.com/?cid=123456789|PROMO2024
food|restaurant|spb|https://maps.google.com/?cid=987654321|
food|street_food|bali|https://maps.google.com/?cid=111222333|FOOD10
food|market|moscow|https://maps.google.com/?cid=444555666|
food|bakery|spb|https://maps.google.com/?cid=777888999|BAKE20
```

### Шаг 2: Запустите скрипт

```bash
python scripts/add_places_from_simple_file.py food_places.txt
```

Скрипт автоматически:
- Извлечет координаты из Google Maps ссылки
- Определит регион (если не указан)
- Сгенерирует AI подсказку
- Добавит место в БД

---

## 🎯 Способ 2: Через Python скрипт напрямую

Создайте файл `add_my_food_places.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from database import TaskPlace, get_session, init_engine
from tasks.ai_hints_generator import generate_hint_for_place

# Загружаем переменные окружения
env_path = Path(__file__).parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
init_engine(db_url)

# СПИСОК ВАШИХ МЕСТ
PLACES = [
    {
        "name": "Название кафе",
        "category": "food",
        "place_type": "cafe",
        "region": "moscow",  # или "spb", "bali"
        "lat": 55.7558,  # Широта
        "lng": 37.6173,  # Долгота
        "google_maps_url": "https://maps.google.com/?cid=...",
        "promo_code": "PROMO2024",  # опционально
        "description": "Описание места (опционально)"
    },
    # Добавьте еще места...
]

with get_session() as session:
    for place_data in PLACES:
        # Проверяем, не существует ли уже
        existing = session.query(TaskPlace).filter(
            TaskPlace.name == place_data["name"],
            TaskPlace.category == place_data["category"],
            TaskPlace.region == place_data["region"]
        ).first()
        
        if existing:
            print(f"SKIP: {place_data['name']} уже существует")
            continue
        
        # Создаем место
        place = TaskPlace(
            category=place_data["category"],
            place_type=place_data["place_type"],
            region=place_data["region"],
            name=place_data["name"],
            description=place_data.get("description"),
            lat=place_data["lat"],
            lng=place_data["lng"],
            google_maps_url=place_data.get("google_maps_url"),
            promo_code=place_data.get("promo_code"),
            is_active=True,
            task_type="urban" if place_data["region"] in ["moscow", "spb"] else "island"
        )
        
        session.add(place)
        session.flush()
        
        # Генерируем подсказку
        if generate_hint_for_place(place):
            print(f"OK: {place.name} - подсказка сгенерирована")
        
        session.commit()
        print(f"ADDED: {place.name}")

print("Done!")
```

Запустите:
```bash
python add_my_food_places.py
```

---

## 🎯 Способ 3: Через Google Maps ссылки (самый простой)

### Шаг 1: Создайте файл `food_places_links.txt`

Формат (каждая строка):
```
category|place_type|region|google_maps_url|promo_code
```

Пример:
```
food|cafe|moscow|https://maps.google.com/?cid=123456789|
food|restaurant|spb|https://maps.google.com/?cid=987654321|FOOD10
```

### Шаг 2: Запустите

```bash
python scripts/add_places_from_google_links.py food_places_links.txt
```

---

## 📝 Важные поля

| Поле | Обязательно | Описание | Пример |
|------|------------|----------|--------|
| `category` | ✅ | Всегда `food` | `food` |
| `place_type` | ✅ | Подкласс | `cafe`, `restaurant`, `street_food`, `market`, `bakery` |
| `region` | ✅ | Регион | `moscow`, `spb`, `bali` |
| `name` | ✅ | Название места | `"Кафе на Тверской"` |
| `lat` / `lng` | ✅ | Координаты | `55.7558`, `37.6173` |
| `google_maps_url` | ⚠️ | Ссылка на карту | `https://maps.google.com/?cid=...` |
| `promo_code` | ❌ | Промокод | `PROMO2024` |
| `description` | ❌ | Описание | `"Уютное кафе с кофе"` |

---

## 🔍 Как найти координаты места?

1. Откройте Google Maps
2. Найдите место
3. Правый клик → "Что здесь?"
4. Координаты появятся внизу (например: `55.7558, 37.6173`)

Или используйте Google Maps ссылку - скрипт сам извлечет координаты!

---

## ✅ После добавления

После добавления мест скрипт автоматически:
- ✅ Сгенерирует AI подсказку для каждого места
- ✅ Проверит на дубликаты
- ✅ Определит регион (если не указан)

Проверить результат:
```bash
python check_places_by_category.py
```

