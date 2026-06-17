# Принудительная фиксация среды: Python 3.11 (Railway игнорирует runtime.txt)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка Python зависимостей (retries — против обрывов PyPI на Railway build)
COPY requirements.txt .
RUN python -m pip install --upgrade pip wheel setuptools \
 && python -m pip install --retries 10 --timeout 120 requests==2.31.0 \
 && python -m pip install --retries 10 --timeout 120 -r requirements.txt

# Копирование кода
COPY . .

# Права на запуск скрипта (если используется)
RUN chmod +x railway-bot-start.sh

# START_COMMAND переопределяет запуск (например worker на отдельном Railway-сервисе)
CMD ["sh", "-c", "${START_COMMAND:-uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}}"]
