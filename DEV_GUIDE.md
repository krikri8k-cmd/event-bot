# 🚀 EventBot - Руководство разработчика

## 🎯 Быстрый старт

### Запуск бота (рекомендуется)
```bash
make dev
```
**Что происходит:**
- ✅ Автоматически убивает зависшие процессы
- ✅ Находит свободный порт (8000, 8001, 8002...)
- ✅ Устанавливает переменные окружения
- ✅ Запускает бота с правильным webhook URL

### Запуск API сервера
```bash
make api
```
**Что происходит:**
- ✅ Автоматически убивает зависшие процессы  
- ✅ Находит свободный порт
- ✅ Подключается к Railway БД
- ✅ Запускает API сервер

### Тестирование Baliforum
```bash
make test
```

## 🛠️ Альтернативные способы

### PowerShell скрипты
```powershell
# Запуск бота
.\scripts\start-dev.ps1

# Запуск API
.\scripts\start-api.ps1

# С кастомным портом
.\scripts\start-dev.ps1 -DefaultPort 9000
```

### Python утилита
```bash
# Настройка окружения для бота
python utils/port_manager.py bot

# Настройка окружения для API
python utils/port_manager.py api
```

## 🔧 Ручная очистка портов

### Если порт все еще занят:
```powershell
# Найти процесс на порту 8000
netstat -ano | findstr :8000

# Убить по PID
taskkill /PID <PID> /F

# Или убить все Python процессы
taskkill /F /IM python.exe
```

### PowerShell команды:
```powershell
# Найти процесс на порту
Get-NetTCPConnection -LocalPort 8000

# Убить все Python процессы
Get-Process python | Stop-Process -Force
```

## 📋 Переменные окружения

### Для бота:
- `PORT` - порт сервера (автоматически)
- `WEBHOOK_URL` - URL для Telegram webhook (автоматически)
- `TELEGRAM_TOKEN` - токен бота (dummy для локальной разработки)
- `ENABLE_BALIFORUM` - включить Baliforum (1)

### Для API:
- `PORT` - порт сервера (автоматически)
- `DATABASE_URL` - URL Railway БД (автоматически)
- `ENABLE_BALIFORUM` - включить Baliforum (1)

## 🎉 Преимущества

✅ **Никаких проблем с портами** - автоматический поиск свободного  
✅ **Автоматическая очистка** - убивает зависшие процессы  
✅ **Правильные URL** - webhook URL всегда соответствует порту  
✅ **Простота** - одна команда `make dev`  
✅ **Надежность** - работает на Windows/PowerShell  

## 🚨 Если что-то пошло не так

1. **Перезагрузи терминал** - закрой и открой PowerShell
2. **Используй другой порт** - `make dev` автоматически найдет свободный
3. **Очисти вручную** - `make clean` или `taskkill /F /IM python.exe`
4. **Проверь процессы** - `Get-Process python`

## 💡 Советы

- Всегда используй `make dev` вместо ручного запуска
- Если бот не отвечает - проверь webhook URL в логах
- Для продакшена на Railway порты настраиваются автоматически
- Локально Baliforum работает с dummy токеном Telegram
