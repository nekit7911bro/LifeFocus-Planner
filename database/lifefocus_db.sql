
-- ============================================
-- LifeFocus Planner
-- PostgreSQL: lifefocus_db
-- Schema: public
-- ============================================

BEGIN;

-- 1. Таблица пользователей
CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

-- 2. Таблица категорий
CREATE TABLE IF NOT EXISTS public.categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80) UNIQUE NOT NULL
);

-- 3. Таблица задач
CREATE TABLE IF NOT EXISTS public.tasks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL
        REFERENCES public.users(id) ON DELETE CASCADE,
    category_id INTEGER
        REFERENCES public.categories(id) ON DELETE SET NULL,
    title VARCHAR(150) NOT NULL,
    description TEXT DEFAULT '',
    due_date DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'Новая',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Добавление основных категорий
INSERT INTO public.categories (name)
VALUES
    ('Учёба'),
    ('Спорт'),
    ('Работа'),
    ('Личное'),
    ('Другое')
ON CONFLICT (name) DO NOTHING;

-- 5. Перенос задач из старой категории
-- «Личная жизнь» в «Личное»
UPDATE public.tasks AS t
SET category_id = personal.id
FROM public.categories AS old_category,
     public.categories AS personal
WHERE t.category_id = old_category.id
  AND old_category.name = 'Личная жизнь'
  AND personal.name = 'Личное';

-- 6. Удаление старой категории
DELETE FROM public.categories
WHERE name = 'Личная жизнь';

-- 7. Индекс для поиска задач пользователя
CREATE INDEX IF NOT EXISTS idx_tasks_user_id
ON public.tasks(user_id);

COMMIT;

-- ============================================
-- Конец скрипта
-- ============================================
