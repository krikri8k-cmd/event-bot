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
            'Привет! @{bot_username} версия "World" - твой цифровой помощник по активностям.\n\n'
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
        "help.feedback.text": (
            "💬 **Написать отзыв Разработчику**\n\n"
            "Спасибо за использование {bot_username}! 🚀\n\n"
            "Если у вас есть предложения, замечания или просто хотите поблагодарить - "
            "напишите мне лично:\n\n"
            "👨‍💻 **@Fincontro**\n\n"
            "Я всегда рад обратной связи и готов помочь! 😊"
        ),
        "help.button.write": "💬 Написать @Fincontro",
        "command.language": "🌐 Выбрать язык / Choose language",
        "command.group.start": "🎉 События чата",
        "commands.list": (
            "📋 **Команды бота:**\n\n"
            "🚀 /start - Запустить бота и показать меню\n"
            "❓ /help - Показать справку\n"
            "📍 /nearby - Найти события рядом\n"
            "➕ /create - Создать событие\n"
            "📋 /myevents - Мои события\n"
            "🔗 /share - Добавить бота в чат\n\n"
            "💡 **Совет:** Используйте кнопки меню для удобной навигации!"
        ),
        # Групповой чат
        "group.greeting": '👋 Привет! Я {bot_username} - версия "Community".\n\n'
        "🎯 **В этом чате я помогаю:**\n"
        "• Создавать события участников чата\n"
        "• Показывать все события, созданные в этом чате\n"
        "• Переходить к полному боту для поиска по геолокации\n\n"
        "💡 **Выберите действие:**",
        "group.panel.text": '👋 Привет! Я {bot_username} - версия "Community".\n\n'
        "🎯 Что умею:\n"
        "• Создавать события участников чата\n"
        "• Показывать события этого чата\n"
        '• Полная версия "World"\n\n'
        "💡 Выберите действие:",
        "group.button.create_event": "➕ Создать событие",
        "group.button.events_list": "📋 События этого чата",
        "group.button.full_version": '🚀 Полная версия "World"',
        "group.button.language_ru": "🌐 Язык (RU)",
        "group.button.language_en": "🌐 Language (EN)",
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
        "group.card.join": "✅ Записаться",
        "group.card.leave": "❌ Не пойду",
        "group.card.participants": "👥 Участники",
        "group.card.footer": "💡 **Создавай через команду /start**",
        "group.list.admin_footer": "",
        "group.list.user_footer": "",
        "group.load_error": "❌ Ошибка при загрузке события",
        "group.language_changed": "✅ Язык изменён",
        "group.panel.what_can_do": (
            '👋 Привет! Я @{bot_username} - версия "Community".\n\n'
            "🎯 Что умею:\n\n"
            "• Создавать события\n"
            "• Показывать события этого чата\n"
            '• Полная версия "World"\n\n'
            "💡 Выберите действие:"
        ),
        "group.nudge_commands": "ℹ️ Чтобы открыть команды, нажмите `/` или введите `/start@{bot_username}`.",
        "group.activated": "🤖 {bot_username} активирован!",
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
        "tasks.button.find_on_map": "🌍 Открыть Google Maps",
        "tasks.button.main_menu": "🏠 Главное меню",
        # Мои события
        "myevents.title": "📋 Мои события",
        "myevents.empty": "У вас пока нет созданных событий.",
        "myevents.create_first": ("Создайте первое событие командой /create"),
        # Мои квесты
        "mytasks.title": "🏆 Мои квесты",
        "mytasks.empty": "У вас нет активных заданий.",
        "mytasks.empty_hint": "Нажмите «Интересные места», чтобы получить новые задания!",
        "mytasks.active_header": "📋 **Ваши активные задания:**",
        "mytasks.reward_line": "Прохождение + 3 🚀",
        "mytasks.place_label": "Место:",
        "mytasks.km_suffix": "км",
        "mytasks.motivation_line": "⏰ Для мотивации даем 24 часа",
        "mytasks.time_to_complete": "Время на выполнение:",
        "mytasks.label_category": "Категория:",
        "mytasks.label_description": "Описание:",
        "mytasks.button.back_to_list": "🔧 К списку заданий",
        "mytasks.button.back_to_tasks": "◀️ Назад к заданиям",
        "mytasks.button.done": "✅ Выполнено",
        "mytasks.button.cancel": "❌ Отменить",
        "mytasks.completed_title": "✅ **Задание выполнено!**",
        "mytasks.share_impressions": (
            "Поделитесь своими впечатлениями:\n• Как прошло выполнение?\n• Что вы почувствовали?\n"
            "• Как это помогло вам?\n\n📸 **Отправьте фото места** где вы были\n"
            "или **напишите отзыв** текстом:"
        ),
        "mytasks.cancel_error": "❌ **Ошибка отмены задания**\n\nНе удалось отменить задание. Попробуйте позже.",
        "tasks.choose_section": "Выберите раздел:",
        "tasks.not_found": "Задание не найдено",
        "tasks.cancelled": "✅ Задание отменено",
        "tasks.accepted": "✅ Задание принято!",
        "tasks.added": "✅ Задание добавлено в активные!",
        "tasks.start_error": "❌ Ошибка при начале задания",
        "tasks.page_edge": "Это крайняя страница",
        "tasks.require_location": "📍 Требуется геолокация",
        "tasks.complete_not_found": "❌ Ошибка: не найдено задание для завершения.",
        "tasks.task_not_found": "❌ Ошибка: не найдено задание.",
        "tasks.category.food": "🍔 Еда",
        "tasks.category.health": "💪 Здоровье",
        "tasks.category.places": "🌟 Интересные места",
        "tasks.places_found": "📍 Найдено мест: {count}",
        "tasks.km_from_you": "📍 {distance:.1f} км от вас",
        "tasks.promo_code": "🎁 Промокод: `{code}`",
        "tasks.take_quest": "🎯 Забрать квест",
        "tasks.button.list": "📋 Список",
        "tasks.no_places_in_category": "❌ Места для этой категории пока не добавлены.",
        "tasks.quest_added_success": "✅ Квест для места '{name}' добавлен в Мои квесты",
        "tasks.quest_already_added": "⚠️ Квест для места '{name}' уже добавлен в Мои квесты",
        "tasks.place_not_found": "❌ Место не найдено",
        "tasks.quest_already_short": "🙈 Квест уже добавлен",
        "tasks.quest_add_error": "❌ Ошибка при добавлении квеста: {error}",
        "tasks.location_received": (
            "✅ **Геолокация получена!**\n\n"
            "Выберите категорию для получения персонализированных заданий:\n\n"
            "🍔 **Еда** - кафе, рестораны, уличная еда\n"
            "💪 **Здоровье** - спорт, йога, спа, клиники\n"
            "🌟 **Интересные места** - парки, выставки, храмы"
        ),
        "tasks.categories_intro": (
            "Выберите категорию заданий:\n\n"
            "🍔 **Еда** - кафе, рестораны, уличная еда\n"
            "💪 **Здоровье** - спорт, йога, спа, клиники\n"
            "🌟 **Интересные места** - парки, выставки, храмы"
        ),
        "myevents.auto_closed": "🤖 Автоматически закрыто {count} прошедших событий",
        "myevents.header": "📋 **Мои события:**\n",
        "myevents.balance": "**Баланс {rocket_balance} 🚀**\n",
        "myevents.created_by_me": "📝 **Созданные мной:**",
        "myevents.recently_closed": "🔴 **Недавно закрытые ({count}):**",
        "myevents.and_more": "... и еще {count} событий",
        "myevents.and_more_closed": "... и еще {count} закрытых событий",
        "myevents.no_events": "У вас пока нет событий.",
        "myevents.button.manage_events": "🔧 Управление событиями",
        "myevents.button.all_added": "📋 Все добавленные события",
        "myevents.button.manage_tasks": "🔧 Управление заданиями",
        "common.cancel": "❌ Отмена",
        "common.title_not_specified": "Без названия",
        "common.location_tba": "Место уточняется",
        "common.time_tba": "Время уточняется",
        "diag.error_msg": "❌ Ошибка диагностики: {error}",
        "diag.commands_error": "❌ Ошибка диагностики команд: {error}",
        "community.cancel": "❌ Отменить создание",
        "community.event_cancelled": "❌ Создание события отменено.",
        "community.cancel_group_title": "❌ **Создание группового события отменено.**\n\n",
        "community.cancel_return_or_stay": "Вы можете вернуться в группу или остаться в боте:",
        "community.cancel_create_via_start": "Если хотите создать событие, нажмите /start",
        "community.location_link": "🔗 Вставить готовую ссылку",
        "community.location_map": "🌍 Найти на карте",
        "community.location_coords": "📍 Ввести координаты",
        "community.confirm_chat_only": "✅ Только чат",
        "community.confirm_world": "🌍 Чат + World",
        "group.list.error": "❌ Ошибка отображения. Попробуйте позже.",
        "group.list.error_events": "❌ Ошибка отображения событий",
        "group.list.error_try_later": "Попробуйте позже или обратитесь к администратору.",
        "group.welcome_added": "🎉 Бот добавлен в группу!",
        "group.welcome_press_start": "Жми /start для создания и поиска событий",
        "group.welcome_pin": "📌 Закрепи, чтобы все знали",
        "group.topic_closed": "Бот не может отправлять сообщения в закрытую тему.",
        "group.test_autodelete_ok": "✅ Тест автоудаления запущен! Сообщение удалится через 10 секунд.",
        "group.test_autodelete_msg": "🧪 Тестовое сообщение — должно удалиться через 10 секунд",
        "group.manage_events.title": "📋 **Управление событиями**",
        "group.manage_events.hint": "• Создать новое событие через кнопку ➕ Создать событие\n",
        "group.hide_bot.text": "👁️‍🗨️ **Спрятать бота**\n\n",
        "group.hide_bot.confirm_yes": "✅ Да, спрятать",
        "group.hide_bot.confirm": (
            "Вы действительно хотите скрыть все сообщения бота из этого чата?\n\n"
            "⚠️ **Это действие:**\n"
            "• Удалит все сообщения бота из чата\n"
            "• Очистит историю взаимодействий\n"
            "• Бот останется в группе, но не будет засорять чат\n\n"
            "💡 **Особенно полезно после создания события** - освобождает чат от служебных сообщений\n\n"
            "Для восстановления функций бота используйте команду /start"
        ),
        "group.manage_events.empty": "У вас нет событий для управления.\n\n💡 Вы можете:\n",
        "group.manage_events.resume_hint": ("• Возобновить закрытые события (если закрыты менее 24 ч назад)"),
        "group.button.back_to_list": "◀️ Назад к списку",
        "group.button.delete": "❌ Удалить",
        "group.manage.title": "⚙️ **Управление событием**",
        "group.manage.participants_count": "👥 Участников: {count}",
        "pager.date_shown": "📅 Показаны события на {date_type}",
        "reminder.event_started": "🎉 **Событие началось!**",
        "reminder.created_by": "*Создано пользователем @{username}*",
        "reminder.participants": "👥 **Участники ({count}):**",
        "reminder.no_participants": "👥 Пока нет участников",
        "reminder.join_cmd": "\n👉 Нажмите /joinevent{event_id} чтобы записаться",
        "reminder.24h_title": "⏰ **Напоминание о событии!**",
        "reminder.date_at_time": "📅 {date} в {time}",
        "reminder.place_unknown": "Место не указано",
        "reminder.date_unknown": "Дата не указана",
        "reminder.organizer_unknown": "Пользователь",
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
        "admin.event.usage": "Использование: /admin_event <id_события>",
        "admin.event.not_found": "Событие с ID {event_id} не найдено",
        "admin.event.invalid_id": "ID события должен быть числом",
        "admin.event.error": "Произошла ошибка при получении информации о событии",
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
        "search.no_last_request": "Нет данных о последнем запросе. Отправьте геолокацию.",
        "search.loading_toast": "🔍 Ищем события...",
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
        # Карточка события (подписи ссылок и создатель)
        "event.source_link": "Источник",
        "event.route_link": "Маршрут",
        "event.source_not_specified": "Источник не указан",
        "event.created_by": "Создано пользователем @{username}",
        # Заголовок списка событий
        "events.header.found_nearby": "🗺 Найдено рядом: <b>{count}</b>",
        "events.header.found_in_radius": "📍 Найдено в радиусе {radius} км: <b>{count}</b>",
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
        "pager.date_already_selected": "Эта дата уже выбрана",
        "pager.state_lost": "Состояние потеряно. Отправьте геолокацию заново.",
        "pager.date_switch_failed": "❌ Не удалось переключить дату",
        "pager.date_error": "❌ Произошла ошибка при переключении даты",
        "pager.page_edge": "Это крайняя страница",
        "pager.page_edge_alert": "⚠️ Это крайняя страница",
        "pager.page_failed": "❌ Не удалось перелистнуть страницу",
        "pager.state_not_found": "Состояние не найдено. Отправьте новую геолокацию.",
        "pager.request_error": "Ошибка обработки запроса",
        "pager.general_error": "Произошла ошибка",
        "pager.use_create": "Используйте команду /create",
        "diag.error": "Произошла ошибка при получении диагностики",
        "diag.search_error": "Произошла ошибка при получении диагностики поиска",
        "event.created": "Событие создано!",
        "event.completed": "✅ Мероприятие завершено!",
        "event.complete_error": "❌ Ошибка при завершении мероприятия",
        "event.not_found": "❌ Событие не найдено",
        "event.not_closed": "❌ Событие не закрыто, его нельзя возобновить",
        "event.resumed": "🔄 Мероприятие снова активно!",
        "event.resume_error": "❌ Ошибка при возобновлении мероприятия",
        "event.ready_to_forward": "✅ Сообщение готово к пересылке!",
        # Управление событием (экран 1/N)
        "manage_event.header": "🔧 Управление событием ({current}/{total}):",
        "manage_event.nav.list": "📋 Список",
        "manage_event.nav.back": "◀️ Назад",
        "manage_event.nav.forward": "▶️ Вперед",
        "manage_event.button.finish_event": "⛔ Завершить мероприятие",
        "manage_event.button.resume": "🔄 Возобновить мероприятие",
        "manage_event.button.edit": "✏ Редактировать",
        "manage_event.button.share": "🔗 Поделиться",
        "manage_event.status.open": "Активно",
        "manage_event.status.closed": "Завершено",
        "manage_event.status.canceled": "Отменено",
        "manage_event.status.unknown": "Неизвестно",
        "manage_event.time_tba": "Время не указано",
        "manage_event.status_label": "📊 Статус:",
        "event.updated": "✅ Событие обновлено!",
        "carousel.last_event": "⚠️ Это последнее событие",
        "carousel.first_event": "⚠️ Это первое событие",
        "carousel.back_to_menu": "🎯 Возврат в главное меню",
        "carousel.back_to_list": "📋 Возврат к списку событий",
        "edit.coords_invalid": ("❌ Неверные координаты. Широта: -90 до 90, долгота: -180 до 180."),
        "edit.coords_link_failed": (
            "❌ Не удалось определить координаты по ссылке. " "Попробуйте ввести координаты вручную."
        ),
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
        "create.location_prompt": "📍 **Как укажем место?**\n\nВыберите один из способов:",
        "create.city_saved": "**Город сохранен:** {city} ✅\n\n📍 **Как укажем место?**\n\nВыберите один из способов:",
        "create.city_saved_ask_place": (
            "**Город сохранен:** {city} ✅\n\n📍 **Введите название места** (например: Кафе 'Уют'):"
        ),
        "create.enter_city": "🏙️ **Введите город** (например: Москва):",
        "create.time_saved_ask_city": "**Время сохранено:** {time} ✅\n\n🏙️ **Введите город** (например: Москва):",
        "create.place_by_coords_message": "📍 **Место определено по координатам:** {lat}, {lng} ✅\n\n",
        "create.place_saved_then_desc": (
            "**Место сохранено** ✅\n{location_text}\n\n"
            "📝 **Введите описание события** (что будет происходить, кому интересно):"
        ),
        "create.invalid_coords": (
            "❌ **Неверный формат координат!**\n\n"
            "Используйте формат: **широта, долгота**\n"
            "Например: 55.7558, 37.6176\n\n"
            "Диапазоны:\n• Широта: -90 до 90\n• Долгота: -180 до 180"
        ),
        "create.link_failed": (
            "❌ Не удалось распознать ссылку Google Maps.\n\n"
            "Попробуйте:\n• Скопировать ссылку из приложения Google Maps\n"
            "• Или нажать кнопку '🔗 Вставить готовую ссылку'"
        ),
        "create.check_data_group": "📌 **Проверьте данные события для группы:**\n\n",
        "create.confirm_question": "✅ **Все данные корректны?**\nВыберите, где опубликовать событие.",
        "create.place_saved_short": (
            "📍 Место сохранено! ✅\n\n" "📝 Теперь введите описание (например: Вечерняя прогулка у океана):"
        ),
        "create.place_defined": "📍 Место определено: *{name}*\n\n",
        "create.add_description": "📝 Теперь добавьте описание события:",
        "create.location_use_buttons": (
            "❌ Пожалуйста, используйте кнопки ниже для указания места:\n\n"
            "• **🔗 Вставить готовую ссылку** — если у вас есть ссылка Google Maps\n"
            "• **🌍 Найти на карте** — чтобы найти место на карте\n"
            "• **📍 Ввести координаты** — если знаете широту и долготу"
        ),
        "create.location_label": "Локация:",
        "create.coordinates_label": "Координаты:",
        "create.location_link_saved": "Ссылка на карту сохранена",
        "create.confirm_location_question": "Всё верно?",
        "create.button_open_on_map": "🌍 Открыть на карте",
        "create.button_open_google_maps": "🌍 Открыть Google Maps",
        "create.button_yes": "✅ Да",
        "create.button_change": "❌ Изменить",
        "create.place_on_map": "Место на карте",
        "create.place_by_link": "Место по ссылке",
        "create.place_by_coords": "Место по координатам",
        "create.place_yandex": "Место на Яндекс.Картах",
        "create.check_event_data": "Проверьте данные мероприятия:",
        "create.label_title": "Название:",
        "create.label_date": "Дата:",
        "create.label_time": "Время:",
        "create.label_place": "Место:",
        "create.label_description": "Описание:",
        "create.confirm_instruction": "Если всё верно, нажмите ✅ Сохранить. Если нужно изменить — нажмите ❌ Отмена.",
        "create.button_save": "✅ Сохранить",
        "share.new_event": "Новое событие!",
        "share.time_at": "в",
        "share.more_events_in_bot": "Больше событий в боте:",
        "create.community.event_created_published": "🎉 **Событие создано и опубликовано!**\n",
        "create.community.published_in_group": "✅ Событие опубликовано в группе!\n",
        "create.community.link_to_message": "🔗 [Ссылка на сообщение]({url})\n\n",
        "create.community.available_in_world": "\n🌍 Событие также доступно в World-версии!\n",
        "create.community.world_publish_failed": "\n⚠️ Не смогли создать событие в World версии, создайте вручную.\n",
        "create.community.event_created_only": "✅ **Событие создано!**\n\n",
        "create.community.publish_to_group_failed": "⚠️ Не удалось опубликовать в группу, но событие сохранено.",
        "create.label_city": "Город:",
        "create.label_link": "Ссылка:",
        "create.paste_google_maps_link": "🔗 Вставьте сюда ссылку из Google Maps:",
        "create.group.enter_title": "✍️ **Введите название мероприятия:**",
        "create.group.welcome_pm": (
            "➕ **Создать событие «Community»**\n\n"
            "— Это событие будет добавлено в группу, из которой вы перешли.\n\n"
            "⬇️ **Напиши название события:**"
        ),
        "create.group.title_saved_ask_date": (
            "**Название сохранено:** *{title}* ✅\n\n" "📅 **Укажите дату** (например: 10.10.2025 18:00):"
        ),
        "create.group.ask_datetime": "📅 **Укажите дату и время** (например: 10.10.2025 18:00):",
        "create.group.invalid_datetime": (
            "❌ **Неверный формат даты!**\n\n"
            "📅 Введите дату в формате **ДД.ММ.ГГГГ ЧЧ:ММ**\n"
            "Например: 10.10.2025 18:00"
        ),
        "create.group.datetime_saved_ask_city": (
            "**Дата и время сохранены:** {datetime_text} ✅\n\n" "🏙️ **Введите город** (например: Москва):"
        ),
        "create.group.city_saved_ask_location": (
            "**Город сохранен:** {city} ✅\n\n" "📍 **Отправьте ссылку на место** (Google Maps или адрес):"
        ),
        "create.group.ask_location_link": "📍 **Отправьте ссылку на место** (Google Maps или адрес):",
        "create.group.location_saved_ask_description": (
            "**Локация сохранена:** {location} ✅\n\n" "📝 **Введите описание события:**"
        ),
        "create.validation.datetime_error": "❌ **Ошибка в формате даты!** Попробуйте еще раз.",
        "create.group.event_created": (
            "✅ **Событие создано!**\n\n"
            "**📌 {title}**\n"
            "📅 {datetime}\n"
            "🏙️ {city}\n"
            "📍 {location}\n"
            "📝 {description}\n\n"
            "*Создано пользователем @{created_by}*"
        ),
        "create.group.error_creating": ("❌ **Произошла ошибка при создании события.** Попробуйте еще раз."),
        "create.cancelled": "Создание отменено.",
        "create.cancelled_full": "❌ Создание мероприятия отменено.",
        "create.wait_already_started": "⏳ Подождите, создание события уже запущено...",
        "create.wait_in_progress": "⏳ Подождите, событие уже создается...",
        "create.translating": "⏳ Секунду, перевожу на английский...",
        "create.translated": "✅ Готово.",
        "create.translation_delayed": "⏳ Перевод задерживается, попробую ещё раз через 30 секунд.",
        "create.validation.no_text": "❌ **Пожалуйста, отправьте текстовое сообщение!**\n\n{next_prompt}",
        "create.validation.invalid_location_link": (
            "❌ Это не похоже на ссылку или координаты.\n\n"
            "📍 Отправьте ссылку Google Maps (или широту, долготу через запятую):"
        ),
        "create.validation.location_link_parse_failed": (
            "❌ Не удалось распознать ссылку.\n\n"
            "📍 Отправьте рабочую ссылку из Google Maps (или координаты через запятую):"
        ),
        "create.validation.invalid_date_format": (
            "❌ **Неверный формат даты!**\n\n" "📅 Введите дату в формате **ДД.ММ.ГГГГ**\n" "Например: 15.12.2024"
        ),
        "create.validation.invalid_date_value": (
            "❌ **Неверная дата!**\n\n"
            "Проверьте правильность даты:\n"
            "• День: 1-31\n"
            "• Месяц: 1-12\n"
            "• Год: 2024-2030\n\n"
            "Например: 15.12.2024\n\n"
            "📅 **Введите дату** (например: 15.12.2024):"
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
        "edit.button.finish": "✅ Готово",
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
        "myevents.button.main_menu": "🏠 Главное меню",
        "myevents.button.my_quests": "🏆 Мои квесты",
        "myevents.button.my_events": "📋 Мои события",
        "common.no_title": "Без названия",
        "common.closed": "(закрыто)",
        "tasks.press_location_hint": (
            "Нажмите кнопку '📍 Отправить геолокацию' чтобы начать!\n\n"
            "💡 Если кнопка не работает:\n\n"
            "• Жми '🌍 Найти на карте'\n"
            "и вставь ссылку\n\n"
            "• Или отправь координаты\n"
            "пример: -8.4095, 115.1889"
        ),
        "community.date_shown": "📅 Показаны события на {date_type}",
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
        "menu.greeting": 'Hello! @{bot_username} "World" version - your digital activity assistant.\n\n'
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
        "help.feedback.text": (
            "💬 **Write feedback to Developer**\n\n"
            "Thanks for using {bot_username}! 🚀\n\n"
            "If you have suggestions, feedback or just want to say thanks - "
            "write to me personally:\n\n"
            "👨‍💻 **@Fincontro**\n\n"
            "I'm always happy to hear from you! 😊"
        ),
        "help.button.write": "💬 Message @Fincontro",
        "command.language": "🌐 Choose language / Выберите язык",
        "command.group.start": "🎉 Chat events",
        "commands.list": (
            "📋 **Bot commands:**\n\n"
            "🚀 /start - Start bot and show menu\n"
            "❓ /help - Show help\n"
            "📍 /nearby - Find nearby events\n"
            "➕ /create - Create event\n"
            "📋 /myevents - My events\n"
            "🔗 /share - Add bot to chat\n\n"
            "💡 **Tip:** Use menu buttons for easy navigation!"
        ),
        # Group chat
        "group.greeting": '👋 Hello! I am {bot_username} - "Community" version.\n\n'
        "🎯 **In this chat I help:**\n"
        "• Create community member events\n"
        "• Show all events created in this chat\n"
        "• Go to full bot for geolocation search\n\n"
        "💡 **Choose an action:**",
        "group.panel.text": '👋 Hello! I am {bot_username} - "Community" version.\n\n'
        "🎯 What I can do:\n"
        "• Create community member events\n"
        "• Show events in this chat\n"
        '• Full "World" version\n\n'
        "💡 Choose an action:",
        "group.button.create_event": "➕ Create event",
        "group.button.events_list": "📋 Events in this chat",
        "group.button.full_version": '🚀 Full "World" version',
        "group.button.language_ru": "🌐 Язык (RU)",
        "group.button.language_en": "🌐 Language (EN)",
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
        "group.card.join": "✅ Join",
        "group.card.leave": "❌ Leave",
        "group.card.participants": "👥 Participants",
        "group.card.footer": "💡 **Create via /start**",
        "group.list.admin_footer": "",
        "group.list.user_footer": "",
        "group.load_error": "❌ Error loading event",
        "group.language_changed": "✅ Language changed",
        "group.panel.what_can_do": (
            '👋 Hello! I am @{bot_username} - "Community" version.\n\n'
            "🎯 What I can do:\n\n"
            "• Create events\n"
            "• Show events in this chat\n"
            '• Full "World" version\n\n'
            "💡 Choose an action:"
        ),
        "group.nudge_commands": "ℹ️ To open commands, press `/` or type `/start@{bot_username}`.",
        "group.activated": "🤖 {bot_username} activated!",
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
        # Event card (link labels and creator)
        "event.source_link": "Source",
        "event.route_link": "Route",
        "event.source_not_specified": "Source not specified",
        "event.created_by": "Created by @{username}",
        # Events list header
        "events.header.found_nearby": "🗺 Found nearby: <b>{count}</b>",
        "events.header.found_in_radius": "📍 Found within {radius} km: <b>{count}</b>",
        "events.header.from_users": "• 👥 From users: {count}",
        "events.header.from_groups": "• 💥 From groups: {count}",
        "events.header.from_sources": "• 🌐 From sources: {count}",
        "events.header.ai_parsed": "• 🤖 AI parsed: {count}",
        "events.summary.found": "🗺 Found {count} events nearby!",
        # Pagination
        "pager.prev": "◀️ Back",
        "pager.next": "Next ▶️",
        "pager.page": "Page {page}/{total}",
        "pager.today": "📅 Today",
        "pager.today_selected": "📅 Today ✅",
        "pager.tomorrow": "📅 Tomorrow",
        "pager.tomorrow_selected": "📅 Tomorrow ✅",
        "pager.radius_km": "{radius} km",
        "pager.radius_expanded": "✅ Radius expanded to {radius} km",
        "pager.date_already_selected": "This date is already selected",
        "pager.state_lost": "State lost. Send your location again.",
        "pager.date_switch_failed": "❌ Failed to switch date",
        "pager.date_error": "❌ Error switching date",
        "pager.page_edge": "This is the last page",
        "pager.page_edge_alert": "⚠️ This is the last page",
        "pager.page_failed": "❌ Failed to flip page",
        "pager.state_not_found": "State not found. Send a new location.",
        "pager.request_error": "Request processing error",
        "pager.general_error": "An error occurred",
        "pager.use_create": "Use the /create command",
        "diag.error": "Error getting diagnostics",
        "diag.search_error": "Error getting search diagnostics",
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
        "create.time_saved": "**Time saved:** {time} ✅",
        "create.enter_location": "📍 **Select a location method**",
        "create.location_saved": (
            "**Location saved** ✅\n{location_text}\n\n"
            "📝 **Enter event description**\n(what will happen, who it's for):"
        ),
        "create.enter_description": ("📝 **Enter event description**\n(what will happen, who it's for):"),
        "create.location_prompt": "📍 **How would you like to set the location?**\n\nChoose one of the options:",
        "create.city_saved": (
            "**City saved:** {city} ✅\n\n📍 **How would you like to set the location?**\n\nChoose one of the options:"
        ),
        "create.city_saved_ask_place": "**City saved:** {city} ✅\n\n📍 **Enter place name** (e.g.: Café):",
        "create.enter_city": "🏙️ **Enter city** (e.g.: Moscow):",
        "create.time_saved_ask_city": "**Time saved:** {time} ✅\n\n🏙️ **Enter city** (e.g.: Moscow):",
        "create.place_by_coords_message": "📍 **Place set by coordinates:** {lat}, {lng} ✅\n\n",
        "create.place_saved_then_desc": (
            "**Place saved** ✅\n{location_text}\n\n" "📝 **Enter event description** (what will happen, who it's for):"
        ),
        "create.invalid_coords": (
            "❌ **Invalid coordinates format!**\n\n"
            "Use format: **latitude, longitude**\n"
            "E.g.: 55.7558, 37.6176\n\n"
            "Ranges: Latitude -90 to 90, Longitude -180 to 180"
        ),
        "create.link_failed": (
            "❌ Could not recognize Google Maps link.\n\n"
            "Try:\n• Copy link from Google Maps app\n"
            "• Or tap '🔗 Paste link' button"
        ),
        "create.check_data_group": "📌 **Check event data for the group:**\n\n",
        "create.confirm_question": "✅ **All data correct?**\nChoose where to publish the event.",
        "create.place_saved_short": "📍 Place saved! ✅\n\n📝 Now enter description (e.g.: Evening walk by the ocean):",
        "create.place_defined": "📍 Place set: *{name}*\n\n",
        "create.add_description": "📝 Now add event description:",
        "create.location_use_buttons": (
            "❌ Please use the buttons below to set the place:\n\n"
            "• **🔗 Paste link** — if you have a Google Maps link\n"
            "• **🌍 Find on map** — to find the place on the map\n"
            "• **📍 Enter coordinates** — if you know latitude and longitude"
        ),
        "create.location_label": "Location:",
        "create.coordinates_label": "Coordinates:",
        "create.location_link_saved": "Map link saved",
        "create.confirm_location_question": "Is everything correct?",
        "create.button_open_on_map": "🌍 Open on map",
        "create.button_open_google_maps": "🌍 Open Google Maps",
        "create.button_yes": "✅ Yes",
        "create.button_change": "❌ Change",
        "create.place_on_map": "Place on map",
        "create.place_by_link": "Place by link",
        "create.place_by_coords": "Place by coordinates",
        "create.place_yandex": "Place on Yandex Maps",
        "create.check_event_data": "Check event data:",
        "create.label_title": "Title:",
        "create.label_date": "Date:",
        "create.label_time": "Time:",
        "create.label_place": "Location:",
        "create.label_description": "Description:",
        "create.confirm_instruction": "If everything is correct, tap ✔️ Save. To change something — tap ❌ Cancel.",
        "create.button_save": "✅ Save",
        "share.new_event": "New event!",
        "share.time_at": "at",
        "share.more_events_in_bot": "More events in the bot:",
        "create.community.event_created_published": "🎉 **Event created and published!**\n",
        "create.community.published_in_group": "✅ Event published in the group!\n",
        "create.community.link_to_message": "🔗 [Link to message]({url})\n\n",
        "create.community.available_in_world": "\n🌍 Event is also available in the World version!\n",
        "create.community.world_publish_failed": (
            "\n⚠️ Could not create event in World version, please create manually.\n"
        ),
        "create.community.event_created_only": "✅ **Event created!**\n\n",
        "create.community.publish_to_group_failed": "⚠️ Could not publish to the group, but the event was saved.",
        "create.label_city": "City:",
        "create.label_link": "Link:",
        "create.paste_google_maps_link": "🔗 Paste your Google Maps link here:",
        "create.group.enter_title": "✍️ **Enter event title:**",
        "create.group.welcome_pm": (
            "➕ **Create Community event**\n\n"
            "— This event will be added to the group you came from.\n\n"
            "⬇️ **Write the event title:**"
        ),
        "create.group.title_saved_ask_date": (
            "**Title saved:** *{title}* ✅\n\n" "📅 **Enter date and time** (e.g.: 10.10.2025 18:00):"
        ),
        "create.group.ask_datetime": "📅 **Enter date and time** (e.g.: 10.10.2025 18:00):",
        "create.group.invalid_datetime": (
            "❌ **Invalid date format!**\n\n"
            "📅 Enter date in format **DD.MM.YYYY HH:MM**\n"
            "Example: 10.10.2025 18:00"
        ),
        "create.group.datetime_saved_ask_city": (
            "**Date and time saved:** {datetime_text} ✅\n\n" "🏙️ **Enter city** (e.g.: Moscow):"
        ),
        "create.group.city_saved_ask_location": (
            "**City saved:** {city} ✅\n\n" "📍 **Send link to the place** (Google Maps or address):"
        ),
        "create.group.ask_location_link": "📍 **Send link to the place** (Google Maps or address):",
        "create.group.location_saved_ask_description": (
            "**Location saved:** {location} ✅\n\n" "📝 **Enter event description:**"
        ),
        "create.validation.datetime_error": "❌ **Date format error!** Please try again.",
        "create.group.event_created": (
            "✅ **Event created!**\n\n"
            "**📌 {title}**\n"
            "📅 {datetime}\n"
            "🏙️ {city}\n"
            "📍 {location}\n"
            "📝 {description}\n\n"
            "*Created by @{created_by}*"
        ),
        "create.group.error_creating": ("❌ **An error occurred while creating the event.** Please try again."),
        "create.cancelled": "Creation cancelled.",
        "create.cancelled_full": "❌ Event creation cancelled.",
        "create.wait_already_started": "⏳ Please wait, event creation is already in progress...",
        "create.wait_in_progress": "⏳ Please wait, event is being created...",
        "create.translating": "⏳ One moment, translating to English...",
        "create.translated": "✅ Done.",
        "create.translation_delayed": "⏳ Translation delayed, will retry in 30 seconds.",
        "create.validation.no_text": "❌ **Please send a text message!**\n\n{next_prompt}",
        "create.validation.invalid_location_link": (
            "❌ This doesn't look like a link or coordinates.\n\n"
            "📍 Send a Google Maps link (or latitude, longitude separated by comma):"
        ),
        "create.validation.location_link_parse_failed": (
            "❌ Could not recognize the link.\n\n"
            "📍 Send a valid Google Maps link (or coordinates separated by comma):"
        ),
        "create.validation.invalid_date_format": (
            "❌ **Invalid date format!**\n\n" "📅 Enter date in format **DD.MM.YYYY**\n" "Example: 15.12.2024"
        ),
        "create.validation.invalid_date_value": (
            "❌ **Invalid date!**\n\n"
            "Check that the date is valid:\n"
            "• Day: 1-31\n"
            "• Month: 1-12\n"
            "• Year: 2024-2030\n\n"
            "Example: 15.12.2024\n\n"
            "📅 **Enter date** (e.g.: 15.12.2024):"
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
        "tasks.button.find_on_map": "🌍 Open Google Maps",
        "tasks.button.main_menu": "🏠 Main menu",
        # My events
        "myevents.title": "📋 My events",
        "myevents.empty": "You don't have any created events yet.",
        "myevents.create_first": "Create your first event with /create command",
        # My quests
        "mytasks.title": "🏆 My quests",
        "mytasks.empty": "You have no active tasks.",
        "mytasks.empty_hint": "Tap «Interesting places» to get new tasks!",
        "mytasks.active_header": "📋 **Your active tasks:**",
        "mytasks.reward_line": "Completion + 3 🚀",
        "mytasks.place_label": "Location:",
        "mytasks.km_suffix": "km",
        "mytasks.motivation_line": "⏰ 24 hours to complete",
        "mytasks.time_to_complete": "Time to complete:",
        "mytasks.label_category": "Category:",
        "mytasks.label_description": "Description:",
        "mytasks.button.back_to_list": "🔧 Back to tasks list",
        "mytasks.button.back_to_tasks": "◀️ Back to tasks",
        "mytasks.button.done": "✅ Done",
        "mytasks.button.cancel": "❌ Cancel",
        "mytasks.completed_title": "✅ **Task completed!**",
        "mytasks.share_impressions": (
            "Share your experience:\n• How did it go?\n• What did you feel?\n• How did it help you?\n\n"
            "📸 **Send a photo** of the place you visited\nor **write your review** as text:"
        ),
        "mytasks.cancel_error": "❌ **Error cancelling task**\n\nCould not cancel the task. Please try again later.",
        "tasks.choose_section": "Choose section:",
        "tasks.not_found": "Task not found",
        "tasks.cancelled": "✅ Task cancelled",
        "tasks.accepted": "✅ Task accepted!",
        "tasks.added": "✅ Task added to active!",
        "tasks.start_error": "❌ Error starting task",
        "tasks.page_edge": "This is the last page",
        "tasks.require_location": "📍 Location required",
        "tasks.complete_not_found": "❌ Error: no task found to complete.",
        "tasks.task_not_found": "❌ Error: task not found.",
        "tasks.category.food": "🍔 Food",
        "tasks.category.health": "💪 Health",
        "tasks.category.places": "🌟 Interesting places",
        "tasks.places_found": "📍 Places found: {count}",
        "tasks.km_from_you": "📍 {distance:.1f} km from you",
        "tasks.promo_code": "🎁 Promo code: `{code}`",
        "tasks.take_quest": "🎯 Take quest",
        "tasks.button.list": "📋 List",
        "tasks.no_places_in_category": "❌ No places in this category yet.",
        "tasks.quest_added_success": "✅ Quest for '{name}' added to My quests",
        "tasks.quest_already_added": "⚠️ Quest for '{name}' is already in My quests",
        "tasks.place_not_found": "❌ Place not found",
        "tasks.quest_already_short": "🙈 Quest already added",
        "tasks.quest_add_error": "❌ Error adding quest: {error}",
        "tasks.location_received": (
            "✅ **Location received!**\n\n"
            "Choose category for personalized tasks:\n\n"
            "🍔 **Food** - cafes, restaurants, street food\n"
            "💪 **Health** - sports, yoga, spa, clinics\n"
            "🌟 **Interesting places** - parks, exhibitions, temples"
        ),
        "tasks.categories_intro": (
            "Choose task category:\n\n"
            "🍔 **Food** - cafes, restaurants, street food\n"
            "💪 **Health** - sports, yoga, spa, clinics\n"
            "🌟 **Interesting places** - parks, exhibitions, temples"
        ),
        "myevents.auto_closed": "🤖 Auto-closed {count} past events",
        "myevents.header": "📋 **My events:**\n",
        "myevents.balance": "**Balance {rocket_balance} 🚀**\n",
        "myevents.created_by_me": "📝 **Created by me:**",
        "myevents.recently_closed": "🔴 **Recently closed ({count}):**",
        "myevents.and_more": "... and {count} more events",
        "myevents.and_more_closed": "... and {count} more closed",
        "myevents.no_events": "You have no events yet.",
        "myevents.button.manage_events": "🔧 Manage events",
        "myevents.button.all_added": "📋 All added events",
        "myevents.button.manage_tasks": "🔧 Manage tasks",
        "common.cancel": "❌ Cancel",
        "common.title_not_specified": "Untitled",
        "common.location_tba": "Location TBA",
        "common.time_tba": "Time TBA",
        "diag.error_msg": "❌ Diagnostics error: {error}",
        "diag.commands_error": "❌ Commands diagnostics error: {error}",
        "community.cancel": "❌ Cancel creation",
        "community.event_cancelled": "❌ Event creation cancelled.",
        "community.cancel_group_title": "❌ **Group event creation cancelled.**\n\n",
        "community.cancel_return_or_stay": "You can return to the group or stay in the bot:",
        "community.cancel_create_via_start": "To create an event, press /start",
        "community.location_link": "🔗 Paste link",
        "community.location_map": "🌍 Find on map",
        "community.location_coords": "📍 Enter coordinates",
        "community.confirm_chat_only": "✅ Chat only",
        "community.confirm_world": "🌍 Chat + World",
        "group.list.error": "❌ Display error. Try again later.",
        "group.list.error_events": "❌ Error displaying events",
        "group.list.error_try_later": "Please try again later or contact the administrator.",
        "group.welcome_added": "🎉 Bot added to the group!",
        "group.welcome_press_start": "Press /start to create and find events",
        "group.welcome_pin": "📌 Pin this message so everyone sees it",
        "group.topic_closed": "The bot cannot send messages to a closed topic.",
        "group.test_autodelete_ok": "✅ Autodelete test started! Message will disappear in 10 seconds.",
        "group.test_autodelete_msg": "🧪 Test message — will be deleted in 10 seconds",
        "group.manage_events.title": "📋 **Manage events**",
        "group.manage_events.hint": "• Create new event via ➕ Create event button\n",
        "group.hide_bot.text": "👁️‍🗨️ **Hide bot**\n\n",
        "group.hide_bot.confirm_yes": "✅ Yes, hide",
        "group.hide_bot.confirm": (
            "Do you want to hide all bot messages in this chat?\n\n"
            "⚠️ **This will:**\n"
            "• Remove all bot messages from the chat\n"
            "• Clear interaction history\n"
            "• Bot stays in the group but won't clutter the chat\n\n"
            "💡 **Useful after creating an event** - frees the chat from service messages\n\n"
            "Use /start to restore bot functions"
        ),
        "group.manage_events.empty": "You have no events to manage.\n\n💡 You can:\n",
        "group.manage_events.resume_hint": ("• Resume closed events (if closed less than 24h ago)"),
        "group.button.back_to_list": "◀️ Back to list",
        "group.button.delete": "❌ Delete",
        "group.manage.title": "⚙️ **Event management**",
        "group.manage.participants_count": "👥 Participants: {count}",
        "pager.date_shown": "📅 Events shown for {date_type}",
        "reminder.event_started": "🎉 **Event started!**",
        "reminder.created_by": "*Created by @{username}*",
        "reminder.participants": "👥 **Participants ({count}):**",
        "reminder.no_participants": "👥 No participants yet",
        "reminder.join_cmd": "\n👉 Press /joinevent{event_id} to join",
        "reminder.24h_title": "⏰ **Event reminder!**",
        "reminder.date_at_time": "📅 {date} at {time}",
        "reminder.place_unknown": "Place not specified",
        "reminder.date_unknown": "Date not specified",
        "reminder.organizer_unknown": "User",
        "event.created": "Event created!",
        "event.completed": "✅ Event completed!",
        "event.complete_error": "❌ Error completing event",
        "event.not_found": "❌ Event not found",
        "event.not_closed": "❌ Event is not closed, cannot resume",
        "event.resumed": "🔄 Event active again!",
        "event.resume_error": "❌ Error resuming event",
        "event.ready_to_forward": "✅ Message ready to forward!",
        # Event management screen (1/N)
        "manage_event.header": "🔧 Event management ({current}/{total}):",
        "manage_event.nav.list": "📋 List",
        "manage_event.nav.back": "◀️ Back",
        "manage_event.nav.forward": "▶️ Next",
        "manage_event.button.finish_event": "⛔ Finish event",
        "manage_event.button.resume": "🔄 Resume event",
        "manage_event.button.edit": "✏ Edit",
        "manage_event.button.share": "🔗 Share",
        "manage_event.status.open": "Active",
        "manage_event.status.closed": "Closed",
        "manage_event.status.canceled": "Canceled",
        "manage_event.status.unknown": "Unknown",
        "manage_event.time_tba": "Time not specified",
        "manage_event.status_label": "📊 Status:",
        "event.updated": "✅ Event updated!",
        "carousel.last_event": "⚠️ This is the last event",
        "carousel.first_event": "⚠️ This is the first event",
        "carousel.back_to_menu": "🎯 Back to main menu",
        "carousel.back_to_list": "📋 Back to events list",
        "edit.coords_invalid": "❌ Invalid coordinates. Latitude must be -90 to 90, longitude -180 to 180.",
        "edit.coords_link_failed": "❌ Could not get coordinates from link. Try entering coordinates manually.",
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
        "admin.event.usage": "Usage: /admin_event <event_id>",
        "admin.event.not_found": "Event with ID {event_id} not found",
        "admin.event.invalid_id": "Event ID must be a number",
        "admin.event.error": "Error getting event information",
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
        "search.no_last_request": "No last request data. Send your location.",
        "search.loading_toast": "🔍 Searching for events...",
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
        "edit.button.finish": "✅ Done",
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
        "myevents.button.main_menu": "🏠 Main menu",
        "myevents.button.my_quests": "🏆 My quests",
        "myevents.button.my_events": "📋 My events",
        "common.no_title": "Untitled",
        "common.closed": "(closed)",
        "tasks.press_location_hint": (
            "Tap '📍 Send location' button to start!\n\n"
            "💡 If button doesn't work:\n\n"
            "• Tap '🌍 Find on map'\n"
            "and paste a link\n\n"
            "• Or send coordinates\n"
            "e.g.: -8.4095, 115.1889"
        ),
        "community.date_shown": "📅 Events shown for {date_type}",
    },
}


def get_bot_username() -> str:
    """Username бота для подстановки в тексты (без @). Из BOT_USERNAME или config."""
    try:
        from config import load_settings

        return load_settings().bot_username
    except Exception:
        import os

        return (os.getenv("BOT_USERNAME") or "MyGuide_EventBot").strip()


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

    # Подстановка username бота (из BOT_USERNAME / config)
    if result and "{bot_username}" in result:
        result = result.replace("{bot_username}", get_bot_username())
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


def get_user_language_or_default(user_id: int, default: str = "ru") -> str:
    """Реэкспорт из user_language для совместимости с group_chat_handlers."""
    from utils.user_language import get_user_language_or_default as _get

    return _get(user_id, default)
