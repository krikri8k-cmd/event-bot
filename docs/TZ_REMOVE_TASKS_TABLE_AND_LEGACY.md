# ТЗ: Удаление legacy-кода и таблицы tasks, фокус на task_places

**Контекст:** Данные в старой таблице `tasks` не нужны. Пользователей с сохранёнными заданиями из этой таблицы нет. Нужно полностью удалить таблицу и весь связанный код, оставив только логику на основе `task_places`.

---

## 1. База данных (порядок важен)

### 1.1. Удалить записи user_tasks, ссылающиеся на tasks

- Выполнить: `DELETE FROM user_tasks WHERE task_id IS NOT NULL;`
- (Опционально: экспорт в бэкап перед удалением, если нужна история.)

### 1.2. Удалить колонку task_id из user_tasks

- Выполнить: `ALTER TABLE user_tasks DROP COLUMN IF EXISTS task_id;`
- PostgreSQL: если есть FK, сначала удалить ограничение, затем колонку. Обычно: `ALTER TABLE user_tasks DROP CONSTRAINT ... ; ALTER TABLE user_tasks DROP COLUMN task_id;` или в одной миграции.

### 1.3. Удалить таблицу tasks

- Выполнить: `DROP TABLE IF EXISTS tasks;`

**Рекомендация:** оформить как миграцию в `migrations/` (один .sql файл) и применять через существующий механизм (или вручную на проде).

---

## 2. Код: database.py

- Удалить класс **Task** целиком (таблица `tasks`).
- В классе **UserTask** удалить поле **task_id** (и импорт/использование ForeignKey на `tasks.id`).

---

## 3. Код: tasks_service.py

### 3.1. Удалить функции, работающие только с таблицей tasks

- **get_all_available_tasks(category, task_type)** — удалить.
- **get_daily_tasks(category, task_type, date)** — удалить.
- **accept_task(user_id, task_id, user_lat, user_lng)** — удалить.

### 3.2. Убрать импорт Task

- Удалить `Task` из `from database import ...`.

### 3.3. get_user_active_tasks(user_id)

- Убрать `session.query(UserTask, Task).outerjoin(Task)`.
- Запрос: только `session.query(UserTask).filter(UserTask.user_id == user_id, UserTask.status == "active")`.
- В цикле убрать переменную `task`. Источники данных только:
  - **frozen_title**, **frozen_description**, **frozen_category**, **frozen_task_hint** из UserTask;
  - при их отсутствии — **place_name** и т.п. (default).
- В возвращаемый словарь не класть **task_id**. Поле **task_id** в dict убрать или всегда передавать `None`.
- **location_url** брать из `user_task.place_url` (не из task).
- **task_type** брать из связанного TaskPlace по `place_id` при необходимости или убрать/заменить на что-то из UserTask.

### 3.4. get_tasks_approaching_deadline(hours_before)

- Убрать `join(Task)`.
- Запрос: только `UserTask` с фильтром по `status`, `expires_at`.
- В результате использовать **user_task.frozen_title** (или place_name) вместо **task.title**.

### 3.5. add_place_to_user_tasks

- Убедиться, что в **user_task_kwargs** нет **task_id** (уже не передаётся после удаления поля из модели).

### 3.6. get_completed_task_ids_today(user_id)

- Функция возвращала список `task_id`. После удаления колонки:
  - либо возвращать список `user_task.id` (если кто-то использует «сколько заданий выполнено сегодня»);
  - либо оставить возврат списка ID для совместимости, но брать их из другой колонки (например, `user_task.id`).
- Проверить вызовы: в текущем коде вызовов не найдено — можно оставить сигнатуру, но внутри возвращать, например, `[ut.id for ut in completed]` по `UserTask.id`.

---

## 4. Код: bot_enhanced_v3.py

### 4.1. Удалить обработчики, завязанные на таблицу tasks и task_id

- **handle_task_detail** (callback `task_detail:*`) — удалить полностью.
- **handle_task_already_taken** (callback `task_already_taken:*`) — удалить полностью.
- **handle_task_accept** (callback `task_accept:*`) — удалить полностью.
- **handle_task_custom_location** (callback `task_custom_location:*`) — удалить полностью.
- Обработчик сообщений **TaskFlow.waiting_for_custom_location** (ввод ссылки/координат для «старого» задания и вызов `accept_task(user_id, task_id, ...)`) — удалить или переписать так, чтобы не вызывать `accept_task` и не использовать `task_id`. Проще всего удалить весь блок, связанный с `selected_task_id` и `accept_task`.

