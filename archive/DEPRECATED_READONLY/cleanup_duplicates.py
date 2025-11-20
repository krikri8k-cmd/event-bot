#!/usr/bin/env python3
"""
Очистка дубликатов в таблице events перед созданием уникального индекса
"""

import os

from sqlalchemy import text

from database import get_session, init_engine


def main():
    # Инициализируем подключение
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:password@host:port/database?sslmode=require",
    )
    init_engine(database_url)

    with get_session() as session:
        # 1. Найдем дубликаты по (source, external_id)
        print("🔍 Ищем дубликаты по (source, external_id)...")
        result = session.execute(
            text("""
            SELECT source, external_id, COUNT(*) as count
            FROM events
            WHERE source = 'baliforum'
            GROUP BY source, external_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """)
        )

        duplicates = result.fetchall()
        print(f"Найдено {len(duplicates)} групп дубликатов:")
        for row in duplicates:
            print(f"  {row[0]}|{row[1]}: {row[2]} записей")

        if not duplicates:
            print("✅ Дубликатов не найдено!")
            return

        # 2. Удаляем дубликаты, оставляя только самую новую запись
        print("\n🧹 Удаляем дубликаты...")
        result = session.execute(
            text("""
            DELETE FROM events
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY source, external_id
                               ORDER BY created_at DESC, id DESC
                           ) as rn
                    FROM events
                    WHERE source = 'baliforum'
                ) t
                WHERE rn > 1
            )
        """)
        )

        deleted_count = result.rowcount
        session.commit()
        print(f"✅ Удалено {deleted_count} дубликатов")

        # 3. Проверяем результат
        result = session.execute(
            text("""
            SELECT source, external_id, COUNT(*) as count
            FROM events
            WHERE source = 'baliforum'
            GROUP BY source, external_id
            HAVING COUNT(*) > 1
        """)
        )

        remaining_duplicates = result.fetchall()
        if remaining_duplicates:
            print(f"⚠️ Остались дубликаты: {len(remaining_duplicates)}")
        else:
            print("✅ Все дубликаты удалены!")


if __name__ == "__main__":
    main()
