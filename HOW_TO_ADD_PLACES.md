# 📍 Как добавлять локации в базу данных

## 🎯 УПРОЩЕННЫЙ СПОСОБ (РЕКОМЕНДУЕТСЯ)

### 1. Открой файл `places_simple.txt`

### 2. Укажи категорию и тип места один раз:
```txt
food:cafe:moscow:ПРОМОКОД123
```

Где:
- `food` - категория: **food** (еда), **health** (здоровье), **places** (интересные места)
- `cafe` - тип места (cafe, park, gym, temple, viewpoint, restaurant, yoga_studio, beach, cliff, ...)
- `moscow` - регион (moscow, spb, bali, jakarta или `auto`)
- `ПРОМОКОД123` - промокод (опционально, применяется ко всем ссылкам ниже)

### 3. Вставь ссылки подряд:
```txt
food:cafe:moscow:ПРОМОКОД123
https://www.google.com/maps/place/Кофейня+1
https://www.google.com/maps/place/Кофейня+2|ПРОМОКОД456
https://www.google.com/maps/place/Кофейня+3

health:park:moscow
https://www.google.com/maps/place/Парк+1
https://www.google.com/maps/place/Парк+2
```

**Промокоды:**
- Можно указать в заголовке (применяется ко всем ссылкам): `food:cafe:moscow:ПРОМОКОД123`
- Можно указать после ссылки через `|` (приоритетнее): `https://maps.google.com/ссылка|ПРОМОКОД456`
- Если промокод не указан, поле будет пустым

### 4. Запусти скрипт:
```bash
python scripts/add_places_from_simple_file.py places_simple.txt
```

**Всё!** Скрипт автоматически:
- ✅ Извлечет координаты из ссылок
- ✅ Определит название места
- ✅ Определит регион (если `auto`)
- ✅ Добавит в таблицу `task_places`

---

## Альтернативный способ через CSV файл

### 1. Открой файл `places_template.csv`

В файле есть столбцы:
- `category` - категория задания (body, spirit, career, social)
- `place_type` - тип места (cafe, park, gym, temple, viewpoint, etc.)
- `region` - регион (moscow, spb, bali, jakarta, или `auto` для автоматического определения)
- `name` - название места
- `google_maps_url` - **ссылка на Google Maps** (главное!)
- `description` - описание (опционально)

### 2. Добавь свои ссылки

Просто заполни строки в CSV файле. Например:

```csv
category,place_type,region,name,google_maps_url,description
body,cafe,moscow,Кофейня на Арбате,https://maps.google.com/?q=55.7558,37.6176,Уютная кофейня
body,park,moscow,Парк Горького,https://maps.google.com/?q=55.7320,37.6010,Красивый парк
body,gym,spb,Фитнес клуб,https://maps.google.com/?q=59.9343,30.3351,Современный спортзал
```

### 3. Запусти скрипт

```bash
python scripts/add_places_simple.py places_template.csv
```

Скрипт автоматически:
- ✅ Извлечет координаты из Google Maps ссылок
- ✅ Определит регион (если указан `auto`)
- ✅ Добавит места в базу данных
- ✅ Проверит на дубликаты

## Типы мест по категориям

### Категория "Тело" (body):
- `cafe` - кафе
- `park` - парк
- `gym` - спортзал
- `yoga_studio` - студия йоги
- `beach` - пляж

### Категория "Дух" (spirit):
- `temple` - храм
- `park` - парк
- `viewpoint` - смотровая площадка
- `beach` - пляж

## Регионы

- `moscow` - Москва
- `spb` - Санкт-Петербург
- `bali` - Бали
- `jakarta` - Джакарта
- `auto` - автоматическое определение по координатам

## Пример заполнения

```csv
category,place_type,region,name,google_maps_url,description
body,cafe,moscow,Кофейня на Арбате,https://www.google.com/maps/place/...,Уютная кофейня в центре
body,park,auto,Парк рядом,https://maps.google.com/?q=55.7558,37.6176,Красивый парк
spirit,temple,bali,Храм в Убуде,https://maps.google.com/place/...,Балийский храм
```

**Важно:** Просто вставляй Google Maps ссылки в столбец `google_maps_url` - скрипт сам извлечет координаты!

