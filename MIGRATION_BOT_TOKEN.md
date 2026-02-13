# Миграция на новый Telegram-бот (токен и username)

## Что сделано в коде

- Токен **только** из `TELEGRAM_TOKEN` (нет хардкода в коде).
- Webhook при старте: `delete_webhook(drop_pending_updates=True)` → `set_webhook(url)`; в логах: `Webhook successfully set`.
- Username бота из `BOT_USERNAME` или `bot_info.username`; хардкод `EventAroundBot` заменён на конфиг/функцию.
- При 403 (пользователь заблокировал бота / не нажал /start у нового бота) — логируем и не падаем (`task_notifications`, `messaging_utils` уже обрабатывали группы).
- Scheduler запускается один раз при старте (singleton в `webhook_attach`).
- В БД нет привязки к bot_id; пользователи — по Telegram `user_id`.

## Перед деплоем нового бота

1. **Снять webhook у старого бота** (один раз):
   ```bash
   set OLD_TELEGRAM_TOKEN=<старый_токен>
   python scripts/delete_webhook_old_bot.py
   ```
   Или: `python scripts/delete_webhook_old_bot.py <старый_токен>`

2. **Обновить токен везде:**
   - Railway: Variables → `TELEGRAM_TOKEN` = новый токен.
   - В репо обновлены: `app.local.env`, `railway.env`, `.env.local`.
   - GitHub Actions: если деплой использует `secrets.TELEGRAM_TOKEN` — обновить секрет в настройках репозитория.

3. **Задать username нового бота** (для текстов и ссылок до первого `get_me()`):
   - Railway: `BOT_USERNAME` = username нового бота **без @** (например `MyNewEventBot`).

## После деплоя

- В логах при старте: `Webhook successfully set`, `Scheduler initialized`, `Бот инициализирован и готов к работе`.
- Проверить: `/start`, команды, webhook (админская `diag_webhook`), ingest, переводы.
- Ожидаемо: 401/Invalid token не должно быть; «Conflict: webhook already set» — только если старый бот ещё держал webhook (решается п.1).

## Рассылка «Мы переехали» от старого бота

Чтобы **разово** отправить всем пользователям из БД сообщение от **старого** бота со ссылкой на нового:

```bash
set OLD_TELEGRAM_TOKEN=<старый_токен>
set NEW_BOT_USERNAME=<новый_username_без_@>
# DATABASE_URL уже в app.local.env / .env
python scripts/broadcast_old_bot_moved.py
```

Сначала проверка без отправки (сколько пользователей):
```bash
python scripts/broadcast_old_bot_moved.py --dry-run
```

Скрипт берёт все `user_id` из таблицы `users`, шлёт каждому сообщение от старого бота (задержка между сообщениями ~0.08 с). 403 (заблокировали бота) пропускает без падения.

## Опционально: старый бот как редирект

Если старый бот временно остаётся в работе и должен только направлять в нового:
```bash
set OLD_TELEGRAM_TOKEN=<старый_токен>
set NEW_BOT_USERNAME=<новый_username_без_@>
python scripts/old_bot_redirect.py
```
Он будет отвечать на любое сообщение ссылкой на нового бота.
