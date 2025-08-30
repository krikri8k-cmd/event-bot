"""
Модуль для инжеста событий в базу данных
"""

from sqlalchemy import Engine, text

from event_apis import RawEvent, fingerprint


def upsert_events(events: list[RawEvent], engine: Engine) -> int:
    """
    Вставляет события в базу данных с дедупликацией.

    Args:
        events: Список событий для вставки
        engine: SQLAlchemy engine

    Returns:
        Количество вставленных событий
    """
    if not events:
        return 0

    inserted_count = 0

    try:
        with engine.begin() as conn:
            for event in events:
                try:
                    # Создаём уникальный идентификатор
                    unique_id = fingerprint(event)

                    # Вставляем событие с ON CONFLICT DO UPDATE
                    conn.execute(
                        text("""
                            INSERT INTO events (
                                title, lat, lng, starts_at, source, external_id, url
                            ) VALUES (
                                :title, :lat, :lng, :starts_at, :source, :external_id, :url
                            )
                            ON CONFLICT (source, external_id) DO UPDATE
                            SET title = EXCLUDED.title,
                                url = EXCLUDED.url,
                                lat = EXCLUDED.lat,
                                lng = EXCLUDED.lng,
                                starts_at = EXCLUDED.starts_at,
                                updated_at = NOW()
                        """),
                        {
                            "title": event.title,
                            "lat": event.lat,
                            "lng": event.lng,
                            "starts_at": event.starts_at,
                            "source": event.source,
                            "external_id": event.external_id or unique_id,
                            "url": event.url,
                        },
                    )

                    # Считаем все изменения (вставки + обновления)
                    inserted_count += 1

                except Exception as e:
                    print(f"Ошибка вставки события '{event.title}': {e}")
                    continue

        print(f"✅ Вставлено {inserted_count} новых событий")
        return inserted_count

    except Exception as e:
        print(f"❌ Ошибка upsert_events: {e}")
        return 0
