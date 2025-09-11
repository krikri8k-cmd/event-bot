"""
Модуль для инжеста событий в базу данных
"""

from sqlalchemy import Engine, text

from event_apis import RawEvent, fingerprint


def upsert_events(events: list[RawEvent], engine: Engine) -> int:
    """
    Вставляет события в базу данных с идемпотентным upsert.

    Args:
        events: Список событий для вставки
        engine: SQLAlchemy engine

    Returns:
        Количество обработанных событий
    """
    if not events:
        return 0

    inserted_count = 0
    updated_count = 0
    error_count = 0

    try:
        for event in events:
            try:
                # Создаём уникальный идентификатор как fallback
                unique_id = fingerprint(event)
                external_id = event.external_id or unique_id

                # Идемпотентный upsert в отдельной транзакции
                with engine.begin() as conn:
                    result = conn.execute(
                        text("""
                            INSERT INTO events (
                                title, lat, lng, starts_at, source, external_id, url,
                                current_participants, max_participants, status, is_generated_by_ai,
                                created_at, updated_at
                            ) VALUES (
                                :title, :lat, :lng, :starts_at, :source, :external_id, :url,
                                0, 0, 'active', false,
                                now(), now()
                            )
                            ON CONFLICT (source, external_id)
                            DO UPDATE SET
                                title = EXCLUDED.title,
                                url = EXCLUDED.url,
                                starts_at = EXCLUDED.starts_at,
                                lat = EXCLUDED.lat,
                                lng = EXCLUDED.lng,
                                updated_at = now()
                            RETURNING (xmax = 0) AS inserted
                        """),
                        {
                            "title": event.title,
                            "lat": event.lat,
                            "lng": event.lng,
                            "starts_at": event.starts_at,
                            "source": event.source,
                            "external_id": external_id,
                            "url": event.url,
                        },
                    )

                    # Проверяем, была ли это вставка или обновление
                    row = result.fetchone()
                    if row and row[0]:  # inserted = True
                        inserted_count += 1
                    else:
                        updated_count += 1

            except Exception as e:
                print(f"Ошибка upsert события '{event.title}': {e}")
                error_count += 1
                continue

        print(f"✅ Upsert завершен: вставлено={inserted_count}, обновлено={updated_count}, ошибок={error_count}")
        return inserted_count + updated_count

    except Exception as e:
        print(f"❌ Ошибка upsert_events: {e}")
        return 0
