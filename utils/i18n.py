"""
Модуль интернационализации (i18n) для бота
Поддерживает русский (ru) и английский (en) языки
"""

# Словари переводов
_TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        # Язык и выбор языка
        "language.choose": "Выберите язык / Choose language",
        "language.changed": "✅ Язык изменён на русский",
        "language.invalid": "❌ Неверный язык",
        "language.save_error": "❌ Ошибка при сохранении языка",
        "language.changed.en": "✅ Language changed to English",
        "language.button.ru": "🇷🇺 Русский",
        "language.button.en": "🇬🇧 English",
        # Главное меню
        "menu.greeting": (
            'Привет! @EventAroundBot версия "World" - твой цифровой помощник по активностям.\n\n'
            "📍 События рядом: находи события в радиусе 5–20 км\n"
            "🎯 Интересные места: промокоды и AI развлечения вокруг\n\n"
            "➕ Создать: организуй встречи и приглашай друзей\n"
            '🔗 Добавить бота в чат: добавь бота версия "Community" в чат — '
            "появится лента встреч и планов только для участников сообщества.\n\n"
            "🚀 Начинай приключение"
        ),
        "menu.button.events_nearby": "📍 События рядом",
        "menu.button.interesting_places": "🎯 Интересные места",
        "menu.button.create": "➕ Создать",
        "menu.button.create_event": "➕ Создать событие",
        "menu.use_buttons": "Используйте кнопки меню для навигации:",
        "menu.button.my_activities": "📝 Мои активности",
        "menu.button.add_bot_to_chat": "🔗 Добавить бота в чат",
        "menu.button.start": "🚀 Старт",
        # Команды бота
        "command.start": "🚀 Запустить бота и показать меню",
        "command.nearby": "📍 События рядом - найти события поблизости",
        "command.create": "➕ Создать новое событие",
        "command.myevents": "📋 Мои события - просмотр созданных событий",
        "command.tasks": "🎯 Интересные места - найти задания поблизости",
        "command.mytasks": "🏆 Мои квесты - просмотр выполненных заданий",
        "command.share": "🔗 Добавить бота в чат",
        "command.help": "💬 Написать отзыв Разработчику",
        "command.language": "🌐 Выбрать язык / Choose language",
        "command.group.start": "🎉 События чата",
        # Групповой чат
        "group.greeting": '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
        "🎯 **В этом чате я помогаю:**\n"
        "• Создавать события участников чата\n"
        "• Показывать все события, созданные в этом чате\n"
        "• Переходить к полному боту для поиска по геолокации\n\n"
        "💡 **Выберите действие:**",
        "group.panel.text": '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
        "🎯 Что умею:\n"
        "• Создавать события участников чата\n"
        "• Показывать события этого чата\n"
        '• Полная версия "World"\n\n'
        "💡 Выберите действие:",
        "group.button.create_event": "➕ Создать событие",
        "group.button.events_list": "📋 События этого чата",
        "group.button.full_version": '🚀 Полная версия "World"',
        "group.button.hide_bot": "👁️‍🗨️ Спрятать бота",
        "group.button.manage_events": "🔧 Управление событиями",
        "group.button.back": "◀️ Назад",
        "group.button.menu": "📋 Меню",
        "group.button.next": "▶️ Вперед",
        "group.join.use_command": "❌ Используйте команду: /join_event_123 (где 123 - ID события)",
        "group.join.use_command_short": "❌ Используйте команду: /joinevent123 (где 123 - ID события)",
        "group.join.invalid_id": "❌ Неверный ID события. Используйте: /join_event_123",
        "group.join.invalid_id_short": "❌ Неверный ID события. Используйте: /joinevent123",
        "group.leave.use_command": "❌ Используйте команду: /leave_event_123 (где 123 - ID события)",
        "group.leave.use_command_short": "❌ Используйте команду: /leaveevent123 (где 123 - ID события)",
        "group.leave.invalid_id": "❌ Неверный ID события. Используйте: /leave_event_123",
        "group.leave.invalid_id_short": "❌ Неверный ID события. Используйте: /leaveevent123",
        "group.event_not_found": "❌ Событие не найдено",
        "group.already_joined": "ℹ️ Вы уже записаны на это событие",
        "group.join_failed": "❌ Не удалось записаться на событие",
        "group.list.empty": (
            "📋 **События этого чата**\n\n"
            "📭 **0 событий**\n\n"
            "В этом чате пока нет активных событий.\n\n"
            "💡 Создайте первое событие, нажав кнопку **➕ Создать событие**!"
        ),
        "group.list.header": "📋 **События этого чата** ({count} событий)\n\n",
        "group.list.place_on_map": "Место на карте",
        "group.list.organizer": "👤 Организатор:",
        "group.list.participants": "👥 Участников:",
        "group.list.you_joined": "✅ Вы записаны | Нажмите 👉 /leaveevent{id} чтобы отменить",
        "group.list.join_prompt": "Нажмите 👉 /joinevent{id} чтобы записаться",
        "group.list.admin_footer": (
            "🔧 Админ-панель: Вы можете управлять любым событием кнопками ниже!\n"
            "💡 Нажмите ➕ Создать событие чтобы добавить свое!"
        ),
        "group.list.user_footer": (
            "🔧 Ваши события: Вы можете управлять своими событиями кнопками ниже!\n"
            "💡 Нажмите ➕ Создать событие чтобы добавить свое!"
        ),
        "group.load_error": "❌ Ошибка при загрузке события",
        "group.panel.what_can_do": (
            '👋 Привет! Я EventAroundBot - версия "Community".\n\n'
            "🎯 Что умею:\n\n"
            "• Создавать события\n"
            "• Показывать события этого чата\n"
            '• Полная версия "World"\n\n'
            "💡 Выберите действие:"
        ),
        "group.nudge_commands": "ℹ️ Чтобы открыть команды, нажмите `/` или введите `/start@EventAroundBot`.",
        "group.activated": "🤖 EventAroundBot активирован!",
        "group.hide_toast": "Скрываем сервисные сообщения бота…",
        "group.message_deleted": "✅ Сообщение удалено",
        "group.message_delete_failed": "❌ Не удалось удалить сообщение",
        "group.list.first_page": "⚠️ Это первая страница",
        "group.list.last_page": "⚠️ Это последняя страница",
        "group.list.header_paged": "📋 **События этого чата** ({count} событий, стр. {page}/{total_pages})\n\n",
        # Задания
        "tasks.title": "🎯 Интересные места",
        "tasks.reward": "Награда 3 🚀",
        "tasks.description": (
            "Самое время развлечься и получить награды.\n\n"
            "Нажмите кнопку **'📍 Отправить геолокацию'** чтобы начать!"
        ),
        "tasks.button.send_location": "📍 Отправить геолокацию",
        "tasks.button.find_on_map": "🌍 Найти на карте",
        "tasks.button.main_menu": "🏠 Главное меню",
        # Мои события
        "myevents.title": "📋 Мои события",
        "myevents.empty": "У вас пока нет созданных событий.",
        "myevents.create_first": ("Создайте первое событие командой /create"),
        # Мои квесты
        "mytasks.title": "🏆 Мои квесты",
        "tasks.choose_section": "Выберите раздел:",
        "tasks.not_found": "Задание не найдено",
        # Добавить бота в чат
        "share.title": '🤝Версия "Community"- наведет структуру и порядок событий в вашем чате.\n\n'
        "🚀 **Награда: За добавление бота в чат 150 ракет !!!** 🚀\n\n"
        "Инструкция:\n\n"
        "Для супергрупп !!!\n"
        "Заходите с Web 💻\n"
        "Сможете добавить в конкретную Тему\n\n"
        "1) Нажми на ссылку и выбери чат\n"
        "{bot_link}\n\n"
        "2) Предоставьте права админ\n\n"
        "3) Разрешите удалять сообщения\n\n"
        "Бот автоматически\n"
        "чистит свои сообщения в чате\n\n"
        "Теперь все события в одном месте ❤",
        # Администрирование
        "admin.permission.denied": "❌ У вас нет прав для выполнения этой команды",
        "admin.ban.usage": (
            "Использование: /ban <user_id> [дни] [причина]\n\n"
            "Примеры:\n"
            "/ban 123456789 - забанить навсегда\n"
            "/ban 123456789 7 - забанить на 7 дней\n"
            "/ban 123456789 30 Спам - забанить на 30 дней с причиной"
        ),
        "admin.ban.success.permanent": "🚫 Пользователь {user_id}{username_part} забанен навсегда",
        "admin.ban.success.temporary": "🚫 Пользователь {user_id}{username_part} забанен на {days} дней",
        "admin.ban.reason": "Причина: {reason}",
        "admin.ban.error": "❌ Ошибка при бане пользователя",
        "admin.ban.invalid_id": "❌ ID пользователя должен быть числом",
        "admin.error.exception": "❌ Произошла ошибка: {error}",
        "admin.unban.usage": (
            "Использование: /unban <user_id>\n\n" "Или ответьте на сообщение пользователя командой /unban"
        ),
        "admin.unban.success": "✅ Пользователь {user_id} разбанен",
        "admin.unban.not_found": "⚠️ Пользователь {user_id} не найден в списке банов",
        "admin.banlist.empty": "📋 Список забаненных пользователей пуст",
        "admin.banlist.header": "🚫 <b>Забаненные пользователи:</b>",
        "admin.banlist.item": "• {user_info}",
        "admin.banlist.reason": "  Причина: {reason}",
        "admin.banlist.until": "  До: {date}",
        "admin.banlist.permanent": "  Навсегда",
        # Ошибки
        "errors.not_found": "❌ Не найдено",
        "errors.banned": "🚫 Вы заблокированы в этом боте",
        "errors.event_load_failed": "❌ Ошибка при загрузке события",
        "errors.location_failed": (
            "❌ Ошибка: не удалось получить геолокацию. Попробуйте отправить геолокацию еще раз."
        ),
        "errors.event_not_found": "❌ Событие не найдено",
        "errors.no_permission": "❌ У вас нет прав для редактирования этого события",
        "errors.general": "❌ Ошибка",
        "errors.update_failed": "❌ Ошибка при обновлении",
        # Поиск событий
        "search.loading": "🔍 Ищу события рядом...",
        "search.error.general": "❌ Произошла ошибка при поиске событий. Попробуйте позже.",
        "search.state_expired": "❌ Данные поиска устарели. Отправьте геолокацию заново.",
        "search.location_not_found": "❌ Геолокация не найдена. Отправьте геолокацию заново.",
        "search.geo_prompt": (
            "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
            "💡 Если кнопка не работает :\n\n"
            "• Жми '🌍 Найти на карте' \n"
            "и вставь ссылку \n\n"
            "• Или отправь координаты\n"
            "пример: -8.4095, 115.1889"
        ),
        # События
        "events.nearby": "📍 События рядом",
        "events.page": "📋 События (страница {page} из {total}):",
        "events.not_found": "❌ События не найдены",
        "events.not_found_with_radius": "📅 В радиусе {radius} км событий {date_text} не найдено.",
        "events.suggestion.change_radius": "💡 Попробуй изменить радиус до {radius} км\n",
        "events.suggestion.repeat_search": "💡 Попробуй изменить радиус и повторить поиск\n",
        "events.suggestion.create_your_own": "➕ Или создай своё событие и собери свою компанию!",
        # Заголовок списка событий
        "events.header.found_nearby": "🗺 Найдено рядом: <b>{count}</b>",
        "events.header.found_in_radius": "🗺 В радиусе {radius} км найдено: <b>{count}</b>",
        "events.header.from_users": "• 👥 От пользователей: {count}",
        "events.header.from_groups": "• 💥 От групп: {count}",
        "events.header.from_sources": "• 🌐 Из источников: {count}",
        "events.header.ai_parsed": "• 🤖 AI-парсинг: {count}",
        "events.summary.found": "🗺 Найдено {count} событий рядом!",
        # Пагинация событий
        "pager.prev": "◀️ Назад",
        "pager.next": "Вперёд ▶️",
        "pager.page": "Стр. {page}/{total}",
        "pager.today": "📅 Сегодня",
        "pager.today_selected": "📅 Сегодня ✅",
        "pager.tomorrow": "📅 Завтра",
        "pager.tomorrow_selected": "📅 Завтра ✅",
        "pager.radius_km": "{radius} км",
        "pager.radius_expanded": "✅ Радиус расширен до {radius} км",
        # Создание событий
        "create.start": (
            '➕ **Создаём событие "World"**\n\n'
            "- Будет видно для всех игроков бота.\n\n"
            "Награда 5 🚀\n\n"
            "**Введите название мероприятия** (например: Прогулка):"
        ),
        "create.enter_title": "**Введите название мероприятия** (например: Прогулка):",
        "create.title_saved": "Название сохранено: *{title}* ✅\n\n📅 Теперь введите дату (например: {example_date}):",
        "create.enter_date": "📅 **Введите дату** (например: {example_date}):",
        "create.date_saved": "**Дата сохранена:** {date} ✅\n\n⏰ **Введите время** (например: 19:00):",
        "create.enter_time": "⏰ **Введите время** (например: 19:00):",
        "create.time_saved": "**Время сохранено:** {time} ✅\n\n📍 **Отправьте геолокацию или введите место:**",
        "create.enter_location": "📍 **Отправьте геолокацию или введите место:**",
        "create.location_saved": (
            "**Место сохранено** ✅\n{location_text}\n\n"
            "📝 **Введите описание события**\n(что будет происходить, кому интересно):"
        ),
        "create.enter_description": ("📝 **Введите описание события**\n(что будет происходить, кому интересно):"),
        "create.cancelled": "Создание отменено.",
        "create.cancelled_full": "❌ Создание мероприятия отменено.",
        "create.wait_already_started": "⏳ Подождите, создание события уже запущено...",
        "create.wait_in_progress": "⏳ Подождите, событие уже создается...",
        "create.validation.no_text": "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n{next_prompt}",
        "create.validation.invalid_date_format": (
            "❌ **Неверный формат даты!**\n\n" "📅 Введите дату в формате **ДД.ММ.ГГГГ**\n" "Например: 15.12.2024"
        ),
        "create.validation.invalid_time_format": (
            "❌ **Неверный формат времени!**\n\n" "⏰ Введите время в формате **ЧЧ:ММ**\n" "Например: 19:00"
        ),
        "create.validation.past_date": "⚠️ Внимание! Дата *{date}* уже прошла (сегодня {today}).\n\n📅 Введите дату:",
        "create.validation.no_commands_in_title": (
            "❌ В названии нельзя указывать команды (символ / в начале)!\n\n"
            "📝 Пожалуйста, придумайте краткое название события:\n"
            "• Что будет происходить\n"
            "• Где будет проходить\n"
            "• Для кого предназначено\n\n"
            "**Введите название мероприятия** (например: Прогулка):"
        ),
        "create.validation.no_links_in_title": (
            "❌ В названии нельзя указывать ссылки и контакты!\n\n"
            "📝 Пожалуйста, придумайте краткое название события:\n"
            "• Что будет происходить\n"
            "• Где будет проходить\n"
            "• Для кого предназначено\n\n"
            "**Введите название мероприятия** (например: Прогулка):"
        ),
        "create.validation.no_links_in_description": (
            "❌ В описании нельзя указывать ссылки и контакты!\n\n"
            "📝 Пожалуйста, опишите событие своими словами:\n"
            "• Что будет происходить\n"
            "• Кому будет интересно\n"
            "• Что взять с собой\n\n"
            "Контакты можно указать после создания события."
        ),
        # Редактирование событий
        "edit.enter_title": "✍️ Введите новое название события:",
        "edit.enter_date": "📅 Введите новую дату в формате ДД.ММ.ГГГГ:",
        "edit.enter_time": "⏰ Введите новое время в формате ЧЧ:ММ:",
        "edit.enter_description": "📝 Введите новое описание:",
        "edit.title_updated": "✅ Название обновлено!",
        "edit.date_updated": "✅ Дата обновлена!",
        "edit.time_updated": "✅ Время обновлено!",
        "edit.description_updated": "✅ Описание обновлено!",
        "edit.invalid_title": "❌ Введите корректное название",
        "edit.invalid_date": "❌ Введите корректную дату",
        "edit.invalid_time": "❌ Введите корректное время",
        "edit.invalid_location": "❌ Введите корректную локацию",
        "edit.invalid_description": "❌ Введите корректное описание",
        "edit.date_format_error": "❌ Ошибка при обновлении даты. Проверьте формат (ДД.ММ.ГГГГ)",
        "edit.time_format_error": "❌ Ошибка при обновлении времени. Проверьте формат (ЧЧ:ММ)",
        "edit.enter_date_with_current": "📅 Введите новую дату в формате ДД.ММ.ГГГГ (текущая дата: {current_date}):",
        "edit.enter_date_with_example": "📅 Введите новую дату в формате ДД.ММ.ГГГГ (например: {example_date}):",
        "edit.enter_time_with_current": "⏰ Введите новое время в формате ЧЧ:ММ (текущее время: {current_time}):",
        "edit.enter_time_with_example": "⏰ Введите новое время в формате ЧЧ:ММ (например: 18:30):",
        "edit.choose_what_to_change": "Выберите, что еще хотите изменить:",
        "edit.header": "✏️ **Редактирование события**\n\nВыберите, что хотите изменить:",
        "edit.event_not_found": "❌ Событие не найдено или не принадлежит вам",
        "edit.title_update_error": "❌ Ошибка при обновлении названия",
        "edit.button.title": "📌 Название",
        "edit.button.date": "📅 Дата",
        "edit.button.time": "⏰ Время",
        "edit.button.location": "📍 Локация",
        "edit.button.description": "📝 Описание",
        "edit.button.finish": "✅ Завершить",
        "common.not_specified": "Не указано",
        "common.access_denied": "Доступ запрещён",
        "common.location_not_found": "Локация не найдена",
        "edit.location_updated": "✅ Локация обновлена: *{location}*",
        "edit.location_update_error": "❌ Ошибка при обновлении локации",
        "edit.description_update_error": "❌ Ошибка при обновлении описания",
        "edit.group.event_not_found": "❌ Событие не найдено",
        "edit.group.no_permission": "❌ У вас нет прав для редактирования этого события",
        "edit.group.header": (
            "✏️ **Редактирование события**\n\n"
            "**Текущие данные:**\n"
            "📌 Название: {title}\n"
            "📅 Дата: {date}\n"
            "⏰ Время: {time}\n"
            "📍 Локация: {location}\n"
            "📝 Описание: {description}\n\n"
            "**Выберите, что хотите изменить:**"
        ),
        "edit.location_google_maps_error": (
            "❌ Не удалось распознать ссылку Google Maps.\n\n"
            "Попробуйте:\n"
            "• Скопировать ссылку из приложения Google Maps\n"
            "• Или ввести координаты в формате: широта, долгота"
        ),
        "edit.coords_out_of_range": (
            "❌ Координаты вне допустимого диапазона. Широта: -90 до 90, долгота: -180 до 180"
        ),
        "edit.coords_format": "❌ Неверный формат координат. Используйте: широта, долгота",
        "edit.group.updated_summary": (
            "✅ **Событие обновлено!**\n\n"
            "📌 Название: {title}\n"
            "📅 Дата: {date}\n"
            "⏰ Время: {time}\n"
            "📍 Локация: {location}\n"
            "📝 Описание: {description}\n\n"
            "Событие обновлено в группе!"
        ),
        "edit.group.invalid_format": "❌ Неверный формат",
        "edit.group.error": "❌ Ошибка",
        "edit.group.updated_toast": "✅ Событие обновлено!",
        "edit.location_map_prompt": "🌍 Открой карту, найди место и вставь ссылку сюда 👇",
        "edit.location_coords_prompt": (
            "📍 Введите координаты в формате: **широта, долгота**\n\n"
            "Например: 55.7558, 37.6176\n"
            "Или: -8.67, 115.21"
        ),
    },
    "en": {
        # Language selection
        "language.choose": "Choose language / Выберите язык",
        "language.changed": "✅ Language changed to English",
        "language.invalid": "❌ Invalid language",
        "language.save_error": "❌ Error saving language",
        "language.changed.ru": "✅ Язык изменён на русский",
        "language.button.ru": "🇷🇺 Русский",
        "language.button.en": "🇬🇧 English",
        # Main menu
        "menu.greeting": 'Hello! @EventAroundBot "World" version - your digital activity assistant.\n\n'
        "📍 Nearby events: find events within 5–20 km radius\n"
        "🎯 Interesting places: promo codes and AI entertainment around\n\n"
        "➕ Create: organize meetings and invite friends\n"
        '🔗 Add bot to chat: add bot "Community" version to chat — '
        "get a feed of meetings and plans only for community members.\n\n"
        "🚀 Start your adventure",
        "menu.button.events_nearby": "📍 Nearby events",
        "menu.button.interesting_places": "🎯 Interesting places",
        "menu.button.create": "➕ Create",
        "menu.button.create_event": "➕ Create event",
        "menu.use_buttons": "Use menu buttons for navigation:",
        "menu.button.my_activities": "📝 My activities",
        "menu.button.add_bot_to_chat": "🔗 Add bot to chat",
        "menu.button.start": "🚀 Start",
        # Bot commands
        "command.start": "🚀 Start bot and show menu",
        "command.nearby": "📍 Nearby events - find events nearby",
        "command.create": "➕ Create new event",
        "command.myevents": "📋 My events - view created events",
        "command.tasks": ("🎯 Interesting places - find tasks nearby"),
        "command.mytasks": "🏆 My quests - view completed tasks",
        "command.share": "🔗 Add bot to chat",
        "command.help": "💬 Write feedback to Developer",
        "command.language": "🌐 Choose language / Выберите язык",
        "command.group.start": "🎉 Chat events",
        # Group chat
        "group.greeting": '👋 Hello! I am EventAroundBot - "Community" version.\n\n'
        "🎯 **In this chat I help:**\n"
        "• Create community member events\n"
        "• Show all events created in this chat\n"
        "• Go to full bot for geolocation search\n\n"
        "💡 **Choose an action:**",
        "group.panel.text": '👋 Hello! I am EventAroundBot - "Community" version.\n\n'
        "🎯 What I can do:\n"
        "• Create community member events\n"
        "• Show events in this chat\n"
        '• Full "World" version\n\n'
        "💡 Choose an action:",
        "group.button.create_event": "➕ Create event",
        "group.button.events_list": "📋 Events in this chat",
        "group.button.full_version": '🚀 Full "World" version',
        "group.button.hide_bot": "👁️‍🗨️ Hide bot",
        "group.button.manage_events": "🔧 Manage events",
        "group.button.back": "◀️ Back",
        "group.button.menu": "📋 Menu",
        "group.button.next": "▶️ Next",
        "group.join.use_command": "❌ Use command: /join_event_123 (where 123 is event ID)",
        "group.join.use_command_short": "❌ Use command: /joinevent123 (where 123 is event ID)",
        "group.join.invalid_id": "❌ Invalid event ID. Use: /join_event_123",
        "group.join.invalid_id_short": "❌ Invalid event ID. Use: /joinevent123",
        "group.leave.use_command": "❌ Use command: /leave_event_123 (where 123 is event ID)",
        "group.leave.use_command_short": "❌ Use command: /leaveevent123 (where 123 is event ID)",
        "group.leave.invalid_id": "❌ Invalid event ID. Use: /leave_event_123",
        "group.leave.invalid_id_short": "❌ Invalid event ID. Use: /leaveevent123",
        "group.event_not_found": "❌ Event not found",
        "group.already_joined": "ℹ️ You are already registered for this event",
        "group.join_failed": "❌ Failed to register for the event",
        "group.list.empty": (
            "📋 **Events in this chat**\n\n"
            "📭 **0 events**\n\n"
            "No active events in this chat yet.\n\n"
            "💡 Create the first event by tapping **➕ Create event**!"
        ),
        "group.list.header": "📋 **Events in this chat** ({count} events)\n\n",
        "group.list.place_on_map": "Place on map",
        "group.list.organizer": "👤 Organizer:",
        "group.list.participants": "👥 Participants:",
        "group.list.you_joined": "✅ You're in | Tap 👉 /leaveevent{id} to leave",
        "group.list.join_prompt": "Tap 👉 /joinevent{id} to join",
        "group.list.admin_footer": (
            "🔧 Admin: You can manage any event with the buttons below!\n" "💡 Tap ➕ Create event to add your own!"
        ),
        "group.list.user_footer": (
            "🔧 Your events: You can manage your events with the buttons below!\n"
            "💡 Tap ➕ Create event to add your own!"
        ),
        "group.load_error": "❌ Error loading event",
        "group.panel.what_can_do": (
            '👋 Hello! I am EventAroundBot - "Community" version.\n\n'
            "🎯 What I can do:\n\n"
            "• Create events\n"
            "• Show events in this chat\n"
            '• Full "World" version\n\n'
            "💡 Choose an action:"
        ),
        "group.nudge_commands": "ℹ️ To open commands, press `/` or type `/start@EventAroundBot`.",
        "group.activated": "🤖 EventAroundBot activated!",
        "group.hide_toast": "Hiding bot service messages…",
        "group.message_deleted": "✅ Message deleted",
        "group.message_delete_failed": "❌ Failed to delete message",
        "group.list.first_page": "⚠️ This is the first page",
        "group.list.last_page": "⚠️ This is the last page",
        "group.list.header_paged": "📋 **Events in this chat** ({count} events, p. {page}/{total_pages})\n\n",
        # Events
        "events.nearby": "📍 Nearby events",
        "events.page": "📋 Events (page {page} of {total}):",
        "events.not_found": "❌ No events found",
        "events.not_found_with_radius": "📅 No events within {radius} km {date_text}.",
        "events.suggestion.change_radius": "💡 Try changing the radius to {radius} km\n",
        "events.suggestion.repeat_search": "💡 Try changing the radius and searching again\n",
        "events.suggestion.create_your_own": "➕ Or create your own event and gather your company!",
        # Events list header
        "events.header.found_nearby": "🗺 Found nearby: <b>{count}</b>",
        "events.header.found_in_radius": "🗺 Found within {radius} km: <b>{count}</b>",
        "events.header.from_users": "• 👥 From users: {count}",
        "events.header.from_groups": "• 💥 From groups: {count}",
        "events.header.from_sources": "• 🌐 From sources: {count}",
        "events.header.ai_parsed": "• 🤖 AI parsed: {count}",
        "events.summary.found": "🗺 Found {count} events nearby!",
        # Pagination
        "pager.prev": "◀️ Back",
        "pager.next": "Forward ▶️",
        "pager.page": "Page {page}/{total}",
        "pager.today": "📅 Today",
        "pager.today_selected": "📅 Today ✅",
        "pager.tomorrow": "📅 Tomorrow",
        "pager.tomorrow_selected": "📅 Tomorrow ✅",
        "pager.radius_km": "{radius} km",
        "pager.radius_expanded": "✅ Radius expanded to {radius} km",
        # Create events
        "create.start": (
            '➕ **Creating "World" event**\n\n'
            "- Will be visible to all bot players.\n\n"
            "Reward 5 🚀\n\n"
            "**Enter event title** (e.g.: Walk):"
        ),
        "create.enter_title": "**Enter event title** (e.g.: Walk):",
        "create.title_saved": "Title saved: *{title}* ✅\n\n📅 Now enter date (e.g.: {example_date}):",
        "create.enter_date": "📅 **Enter date** (e.g.: {example_date}):",
        "create.date_saved": "**Date saved:** {date} ✅\n\n⏰ **Enter time** (e.g.: 19:00):",
        "create.enter_time": "⏰ **Enter time** (e.g.: 19:00):",
        "create.time_saved": "**Time saved:** {time} ✅\n\n📍 **Send location or enter place:**",
        "create.enter_location": "📍 **Send location or enter place:**",
        "create.location_saved": (
            "**Location saved** ✅\n{location_text}\n\n"
            "📝 **Enter event description**\n(what will happen, who it's for):"
        ),
        "create.enter_description": ("📝 **Enter event description**\n(what will happen, who it's for):"),
        "create.cancelled": "Creation cancelled.",
        "create.cancelled_full": "❌ Event creation cancelled.",
        "create.wait_already_started": "⏳ Please wait, event creation is already in progress...",
        "create.wait_in_progress": "⏳ Please wait, event is being created...",
        "create.validation.no_text": "❌ **Please send a text message!**\n\n{next_prompt}",
        "create.validation.invalid_date_format": (
            "❌ **Invalid date format!**\n\n" "📅 Enter date in format **DD.MM.YYYY**\n" "Example: 15.12.2024"
        ),
        "create.validation.invalid_time_format": (
            "❌ **Invalid time format!**\n\n" "⏰ Enter time in format **HH:MM**\n" "Example: 19:00"
        ),
        "create.validation.past_date": (
            "⚠️ Warning! Date *{date}* has already passed (today is {today}).\n\n" "📅 Enter date:"
        ),
        "create.validation.no_commands_in_title": (
            "❌ Cannot use commands (symbol / at the beginning) in title!\n\n"
            "📝 Please create a short event title:\n"
            "• What will happen\n"
            "• Where it will take place\n"
            "• Who it's for\n\n"
            "**Enter event title** (e.g.: Walk):"
        ),
        "create.validation.no_links_in_title": (
            "❌ Cannot use links and contacts in title!\n\n"
            "📝 Please create a short event title:\n"
            "• What will happen\n"
            "• Where it will take place\n"
            "• Who it's for\n\n"
            "**Enter event title** (e.g.: Walk):"
        ),
        "create.validation.no_links_in_description": (
            "❌ Cannot use links and contacts in description!\n\n"
            "📝 Please describe the event in your own words:\n"
            "• What will happen\n"
            "• Who it's for\n"
            "• What to bring\n\n"
            "You can add contacts after creating the event."
        ),
        # Tasks
        "tasks.title": "🎯 Interesting places",
        "tasks.reward": "Reward 3 🚀",
        "tasks.description": "Time to have fun and get rewards.\n\nPress the **'📍 Send location'** button to start!",
        "tasks.button.send_location": "📍 Send location",
        "tasks.button.find_on_map": "🌍 Find on map",
        "tasks.button.main_menu": "🏠 Main menu",
        # My events
        "myevents.title": "📋 My events",
        "myevents.empty": "You don't have any created events yet.",
        "myevents.create_first": "Create your first event with /create command",
        # My quests
        "mytasks.title": "🏆 My quests",
        "tasks.choose_section": "Choose section:",
        "tasks.not_found": "Task not found",
        # Add bot to chat
        "share.title": '🤝"Community" version - will bring structure and order to events in your chat.\n\n'
        "🚀 **Reward: For adding bot to chat 150 rockets !!!** 🚀\n\n"
        "Instructions:\n\n"
        "For supergroups !!!\n"
        "Access from Web 💻\n"
        "You can add to a specific Topic\n\n"
        "1) Click the link and select chat\n"
        "{bot_link}\n\n"
        "2) Grant admin rights\n\n"
        "3) Allow deleting messages\n\n"
        "Bot automatically\n"
        "cleans its messages in chat\n\n"
        "Now all events in one place ❤",
        # Administration
        "admin.permission.denied": "❌ You don't have permission to run this command",
        "admin.ban.usage": (
            "Usage: /ban <user_id> [days] [reason]\n\n"
            "Examples:\n"
            "/ban 123456789 — ban permanently\n"
            "/ban 123456789 7 — ban for 7 days\n"
            "/ban 123456789 30 Spam — ban for 30 days with a reason"
        ),
        "admin.ban.success.permanent": "🚫 User {user_id}{username_part} banned permanently",
        "admin.ban.success.temporary": "🚫 User {user_id}{username_part} banned for {days} days",
        "admin.ban.reason": "Reason: {reason}",
        "admin.ban.error": "❌ Failed to ban user",
        "admin.ban.invalid_id": "❌ User ID must be a number",
        "admin.error.exception": "❌ Error: {error}",
        "admin.unban.usage": ("Usage: /unban <user_id>\n\n" "Or reply to a user's message with /unban"),
        "admin.unban.success": "✅ User {user_id} unbanned",
        "admin.unban.not_found": "⚠️ User {user_id} not found in ban list",
        "admin.banlist.empty": "📋 Banned users list is empty",
        "admin.banlist.header": "🚫 <b>Banned users:</b>",
        "admin.banlist.item": "• {user_info}",
        "admin.banlist.reason": "  Reason: {reason}",
        "admin.banlist.until": "  Until: {date}",
        "admin.banlist.permanent": "  Permanent",
        # Errors
        "errors.not_found": "❌ Not found",
        "errors.banned": "🚫 You are blocked in this bot",
        "errors.event_load_failed": "❌ Error loading event",
        "errors.location_failed": ("❌ Error: could not get location. Please send your location again."),
        "errors.event_not_found": "❌ Event not found",
        "errors.no_permission": "❌ You don't have permission to edit this event",
        "errors.general": "❌ Error",
        "errors.update_failed": "❌ Update failed",
        # Search
        "search.loading": "🔍 Searching for events nearby...",
        "search.error.general": "❌ Error while searching for events. Please try again later.",
        "search.state_expired": "❌ Search data expired. Send your location again.",
        "search.location_not_found": "❌ Location not found. Send your location again.",
        "search.geo_prompt": (
            "Press the '📍 Send location' button to start!\n\n"
            "💡 If the button does not work:\n\n"
            "• Tap '🌍 Find on map' and paste a link\n\n"
            "• Or send coordinates, e.g.: -8.4095, 115.1889"
        ),
        # Event editing
        "edit.enter_title": "✍️ Enter new event title:",
        "edit.enter_date": "📅 Enter new date in format DD.MM.YYYY:",
        "edit.enter_time": "⏰ Enter new time in format HH:MM:",
        "edit.enter_description": "📝 Enter new description:",
        "edit.title_updated": "✅ Title updated!",
        "edit.date_updated": "✅ Date updated!",
        "edit.time_updated": "✅ Time updated!",
        "edit.description_updated": "✅ Description updated!",
        "edit.invalid_title": "❌ Enter valid title",
        "edit.invalid_date": "❌ Enter valid date",
        "edit.invalid_time": "❌ Enter valid time",
        "edit.invalid_location": "❌ Enter valid location",
        "edit.invalid_description": "❌ Enter valid description",
        "edit.date_format_error": "❌ Error updating date. Check format (DD.MM.YYYY)",
        "edit.time_format_error": "❌ Error updating time. Check format (HH:MM)",
        "edit.enter_date_with_current": "📅 Enter new date in format DD.MM.YYYY (current date: {current_date}):",
        "edit.enter_date_with_example": "📅 Enter new date in format DD.MM.YYYY (e.g.: {example_date}):",
        "edit.enter_time_with_current": "⏰ Enter new time in format HH:MM (current time: {current_time}):",
        "edit.enter_time_with_example": "⏰ Enter new time in format HH:MM (e.g.: 18:30):",
        "edit.choose_what_to_change": "Choose what else to change:",
        "edit.header": "✏️ **Edit event**\n\nChoose what to change:",
        "edit.event_not_found": "❌ Event not found or does not belong to you",
        "edit.title_update_error": "❌ Error updating title",
        "edit.button.title": "📌 Title",
        "edit.button.date": "📅 Date",
        "edit.button.time": "⏰ Time",
        "edit.button.location": "📍 Location",
        "edit.button.description": "📝 Description",
        "edit.button.finish": "✅ Finish",
        "common.not_specified": "Not specified",
        "common.access_denied": "Access denied",
        "common.location_not_found": "Location not found",
        "edit.location_updated": "✅ Location updated: *{location}*",
        "edit.location_update_error": "❌ Error updating location",
        "edit.description_update_error": "❌ Error updating description",
        "edit.group.event_not_found": "❌ Event not found",
        "edit.group.no_permission": "❌ You don't have permission to edit this event",
        "edit.group.header": (
            "✏️ **Edit event**\n\n"
            "**Current data:**\n"
            "📌 Title: {title}\n"
            "📅 Date: {date}\n"
            "⏰ Time: {time}\n"
            "📍 Location: {location}\n"
            "📝 Description: {description}\n\n"
            "**Choose what to change:**"
        ),
        "edit.location_google_maps_error": (
            "❌ Could not recognize Google Maps link.\n\n"
            "Try:\n"
            "• Copy link from Google Maps app\n"
            "• Or enter coordinates as: latitude, longitude"
        ),
        "edit.coords_out_of_range": ("❌ Coordinates out of valid range. Latitude: -90 to 90, longitude: -180 to 180"),
        "edit.coords_format": "❌ Invalid coordinates format. Use: latitude, longitude",
        "edit.group.updated_summary": (
            "✅ **Event updated!**\n\n"
            "📌 Title: {title}\n"
            "📅 Date: {date}\n"
            "⏰ Time: {time}\n"
            "📍 Location: {location}\n"
            "📝 Description: {description}\n\n"
            "Event updated in group!"
        ),
        "edit.group.invalid_format": "❌ Invalid format",
        "edit.group.error": "❌ Error",
        "edit.group.updated_toast": "✅ Event updated!",
        "edit.location_map_prompt": "🌍 Open the map, find the place and paste the link here 👇",
        "edit.location_coords_prompt": (
            "📍 Enter coordinates in format: **latitude, longitude**\n\n" "E.g.: 55.7558, 37.6176\n" "Or: -8.67, 115.21"
        ),
    },
}


