#!/usr/bin/env python3
"""
Структурированное логирование для ingest и search операций
"""

import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class StructuredLogger:
    """Логгер для структурированных JSON логов"""

    @staticmethod
    def log_ingest(
        source: str,
        region: str,
        parsed: int,
        skipped_no_time: int = 0,
        skipped_no_coords: int = 0,
        upserted: int = 0,
        updated: int = 0,
        window_start: str | None = None,
        window_end: str | None = None,
        duration_ms: float | None = None,
        errors: int = 0,
        **kwargs,
    ) -> None:
        """
        Логирует результат ingest операции

        Args:
            source: Источник данных (baliforum, kudago, ai)
            region: Регион (bali, msk, spb)
            parsed: Количество распарсенных событий
            skipped_no_time: Количество пропущенных событий без времени
            skipped_no_coords: Количество пропущенных событий без координат
            upserted: Количество вставленных событий
            updated: Количество обновленных событий
            window_start: Начало временного окна (ISO format)
            window_end: Конец временного окна (ISO format)
            duration_ms: Время выполнения в миллисекундах
            errors: Количество ошибок
            **kwargs: Дополнительные поля
        """
        log_data = {
            "type": "ingest",
            "timestamp": datetime.now(datetime.UTC).isoformat() + "Z",
            "source": source,
            "region": region,
            "parsed": parsed,
            "skipped_no_time": skipped_no_time,
            "skipped_no_coords": skipped_no_coords,
            "upserted": upserted,
            "updated": updated,
            "errors": errors,
        }

        if window_start:
            log_data["window_start"] = window_start
        if window_end:
            log_data["window_end"] = window_end
        if duration_ms is not None:
            log_data["duration_ms"] = round(duration_ms, 2)

        # Добавляем дополнительные поля
        log_data.update(kwargs)

        logger.info(json.dumps(log_data, ensure_ascii=False))

    @staticmethod
    def log_search(
        region: str,
        radius_km: float,
        user_lat: float,
        user_lng: float,
        found_total: int,
        found_user: int = 0,
        found_parser: int = 0,
        message_id: str | None = None,
        empty_reason: str | None = None,
        duration_ms: float | None = None,
        **kwargs,
    ) -> None:
        """
        Логирует результат search операции

        Args:
            region: Регион поиска (bali, msk, spb)
            radius_km: Радиус поиска в км
            user_lat: Широта пользователя
            user_lng: Долгота пользователя
            found_total: Общее количество найденных событий
            found_user: Количество пользовательских событий
            found_parser: Количество событий от парсеров
            message_id: ID сообщения Telegram
            empty_reason: Причина пустого результата
            duration_ms: Время выполнения в миллисекундах
            **kwargs: Дополнительные поля
        """
        log_data = {
            "type": "search",
            "timestamp": datetime.now(datetime.UTC).isoformat() + "Z",
            "region": region,
            "radius_km": radius_km,
            "user_lat": user_lat,
            "user_lng": user_lng,
            "found_total": found_total,
            "found_user": found_user,
            "found_parser": found_parser,
        }

        if message_id:
            log_data["message_id"] = message_id
        if empty_reason:
            log_data["empty_reason"] = empty_reason
        if duration_ms is not None:
            log_data["duration_ms"] = round(duration_ms, 2)

        # Добавляем дополнительные поля
        log_data.update(kwargs)

        logger.info(json.dumps(log_data, ensure_ascii=False))


class TimingContext:
    """Контекстный менеджер для измерения времени выполнения"""

    def __init__(self, operation: str, **kwargs):
        self.operation = operation
        self.kwargs = kwargs
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            self.kwargs["duration_ms"] = duration_ms

            if self.operation == "ingest":
                StructuredLogger.log_ingest(**self.kwargs)
            elif self.operation == "search":
                StructuredLogger.log_search(**self.kwargs)
