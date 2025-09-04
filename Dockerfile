# Dockerfile для Telegram бота
FROM python:3.12-slim

# Настройки Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Рабочая директория
WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Обновим pip и установим зависимости
COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip wheel setuptools \
 && pip install -r requirements.txt

# Копируем проект
COPY . .

# Запускаем Telegram бота напрямую
CMD ["python", "bot_enhanced_v3.py"]
