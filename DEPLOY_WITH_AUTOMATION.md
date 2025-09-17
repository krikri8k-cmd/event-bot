# 🚀 Деплой Event-Bot с Автоматизацией

## 📋 Что включено в деплой

### 🤖 **Основные компоненты:**
- **Telegram бот** - обработка пользователей
- **Автоматизация парсинга** - каждые 12 часов
- **Автоочистка событий** - каждые 6 часов  
- **API сервер** - для веб-интерфейса
- **Правильная архитектура** - events_parser → events

### ⏰ **Расписание автоматизации:**
```
🌅 УТРЕННИЙ ПАРСИНГ (~08:00):
   • Парсинг BaliForum
   • Синхронизация в events
   • Очистка старых событий

🌙 ВЕЧЕРНИЙ ПАРСИНГ (~20:00):
   • Обновление событий
   • Подготовка к следующему дню
   • Логирование статистики
```

## 🚂 Деплой на Railway

### **Быстрый деплой:**
```bash
# Способ 1: Автоматический скрипт
python deploy.py

# Способ 2: Batch файл (Windows)
deploy.bat

# Способ 3: Ручной деплой
git add .
git commit -m "Deploy with automation"
git push origin main
railway up
```

### **Первоначальная настройка Railway:**
```bash
# 1. Установить Railway CLI
npm install -g @railway/cli

# 2. Залогиниться
railway login

# 3. Создать проект или подключиться
railway init
# или
railway link

# 4. Задеплоить
railway up
```

## 🔧 Переменные окружения

### **Обязательные:**
```env
DATABASE_URL=postgresql://...
TELEGRAM_TOKEN=your_bot_token
OPENAI_API_KEY=your_openai_key
```

### **Опциональные:**
```env
GOOGLE_MAPS_API_KEY=your_maps_key
MEETUP_API_KEY=your_meetup_key
EVENTBRITE_API_KEY=your_eventbrite_key

# Настройки автоматизации
ENABLE_BALIFORUM=1
AI_PARSE_ENABLE=1
AI_GENERATE_SYNTHETIC=0
```

## 📊 Мониторинг

### **Railway команды:**
```bash
# Логи приложения
railway logs

# Статус сервиса  
railway status

# Открыть в браузере
railway open

# Подключиться к БД
railway connect
```

### **Проверка работы:**
```bash
# Проверить здоровье API
curl https://your-app.railway.app/health

# Проверить статистику событий
curl https://your-app.railway.app/api/events/stats
```

## 🔄 Обновление деплоя

### **При изменениях в коде:**
```bash
git add .
git commit -m "Update: your changes"
git push origin main
railway up --detach
```

### **При изменении переменных:**
```bash
railway variables set VARIABLE_NAME=value
railway up --detach
```

## 🐛 Диагностика проблем

### **Частые проблемы:**

**1. Бот не отвечает:**
```bash
railway logs | grep ERROR
# Проверить TELEGRAM_TOKEN
```

**2. Автоматизация не работает:**
```bash
railway logs | grep "modern_scheduler"
# Проверить DATABASE_URL и ENABLE_BALIFORUM
```

**3. База данных недоступна:**
```bash
railway connect
# Проверить DATABASE_URL
```

**4. Нет событий:**
```bash
# Проверить в логах
railway logs | grep "BaliForum"
# Проверить OPENAI_API_KEY для AI парсинга
```

## 📈 Масштабирование

### **Настройки ресурсов:**
- **Memory**: 1GB (минимум)
- **CPU**: 1 vCPU
- **Storage**: 1GB для логов

### **Оптимизация:**
- Автоматизация: 12 часов (оптимально)
- Очистка: 6 часов
- Логи: ротация каждые 7 дней

## ✅ Чек-лист деплоя

- [ ] Переменные окружения настроены
- [ ] База данных подключена
- [ ] Telegram бот токен валиден
- [ ] OpenAI API ключ работает
- [ ] Railway проект создан и подключен
- [ ] Код закоммичен в git
- [ ] Деплой выполнен успешно
- [ ] Логи показывают работу автоматизации
- [ ] Бот отвечает в Telegram
- [ ] События парсятся и сохраняются

## 🎉 Готово!

После успешного деплоя у вас будет:
- ✅ Работающий Telegram бот
- ✅ Автоматическое пополнение событий  
- ✅ Правильная архитектура данных
- ✅ Мониторинг и логирование
- ✅ Автоочистка старых данных

**Ваш Event-Bot готов к продуктивной работе!** 🎯