### 4.2. Убрать импорты и вызовы

- Удалить **accept_task** из импортов (из tasks_service).
- Удалить все вызовы **accept_task(...)** (остаются только те, что связаны с удалёнными выше хендлерами).
- В обработчиках больше не использовать **session.query(Task)** и не передавать **task_id** в callback_data.

### 4.3. Состояние TaskFlow

- **TaskFlow.waiting_for_location** и **TaskFlow.waiting_for_category** оставить — они используются для сценария «Интересные места» (выбор категории и показ мест из task_places).
- **TaskFlow.waiting_for_custom_location** — если после удаления хендлеров оно нигде не устанавливается, можно удалить из StatesGroup или оставить пустым.

---

## 5. Скрипты и прочее

- **scripts/add_food_island_tasks.py** — завязан на таблицу `tasks`. Удалить или пометить устаревшим (не запускать).
- **scripts/check_tasks_for_category.py** — использует `Task`. Удалить или переписать на task_places.
- **scripts/migrate_old_tasks_to_frozen.py** — использует `Task` и `user_task.task_id`. После удаления таблицы не нужен; удалить или оставить только как архив.
- **verify_migrations_applied.py** — убрать проверки, связанные с таблицей `tasks` (SELECT FROM tasks, проверки категорий в tasks). Оставить только проверки по `task_places` и другим актуальным таблицам.
- **add_tasks.py** (если есть в корне) — если пишет в `tasks`, удалить или не использовать.

---

## 6. task_places: зеркалирование и перевод

### 6.1. Зеркалирование имён

- Убедиться, что для всех записей **name_en = name** (без перевода названий).
- Уже есть **run_name_mirror()** в `utils/backfill_task_places_translation.py`. Запустить при необходимости или убедиться, что бэкфилл при старте это делает.

### 6.2. Массовый перевод task_hint → task_hint_en

- Запустить фоновую задачу перевода для всех мест, где **task_hint_en** пустой (NULL или пустая строка).
- Использовать существующий **run_hint_backfill()** (или **run_full_backfill()**) в `utils/backfill_task_places_translation.py` с нужным batch_size.
- Логирование — см. п. 7.

---

## 7. Логирование

После выполнения шагов БД и кода вывести в консоль:

- `[CLEANUP] Таблица tasks и связанные записи удалены.`
- При запуске перевода квестов: `[GPT] Запущен перевод task_hint для X мест.` (X — количество записей, для которых запущен/запланирован перевод, например количество строк с пустым task_hint_en).

---

## 8. Проверка интерфейса

- Команда **/tasks** и пункт меню **«Interesting places»** должны работать только на данных из **task_places** (через **show_tasks_for_category** → **get_all_places_for_category**).
- Убедиться, что ни один сценарий не вызывает обращений к таблице `tasks` или к полю `task_id` (нет ошибок типа «relation tasks does not exist» или «column task_id does not exist»).
- Проверить: выбор категории → список мест → «Забрать квест» → добавление в «Мои квесты» и отображение списка активных заданий (только через UserTask + frozen_* / place_id).

---

## 9. Краткий чеклист для агента

1. Миграция БД: DELETE user_tasks WHERE task_id IS NOT NULL; ALTER user_tasks DROP COLUMN task_id; DROP TABLE tasks;
2. database.py: удалить класс Task и поле task_id из UserTask.
3. tasks_service.py: удалить get_all_available_tasks, get_daily_tasks, accept_task; убрать Task из импортов и из get_user_active_tasks / get_tasks_approaching_deadline; убрать task_id из возвращаемых структур.
4. bot_enhanced_v3.py: удалить handle_task_detail, handle_task_already_taken, handle_task_accept, handle_task_custom_location и обработчик ввода локации для task_id; убрать импорт accept_task.
5. Скрипты и verify: убрать/обновить всё, что ссылается на Task/tasks.
6. Запустить run_name_mirror (если нужно) и run_hint_backfill; вывести логи [CLEANUP] и [GPT].
7. Ручная проверка: /tasks, Interesting places, Забрать квест, Мои квесты — без ошибок.
