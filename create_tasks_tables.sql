-- Создание таблиц для системы заданий "Цели на районе"

-- Таблица заданий (15 заданий в каждой категории)
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    category VARCHAR(20) NOT NULL, -- 'body' или 'spirit'
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    location_url VARCHAR(500), -- может быть NULL
    order_index INTEGER NOT NULL, -- порядок показа (1-15)
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица принятых заданий пользователями
CREATE TABLE IF NOT EXISTS user_tasks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    task_id INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'completed', 'cancelled', 'expired'
    feedback TEXT, -- фидбек пользователя
    accepted_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL, -- accepted_at + 48 часов
    completed_at TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Индексы для оптимизации
CREATE INDEX IF NOT EXISTS idx_tasks_category_order ON tasks(category, order_index);
CREATE INDEX IF NOT EXISTS idx_user_tasks_user_status ON user_tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_tasks_expires ON user_tasks(expires_at);

-- Вставляем тестовые задания для категории "Тело" (body)
INSERT INTO tasks (category, title, description, location_url, order_index) VALUES
('body', 'Йога на пляже', 'Попробуйте йогу на пляже утром или вечером. Отличный способ начать день с энергией!', 'https://maps.google.com/maps?q=Kuta+Beach+Bali', 1),
('body', 'Пробежка по набережной', 'Утренняя или вечерняя пробежка вдоль океана. Свежий воздух и красивые виды!', 'https://maps.google.com/maps?q=Sanur+Beach+Walk', 2),
('body', 'Утренняя растяжка', 'Начните день с легкой растяжки. Найдите тихое место и потянитесь 15-20 минут.', NULL, 3),
('body', 'Плавание в океане', 'Поплавайте в океане. Отличная кардио-нагрузка и закаливание!', 'https://maps.google.com/maps?q=Seminyak+Beach', 4),
('body', 'Велосипедная прогулка', 'Прокатитесь на велосипеде по окрестностям. Исследуйте новые места!', 'https://maps.google.com/maps?q=Ubud+Bike+Tour', 5),
('body', 'Тренировка на свежем воздухе', 'Сделайте комплекс упражнений на природе. Отжимания, приседания, планка.', NULL, 6),
('body', 'Пешая прогулка по рисовым террасам', 'Прогуляйтесь по рисовым террасам. Красивые виды и легкая физическая активность.', 'https://maps.google.com/maps?q=Tegallalang+Rice+Terraces', 7),
('body', 'Серфинг для начинающих', 'Попробуйте серфинг! Начните с уроков на спокойной воде.', 'https://maps.google.com/maps?q=Canggu+Beach+Surf', 8),
('body', 'Йога в джунглях', 'Занятие йогой в окружении природы. Найдите спокойное место среди деревьев.', 'https://maps.google.com/maps?q=Ubud+Yoga+Center', 9),
('body', 'Плавание в водопаде', 'Поплавайте в природном водопаде. Освежающе и полезно для здоровья!', 'https://maps.google.com/maps?q=Tegenungan+Waterfall', 10),
('body', 'Утренняя зарядка на пляже', 'Сделайте зарядку на пляже на рассвете. Встретьте солнце с энергией!', 'https://maps.google.com/maps?q=Jimbaran+Beach', 11),
('body', 'Пеший поход к вулкану', 'Совершите поход к вулкану. Физическая нагрузка и невероятные виды!', 'https://maps.google.com/maps?q=Mount+Batur', 12),
('body', 'Танцы на пляже', 'Потанцуйте на пляже под закат. Отличная кардио-тренировка!', 'https://maps.google.com/maps?q=Legian+Beach', 13),
('body', 'Стретчинг в парке', 'Потянитесь в городском парке. Найдите тихое место и расслабьтесь.', 'https://maps.google.com/maps?q=Sanur+Beach+Park', 14),
('body', 'Плавание с маской', 'Поплавайте с маской и трубкой. Исследуйте подводный мир!', 'https://maps.google.com/maps?q=Nusa+Dua+Beach', 15);

-- Вставляем тестовые задания для категории "Дух" (spirit)
INSERT INTO tasks (category, title, description, location_url, order_index) VALUES
('spirit', 'Медитация на рассвете', 'Проведите 20 минут в медитации на рассвете. Найдите тихое место и сосредоточьтесь на дыхании.', 'https://maps.google.com/maps?q=Sanur+Beach+Sunrise', 1),
('spirit', 'Посещение храма', 'Посетите местный храм. Познакомьтесь с культурой и традициями Бали.', 'https://maps.google.com/maps?q=Besakih+Temple', 2),
('spirit', 'Прогулка по священному лесу', 'Прогуляйтесь по священному лесу обезьян. Погрузитесь в атмосферу древности.', 'https://maps.google.com/maps?q=Sacred+Monkey+Forest', 3),
('spirit', 'Медитация у водопада', 'Помедитируйте у водопада. Звуки воды помогут расслабиться и очистить разум.', 'https://maps.google.com/maps?q=Tibumana+Waterfall', 4),
('spirit', 'Церемония очищения', 'Примите участие в церемонии очищения. Познайте духовные практики Бали.', 'https://maps.google.com/maps?q=Tirta+Empul+Temple', 5),
('spirit', 'Созерцание заката', 'Проведите время в созерцании заката. Размышляйте о прошедшем дне.', 'https://maps.google.com/maps?q=Uluwatu+Temple+Sunset', 6),
('spirit', 'Прогулка по рисовым полям', 'Медленно прогуляйтесь по рисовым полям. Наблюдайте за природой и размышляйте.', 'https://maps.google.com/maps?q=Jatiluwih+Rice+Terraces', 7),
('spirit', 'Медитация в пещере', 'Помедитируйте в пещере. Тишина и полумрак помогут углубиться в себя.', 'https://maps.google.com/maps?q=Goa+Gajah+Cave', 8),
('spirit', 'Посещение духовного центра', 'Посетите духовный центр или ашрам. Познакомьтесь с практиками саморазвития.', 'https://maps.google.com/maps?q=Pyramids+of+Chi', 9),
('spirit', 'Прогулка по ботаническому саду', 'Погуляйте по ботаническому саду. Наблюдайте за разнообразием растений.', 'https://maps.google.com/maps?q=Bali+Botanical+Garden', 10),
('spirit', 'Медитация на вершине холма', 'Поднимитесь на холм и помедитируйте. Вид сверху поможет обрести перспективу.', 'https://maps.google.com/maps?q=Campuhan+Ridge+Walk', 11),
('spirit', 'Посещение галереи искусства', 'Посетите галерею местного искусства. Погрузитесь в творческую атмосферу.', 'https://maps.google.com/maps?q=ARMA+Museum', 12),
('spirit', 'Прогулка по саду специй', 'Погуляйте по саду специй. Изучите ароматы и их влияние на настроение.', 'https://maps.google.com/maps?q=Bali+Spice+Garden', 13),
('spirit', 'Медитация у озера', 'Помедитируйте у спокойного озера. Отражение в воде поможет найти внутренний покой.', 'https://maps.google.com/maps?q=Lake+Batur', 14),
('spirit', 'Посещение центра ремесел', 'Посетите центр традиционных ремесел. Познайте мастерство и терпение мастеров.', 'https://maps.google.com/maps?q=Ubud+Art+Market', 15);
