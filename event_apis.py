#!/usr/bin/env python3
"""
Модуль для работы с внешними API событий
"""

import datetime as dt
import hashlib
from dataclasses import dataclass


@dataclass
class RawEvent:
    """Сырое событие из внешнего API"""

    title: str
    lat: float
    lng: float
    starts_at: dt.datetime | None
    source: str
    external_id: str | None = None
    url: str | None = None
    description: str | None = None

    def fingerprint(self) -> str:
        """
        Создаёт уникальный отпечаток события для дедупликации.
        Используется если external_id не предоставлен.
        """
        # Создаём строку из ключевых полей
        key_fields = [
            self.title.strip().lower(),
            f"{self.lat:.6f}",
            f"{self.lng:.6f}",
            self.source,
        ]

        # Добавляем время если есть
        if self.starts_at:
            key_fields.append(self.starts_at.isoformat())

        # Создаём хеш
        content = "|".join(key_fields)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def fingerprint(event: RawEvent) -> str:
    """
    Возвращает уникальный идентификатор события.
    Приоритет: external_id > fingerprint() > None
    """
    if event.external_id:
        return f"{event.source}:{event.external_id}"
    return f"{event.source}:{event.fingerprint()}"
