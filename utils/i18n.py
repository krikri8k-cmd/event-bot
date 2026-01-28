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
        # Ошибки
        "errors.not_found": "❌ Не найдено",
        "errors.event_not_found": "❌ Событие не найдено",
        "errors.no_permission": "❌ У вас нет прав для редактирования этого события",
        "errors.general": "❌ Ошибка",
        "errors.update_failed": "❌ Ошибка при обновлении",
        # Поиск событий
        "search.loading": "🔍 Ищу события рядом...",
        "search.error.general": "❌ Произошла ошибка при поиске событий. Попробуйте позже.",
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
        "edit.date_format_error": "❌ Ошибка при обновлении даты. Проверьте формат (ДД.ММ.ГГГГ)",
        "edit.time_format_error": "❌ Ошибка при обновлении времени. Проверьте формат (ЧЧ:ММ)",
    },
    "en": {
        # Language selection
        "language.choose": "Choose language / Выберите язык",
        "language.changed": "✅ Language changed to English",
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
        # Events
        "events.nearby": "📍 Nearby events",
        "events.page": "📋 Events (page {page} of {total}):",
        "events.not_found": "❌ No events found",
        "events.not_found_with_radius": "📅 No events within {radius} km {date_text}.",
        "events.suggestion.change_radius": "💡 Try changing the radius to {radius} km\n",
        "events.suggestion.repeat_search": "💡 Try changing the radius and searching again\n",
        "events.suggestion.create_your_own": "➕ Or create your own event and gather your company!",
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
        # Errors
        "errors.not_found": "❌ Not found",
        "errors.event_not_found": "❌ Event not found",
        "errors.no_permission": "❌ You don't have permission to edit this event",
        "errors.general": "❌ Error",
        "errors.update_failed": "❌ Update failed",
        # Search
        "search.loading": "🔍 Searching for events nearby...",
        "search.error.general": "❌ Error while searching for events. Please try again later.",
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
        "edit.date_format_error": "❌ Error updating date. Check format (DD.MM.YYYY)",
        "edit.time_format_error": "❌ Error updating time. Check format (HH:MM)",
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
