# Принудительная фиксация среды: Python 3.11 (Railway игнорирует runtime.txt)
FROM python:3.11-slim

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Права на запуск скрипта (если используется)
RUN chmod +x railway-bot-start.sh

# Запуск через uvicorn (порт из переменной окружения)
CMD ["sh", "-c", "uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