def t(key: str, lang: str = "ru") -> str:
    """
    Получить перевод по ключу

    Args:
        key: Ключ перевода (например, "menu.greeting")
        lang: Код языка ("ru" или "en"), по умолчанию "ru"

    Returns:
        Переведённый текст или [key], если ключ не найден
    """
    # Fallback на русский, если язык не поддерживается
    if lang not in _TRANSLATIONS:
        lang = "ru"

    translations = _TRANSLATIONS.get(lang, _TRANSLATIONS["ru"])
    result = translations.get(key)

    if result is None:
        # Если ключ не найден, пробуем найти в русском
        if lang != "ru":
            result = _TRANSLATIONS["ru"].get(key)

        # Если всё равно не найдено, возвращаем ключ в квадратных скобках
        if result is None:
            return f"[{key}]"

    return result


def format_translation(key: str, lang: str = "ru", **kwargs) -> str:
    """
    Получить перевод и подставить значения

    Args:
        key: Ключ перевода
        lang: Код языка
        **kwargs: Параметры для подстановки в строку

    Returns:
        Переведённый текст с подставленными значениями
    """
    text = t(key, lang)
    try:
        return text.format(**kwargs)
    except (KeyError, ValueError):
        # Если форматирование не удалось, возвращаем как есть
        return text


def get_supported_languages() -> list[str]:
    """Получить список поддерживаемых языков"""
    return list(_TRANSLATIONS.keys())


def is_language_supported(lang: str) -> bool:
    """Проверить, поддерживается ли язык"""
    return lang in _TRANSLATIONS
