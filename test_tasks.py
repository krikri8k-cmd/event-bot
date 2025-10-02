#!/usr/bin/env python3
"""
Простой тест системы заданий
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv("app.local.env")


def test_tasks():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    # Тестируем получение заданий для категории 'body' (день 1)
    cur.execute("""
        SELECT id, title, description, location_url, order_index
        FROM tasks
        WHERE category = 'body' AND order_index BETWEEN 1 AND 3
        ORDER BY order_index
    """)

    body_tasks = cur.fetchall()
    print(f"Body tasks (day 1): {len(body_tasks)}")
    for task in body_tasks:
        print(f"  - {task[1]} (order: {task[4]})")

    # Тестируем получение заданий для категории 'spirit' (день 1)
    cur.execute("""
        SELECT id, title, description, location_url, order_index
        FROM tasks
        WHERE category = 'spirit' AND order_index BETWEEN 1 AND 3
        ORDER BY order_index
    """)

    spirit_tasks = cur.fetchall()
    print(f"Spirit tasks (day 1): {len(spirit_tasks)}")
    for task in spirit_tasks:
        print(f"  - {task[1]} (order: {task[4]})")

    # Тестируем получение заданий для дня 2
    cur.execute("""
        SELECT id, title, description, location_url, order_index
        FROM tasks
        WHERE category = 'body' AND order_index BETWEEN 4 AND 6
        ORDER BY order_index
    """)

    body_tasks_day2 = cur.fetchall()
    print(f"Body tasks (day 2): {len(body_tasks_day2)}")
    for task in body_tasks_day2:
        print(f"  - {task[1]} (order: {task[4]})")

    cur.close()
    conn.close()


if __name__ == "__main__":
    test_tasks()
