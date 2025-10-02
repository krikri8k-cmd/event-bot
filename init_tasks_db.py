#!/usr/bin/env python3
"""
Скрипт для инициализации базы данных с заданиями
"""

import logging
import os

from dotenv import load_dotenv

from database import Task, create_all, get_session, init_engine

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv("app.local.env")

# Инициализируем базу данных
init_engine(os.getenv("DATABASE_URL"))


def init_tasks_database():
    """Инициализирует базу данных с заданиями"""
    try:
        # Создаем все таблицы
        create_all()
        logger.info("Таблицы созданы успешно")

        # Проверяем, есть ли уже задания
        with get_session() as session:
            existing_tasks = session.query(Task).count()

            if existing_tasks > 0:
                logger.info(f"В базе уже есть {existing_tasks} заданий")
                return

            # Вставляем задания для категории "Тело" (body)
            body_tasks = [
                Task(
                    category="body",
                    title="Йога на пляже",
                    description="Попробуйте йогу на пляже утром или вечером. Отличный способ начать день с энергией!",
                    location_url="https://maps.google.com/maps?q=Kuta+Beach+Bali",
                    order_index=1,
                ),
                Task(
                    category="body",
                    title="Пробежка по набережной",
                    description="Утренняя или вечерняя пробежка вдоль океана. Свежий воздух и красивые виды!",
                    location_url="https://maps.google.com/maps?q=Sanur+Beach+Walk",
                    order_index=2,
                ),
                Task(
                    category="body",
                    title="Утренняя растяжка",
                    description="Начните день с легкой растяжки. Найдите тихое место и потянитесь 15-20 минут.",
                    location_url=None,
                    order_index=3,
                ),
                Task(
                    category="body",
                    title="Плавание в океане",
                    description="Поплавайте в океане. Отличная кардио-нагрузка и закаливание!",
                    location_url="https://maps.google.com/maps?q=Seminyak+Beach",
                    order_index=4,
                ),
                Task(
                    category="body",
                    title="Велосипедная прогулка",
                    description="Прокатитесь на велосипеде по окрестностям. Исследуйте новые места!",
                    location_url="https://maps.google.com/maps?q=Ubud+Bike+Tour",
                    order_index=5,
                ),
                Task(
                    category="body",
                    title="Тренировка на свежем воздухе",
                    description="Сделайте комплекс упражнений на природе. Отжимания, приседания, планка.",
                    location_url=None,
                    order_index=6,
                ),
                Task(
                    category="body",
                    title="Пешая прогулка по рисовым террасам",
                    description="Прогуляйтесь по рисовым террасам. Красивые виды и легкая физическая активность.",
                    location_url="https://maps.google.com/maps?q=Tegallalang+Rice+Terraces",
                    order_index=7,
                ),
                Task(
                    category="body",
                    title="Серфинг для начинающих",
                    description="Попробуйте серфинг! Начните с уроков на спокойной воде.",
                    location_url="https://maps.google.com/maps?q=Canggu+Beach+Surf",
                    order_index=8,
                ),
                Task(
                    category="body",
                    title="Йога в джунглях",
                    description="Занятие йогой в окружении природы. Найдите спокойное место среди деревьев.",
                    location_url="https://maps.google.com/maps?q=Ubud+Yoga+Center",
                    order_index=9,
                ),
                Task(
                    category="body",
                    title="Плавание в водопаде",
                    description="Поплавайте в природном водопаде. Освежающе и полезно для здоровья!",
                    location_url="https://maps.google.com/maps?q=Tegenungan+Waterfall",
                    order_index=10,
                ),
                Task(
                    category="body",
                    title="Утренняя зарядка на пляже",
                    description="Сделайте зарядку на пляже на рассвете. Встретьте солнце с энергией!",
                    location_url="https://maps.google.com/maps?q=Jimbaran+Beach",
                    order_index=11,
                ),
                Task(
                    category="body",
                    title="Пеший поход к вулкану",
                    description="Совершите поход к вулкану. Физическая нагрузка и невероятные виды!",
                    location_url="https://maps.google.com/maps?q=Mount+Batur",
                    order_index=12,
                ),
                Task(
                    category="body",
                    title="Танцы на пляже",
                    description="Потанцуйте на пляже под закат. Отличная кардио-тренировка!",
                    location_url="https://maps.google.com/maps?q=Legian+Beach",
                    order_index=13,
                ),
                Task(
                    category="body",
                    title="Стретчинг в парке",
                    description="Потянитесь в городском парке. Найдите тихое место и расслабьтесь.",
                    location_url="https://maps.google.com/maps?q=Sanur+Beach+Park",
                    order_index=14,
                ),
                Task(
                    category="body",
                    title="Плавание с маской",
                    description="Поплавайте с маской и трубкой. Исследуйте подводный мир!",
                    location_url="https://maps.google.com/maps?q=Nusa+Dua+Beach",
                    order_index=15,
                ),
            ]

            # Вставляем задания для категории "Дух" (spirit)
            spirit_tasks = [
                Task(
                    category="spirit",
                    title="Медитация на рассвете",
                    description="Проведите 20 минут в медитации на рассвете. "
                    "Найдите тихое место и сосредоточьтесь на дыхании.",
                    location_url="https://maps.google.com/maps?q=Sanur+Beach+Sunrise",
                    order_index=1,
                ),
                Task(
                    category="spirit",
                    title="Посещение храма",
                    description="Посетите местный храм. Познакомьтесь с культурой и традициями Бали.",
                    location_url="https://maps.google.com/maps?q=Besakih+Temple",
                    order_index=2,
                ),
                Task(
                    category="spirit",
                    title="Прогулка по священному лесу",
                    description="Прогуляйтесь по священному лесу обезьян. Погрузитесь в атмосферу древности.",
                    location_url="https://maps.google.com/maps?q=Sacred+Monkey+Forest",
                    order_index=3,
                ),
                Task(
                    category="spirit",
                    title="Медитация у водопада",
                    description="Помедитируйте у водопада. Звуки воды помогут расслабиться и очистить разум.",
                    location_url="https://maps.google.com/maps?q=Tibumana+Waterfall",
                    order_index=4,
                ),
                Task(
                    category="spirit",
                    title="Церемония очищения",
                    description="Примите участие в церемонии очищения. Познайте духовные практики Бали.",
                    location_url="https://maps.google.com/maps?q=Tirta+Empul+Temple",
                    order_index=5,
                ),
                Task(
                    category="spirit",
                    title="Созерцание заката",
                    description="Проведите время в созерцании заката. Размышляйте о прошедшем дне.",
                    location_url="https://maps.google.com/maps?q=Uluwatu+Temple+Sunset",
                    order_index=6,
                ),
                Task(
                    category="spirit",
                    title="Прогулка по рисовым полям",
                    description="Медленно прогуляйтесь по рисовым полям. Наблюдайте за природой и размышляйте.",
                    location_url="https://maps.google.com/maps?q=Jatiluwih+Rice+Terraces",
                    order_index=7,
                ),
                Task(
                    category="spirit",
                    title="Медитация в пещере",
                    description="Помедитируйте в пещере. Тишина и полумрак помогут углубиться в себя.",
                    location_url="https://maps.google.com/maps?q=Goa+Gajah+Cave",
                    order_index=8,
                ),
                Task(
                    category="spirit",
                    title="Посещение духовного центра",
                    description="Посетите духовный центр или ашрам. Познакомьтесь с практиками саморазвития.",
                    location_url="https://maps.google.com/maps?q=Pyramids+of+Chi",
                    order_index=9,
                ),
                Task(
                    category="spirit",
                    title="Прогулка по ботаническому саду",
                    description="Погуляйте по ботаническому саду. Наблюдайте за разнообразием растений.",
                    location_url="https://maps.google.com/maps?q=Bali+Botanical+Garden",
                    order_index=10,
                ),
                Task(
                    category="spirit",
                    title="Медитация на вершине холма",
                    description="Поднимитесь на холм и помедитируйте. Вид сверху поможет обрести перспективу.",
                    location_url="https://maps.google.com/maps?q=Campuhan+Ridge+Walk",
                    order_index=11,
                ),
                Task(
                    category="spirit",
                    title="Посещение галереи искусства",
                    description="Посетите галерею местного искусства. Погрузитесь в творческую атмосферу.",
                    location_url="https://maps.google.com/maps?q=ARMA+Museum",
                    order_index=12,
                ),
                Task(
                    category="spirit",
                    title="Прогулка по саду специй",
                    description="Погуляйте по саду специй. Изучите ароматы и их влияние на настроение.",
                    location_url="https://maps.google.com/maps?q=Bali+Spice+Garden",
                    order_index=13,
                ),
                Task(
                    category="spirit",
                    title="Медитация у озера",
                    description="Помедитируйте у спокойного озера. Отражение в воде поможет найти внутренний покой.",
                    location_url="https://maps.google.com/maps?q=Lake+Batur",
                    order_index=14,
                ),
                Task(
                    category="spirit",
                    title="Посещение центра ремесел",
                    description="Посетите центр традиционных ремесел. Познайте мастерство и терпение мастеров.",
                    location_url="https://maps.google.com/maps?q=Ubud+Art+Market",
                    order_index=15,
                ),
            ]

            # Добавляем все задания в базу
            all_tasks = body_tasks + spirit_tasks
            session.add_all(all_tasks)
            session.commit()

            logger.info(f"Добавлено {len(all_tasks)} заданий:")
            logger.info(f"- Тело: {len(body_tasks)} заданий")
            logger.info(f"- Дух: {len(spirit_tasks)} заданий")

    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise


if __name__ == "__main__":
    init_tasks_database()
    logger.info("Инициализация базы данных завершена!")
