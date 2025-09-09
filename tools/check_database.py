#!/usr/bin/env python3
"""
Проверка базы данных проекта
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_settings
from database import Event, Moment, User, get_session, init_engine


def check_database():
    """Проверяет состояние базы данных"""

    print("🗄️ Проверка базы данных")
    print("=" * 50)

    try:
        # Инициализация базы данных
        settings = load_settings()
        init_engine(settings.database_url)

        with get_session() as session:
            # Проверяем подключение
            print("✅ Подключение к базе данных успешно")
            print()

            # Общая статистика
            print("📊 Общая статистика:")
            total_events = session.query(Event).count()
            total_moments = session.query(Moment).count()
            total_users = session.query(User).count()

            print(f"  • Событий: {total_events}")
            print(f"  • Моментов: {total_moments}")
            print(f"  • Пользователей: {total_users}")
            print()

            # События за последние 24 часа
            now = datetime.now(UTC)
            yesterday = now - timedelta(hours=24)

            print("📅 События за последние 24 часа:")
            recent_events = session.query(Event).filter(Event.created_at_utc >= yesterday).count()
            print(f"  • Всего: {recent_events}")

            # По источникам
            source_stats = (
                session.query(
                    Event.source,
                    session.query(Event)
                    .filter(Event.created_at_utc >= yesterday, Event.source == Event.source)
                    .count(),
                )
                .filter(Event.created_at_utc >= yesterday, Event.source.isnot(None))
                .group_by(Event.source)
                .all()
            )

            if source_stats:
                print("  • По источникам:")
                for source, count in source_stats:
                    print(f"    - {source}: {count}")
            else:
                print("  • Нет событий с источниками")

            # Пользовательские события
            user_events = (
                session.query(Event)
                .filter(
                    Event.created_at_utc >= yesterday,
                    Event.source.is_(None),
                    Event.organizer_id.isnot(None),
                )
                .count()
            )
            print(f"  • Пользовательские: {user_events}")

            # AI события
            ai_events = (
                session.query(Event)
                .filter(Event.created_at_utc >= yesterday, Event.is_generated_by_ai is True)
                .count()
            )
            print(f"  • AI-сгенерированные: {ai_events}")
            print()

            # Проверяем дубликаты
            print("🔍 Проверка дубликатов:")
            duplicates = (
                session.query(
                    Event.title,
                    Event.starts_at,
                    Event.location_name,
                    session.query(Event)
                    .filter(
                        Event.title == Event.title,
                        Event.starts_at == Event.starts_at,
                        Event.location_name == Event.location_name,
                    )
                    .count()
                    .label("count"),
                )
                .group_by(Event.title, Event.starts_at, Event.location_name)
                .having(
                    session.query(Event)
                    .filter(
                        Event.title == Event.title,
                        Event.starts_at == Event.starts_at,
                        Event.location_name == Event.location_name,
                    )
                    .count()
                    > 1
                )
                .all()
            )

            if duplicates:
                print(f"  ❌ Найдено {len(duplicates)} групп дубликатов:")
                for title, starts_at, location, count in duplicates[:5]:
                    print(f"    - {title} ({starts_at}) в {location}: {count} раз")
                if len(duplicates) > 5:
                    print(f"    ... и еще {len(duplicates) - 5}")
            else:
                print("  ✅ Дубликатов не найдено")
            print()

            # Статистика моментов
            print("⚡ Статистика моментов:")
            active_moments = (
                session.query(Moment)
                .filter(Moment.is_active is True, Moment.expires_at > now)
                .count()
            )

            expired_moments = (
                session.query(Moment)
                .filter(Moment.is_active is True, Moment.expires_at <= now)
                .count()
            )

            print(f"  • Активных: {active_moments}")
            print(f"  • Истекших (требуют очистки): {expired_moments}")
            print(f"  • Всего: {total_moments}")
            print()

            # Проверяем события без координат
            print("📍 События без координат:")
            events_without_coords = (
                session.query(Event).filter(Event.lat.is_(None) | Event.lng.is_(None)).count()
            )
            print(f"  • Без координат: {events_without_coords}")

            if events_without_coords > 0:
                print("  ⚠️ Рекомендуется добавить геокодирование")
            print()

            # Проверяем события без ссылок
            print("🔗 События без ссылок:")
            events_without_url = (
                session.query(Event).filter(Event.url.is_(None) | (Event.url == "")).count()
            )
            print(f"  • Без ссылок: {events_without_url}")

            if events_without_url > 0:
                print("  ⚠️ Рекомендуется добавить ссылки на источники")
            print()

            # Проверяем индексы
            print("🔍 Проверка индексов:")
            try:
                # Проверяем основные индексы
                indexes_to_check = [
                    "idx_events_coords",
                    "idx_events_starts_at",
                    "idx_events_source",
                    "idx_moments_active_exp",
                ]

                for index_name in indexes_to_check:
                    try:
                        result = session.execute(
                            f"SELECT 1 FROM pg_indexes WHERE indexname = '{index_name}'"
                        ).fetchone()
                        if result:
                            print(f"  ✅ {index_name}")
                        else:
                            print(f"  ❌ {index_name} - отсутствует")
                    except Exception:
                        print(f"  ⚠️ {index_name} - не удалось проверить")

            except Exception as e:
                print(f"  ⚠️ Не удалось проверить индексы: {e}")

            print()
            print("✅ Проверка базы данных завершена")
            return True

    except Exception as e:
        print(f"❌ Ошибка при проверке базы данных: {e}")
        return False


if __name__ == "__main__":
    success = check_database()
    sys.exit(0 if success else 1)
