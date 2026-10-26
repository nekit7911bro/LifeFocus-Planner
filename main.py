
import os
import re
import calendar
from datetime import datetime, date
from functools import wraps
from urllib.parse import urlsplit

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash


# Настройки приложения
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "lifefocus-dev-key")

# Настройки PostgreSQL
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "lifefocus_db"
DB_USER = "postgres"
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

STATUSES = ("Новая", "В работе", "Выполнена")
MONTH_NAMES = (
    "Январь", "Февраль", "Март", "Апрель",
    "Май", "Июнь", "Июль", "Август",
    "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
)


# Подключение к базе данных
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor
    )


# Функции работы с PostgreSQL
def fetch_all(query, params=()):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    finally:
        connection.close()


def fetch_one(query, params=()):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()
    finally:
        connection.close()


def execute_query(query, params=()):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            affected_rows = cursor.rowcount
        connection.commit()
        return affected_rows
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# Создание таблиц при первом запуске
def initialize_database():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(80) UNIQUE NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    category_id INTEGER
                        REFERENCES categories(id) ON DELETE SET NULL,
                    title VARCHAR(150) NOT NULL,
                    description TEXT DEFAULT '',
                    due_date DATE,
                    status VARCHAR(30) NOT NULL DEFAULT 'Новая',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            for name in ("Учёба", "Работа", "Личное", "Другое"):
                cursor.execute("""
                    INSERT INTO categories (name)
                    VALUES (%s)
                    ON CONFLICT (name) DO NOTHING
                """, (name,))

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


# Общие данные HTML-шаблонов
@app.context_processor
def inject_template_data():
    return {
        "theme": session.get("theme", "light"),
        "statuses": STATUSES
    }


# Проверка авторизации
def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Для продолжения войдите в аккаунт.", "error")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


# Стартовая страница
@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("home"))
    return render_template("index.html")


# Переключение светлой и тёмной темы
@app.route("/theme", methods=["POST"])
def toggle_theme():
    session["theme"] = (
        "dark" if session.get("theme", "light") == "light"
        else "light"
    )

    destination = request.form.get("next", "")
    parsed = urlsplit(destination)

    # Проверяем безопасный внутренний адрес
    if (
        destination.startswith("/")
        and not destination.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
        and "\\" not in destination
    ):
        return redirect(destination)

    if session.get("user_id"):
        return redirect(url_for("home"))
    return redirect(url_for("index"))


# Регистрация нового пользователя
@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("home"))

    if request.method == "GET":
        return render_template("auth.html", mode="register")

    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not username or not email or not password:
        flash("Заполните все обязательные поля.", "error")
        return redirect(url_for("register"))

    if len(username) > 50:
        flash("Имя пользователя слишком длинное.", "error")
        return redirect(url_for("register"))

    if (
        len(email) > 100
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        flash("Введите корректную электронную почту.", "error")
        return redirect(url_for("register"))

    if len(password) < 8:
        flash("Пароль должен содержать минимум 8 символов.", "error")
        return redirect(url_for("register"))

    if password != confirm_password:
        flash("Пароли не совпадают.", "error")
        return redirect(url_for("register"))

    if fetch_one(
        "SELECT id FROM users WHERE username = %s OR email = %s",
        (username, email)
    ):
        flash("Логин или почта уже используются.", "error")
        return redirect(url_for("register"))

    try:
        execute_query("""
            INSERT INTO users (username, email, password_hash)
            VALUES (%s, %s, %s)
        """, (username, email, generate_password_hash(password)))
    except psycopg2.errors.UniqueViolation:
        flash("Логин или почта уже используются.", "error")
        return redirect(url_for("register"))

    flash("Регистрация прошла успешно. Теперь войдите.", "success")
    return redirect(url_for("login"))


# Вход пользователя в аккаунт
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))

    if request.method == "GET":
        return render_template("auth.html", mode="login")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    user = fetch_one("""
        SELECT id, username, password_hash
        FROM users
        WHERE username = %s
    """, (username,))

    if not user or not check_password_hash(
        user["password_hash"], password
    ):
        flash("Неверный логин или пароль.", "error")
        return redirect(url_for("login"))

    saved_theme = session.get("theme", "light")
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["theme"] = saved_theme

    # После входа показываем стартовый экран
    return redirect(url_for("home"))


# Выход из аккаунта
@app.route("/logout", methods=["POST"])
@login_required
def logout():
    saved_theme = session.get("theme", "light")
    session.clear()
    session["theme"] = saved_theme
    return redirect(url_for("index"))


# Список категорий
def get_categories():
    return fetch_all(
        "SELECT id, name FROM categories ORDER BY name"
    )


# Получение задачи текущего пользователя
def get_task(task_id):
    return fetch_one("""
        SELECT t.*, c.name AS category_name
        FROM tasks t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.id = %s AND t.user_id = %s
    """, (task_id, session["user_id"]))


# Проверка полей формы задачи
def read_task_form():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category_text = request.form.get("category_id", "").strip()
    date_text = request.form.get("due_date", "").strip()

    if not title:
        raise ValueError("Введите название задачи.")

    if len(title) > 150:
        raise ValueError("Название не должно превышать 150 символов.")

    if len(description) > 3000:
        raise ValueError("Описание слишком длинное.")

    due_date = None
    if date_text:
        try:
            due_date = date.fromisoformat(date_text)
        except ValueError:
            raise ValueError("Некорректная дата выполнения.")

    category_id = None
    if category_text:
        if not category_text.isdigit():
            raise ValueError("Некорректная категория.")

        category_id = int(category_text)

        if not fetch_one(
            "SELECT id FROM categories WHERE id = %s",
            (category_id,)
        ):
            raise ValueError("Выбранная категория не существует.")

    return title, description, due_date, category_id


# Статистика задач пользователя
def get_statistics():
    stats = fetch_one("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (
                WHERE status = 'Новая'
            ) AS new_count,
            COUNT(*) FILTER (
                WHERE status = 'В работе'
            ) AS active_count,
            COUNT(*) FILTER (
                WHERE status = 'Выполнена'
            ) AS done_count,
            COUNT(*) FILTER (
                WHERE due_date < CURRENT_DATE
                AND status <> 'Выполнена'
            ) AS overdue_count
        FROM tasks
        WHERE user_id = %s
    """, (session["user_id"],))

    stats["percent"] = (
        round(stats["done_count"] / stats["total"] * 100)
        if stats["total"] else 0
    )
    return stats


# Статистика по категориям
def get_category_statistics(user_id):
    return fetch_all("""
        SELECT
            COALESCE(c.name, 'Без категории') AS name,
            COUNT(*) AS total
        FROM tasks t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = %s
        GROUP BY c.id, c.name
        ORDER BY total DESC, name ASC
    """, (user_id,))


# Рабочее пространство пользователя
@app.route("/home")
@login_required
def home():
    user_id = session["user_id"]

    # Определяем открытый раздел
    view = request.args.get("view", "welcome")
    if view not in {"welcome", "tasks", "calendar", "stats"}:
        view = "welcome"

    # Параметры поиска и фильтрации
    search = request.args.get("q", "").strip()
    selected_status = request.args.get("status", "")
    selected_category = request.args.get("category", "")
    selected_sort = request.args.get("sort", "newest")

    # Получаем задачи пользователя
    query = """
        SELECT
            t.id, t.title, t.description, t.status, t.due_date,
            t.category_id, t.created_at,
            c.name AS category_name
        FROM tasks t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = %s
    """
    params = [user_id]

    # Поиск только по названию задачи
    if search:
        query += " AND t.title ILIKE %s"
        params.append("%" + search + "%")

    if selected_status in STATUSES:
        query += " AND t.status = %s"
        params.append(selected_status)

    if selected_category.isdigit():
        query += " AND t.category_id = %s"
        params.append(int(selected_category))

    
    # Сортировка списка задач
    sorting_options = {
        "newest": "t.created_at DESC, t.id DESC",
        "oldest": "t.created_at ASC, t.id ASC",
        "deadline": "t.due_date ASC NULLS LAST, t.id DESC",
        "title_asc": "LOWER(t.title) ASC, t.id DESC",
        "title_desc": "LOWER(t.title) DESC, t.id DESC"
    }

    query += " ORDER BY " + sorting_options.get(
        selected_sort, sorting_options["newest"]
    )

    tasks = fetch_all(query, params)

    
    # Выбираем месяц календаря
    today = date.today()
    month_text = request.args.get("month", "")

    try:
        shown_month = datetime.strptime(
            month_text, "%Y-%m"
        ).date().replace(day=1)
    except ValueError:
        shown_month = today.replace(day=1)

    # Выбираем дату календаря
    selected_text = request.args.get("day", "")
    try:
        selected_day = date.fromisoformat(selected_text)
        shown_month = selected_day.replace(day=1)
    except ValueError:
        selected_day = shown_month if month_text else today

    # Предыдущий и следующий месяцы
    if shown_month.month == 1:
        prev_month = date(shown_month.year - 1, 12, 1)
    else:
        prev_month = date(
            shown_month.year, shown_month.month - 1, 1
        )

    if shown_month.month == 12:
        next_month = date(shown_month.year + 1, 1, 1)
    else:
        next_month = date(
            shown_month.year, shown_month.month + 1, 1
        )

    month_title = (
        f"{MONTH_NAMES[shown_month.month - 1]} "
        f"{shown_month.year}"
    )

    # Даты с задачами в выбранном месяце
    month_tasks = fetch_all("""
        SELECT due_date, COUNT(*) AS total
        FROM tasks
        WHERE user_id = %s
          AND due_date >= %s
          AND due_date < %s
        GROUP BY due_date
    """, (user_id, shown_month, next_month))

    task_days = {
        task["due_date"].day: task["total"]
        for task in month_tasks
    }

    # Задачи выбранного дня
    day_tasks = fetch_all("""
        SELECT id, title, status, due_date
        FROM tasks
        WHERE user_id = %s AND due_date = %s
        ORDER BY created_at DESC
    """, (user_id, selected_day))

    # Сетка календаря с понедельника
    weeks = calendar.monthcalendar(
        shown_month.year, shown_month.month
    )
    while len(weeks) < 6:
        weeks.append([0] * 7)

    # Подготовка данных для статистики
    stats = get_statistics()
    category_stats = get_category_statistics(user_id)

    return render_template(
        "home.html",
        view=view,
        tasks=tasks,
        categories=get_categories(),
        stats=stats,
        category_stats=category_stats,
        search=search,
        selected_status=selected_status,
        selected_category=selected_category,
        selected_sort=selected_sort,
        today=today,
        shown_month=shown_month,
        selected_day=selected_day,
        month_title=month_title,
        prev_month=prev_month,
        next_month=next_month,
        weeks=weeks,
        task_days=task_days,
        day_tasks=day_tasks
    )


# Создание задачи
@app.route("/tasks/create", methods=["GET", "POST"])
@login_required
def create_task():
    if request.method == "GET":
        due_date = request.args.get("due_date", "")
        try:
            date.fromisoformat(due_date)
        except ValueError:
            due_date = ""

        return render_template(
            "task_creation.html",
            task=None,
            categories=get_categories(),
            default_due_date=due_date
        )

    try:
        title, description, due_date, category_id = read_task_form()
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("create_task"))

    execute_query("""
        INSERT INTO tasks (
            user_id, category_id, title, description, due_date, status
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        session["user_id"], category_id, title,
        description, due_date, "Новая"
    ))

    flash("Задача успешно создана.", "success")
    return redirect(url_for("home", view="tasks"))


# Редактирование задачи
@app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id):
    task = get_task(task_id)

    if task is None:
        flash("Задача не найдена.", "error")
        return redirect(url_for("home", view="tasks"))

    if request.method == "GET":
        default_due_date = (
            task["due_date"].isoformat()
            if task["due_date"] else ""
        )

        return render_template(
            "task_creation.html",
            task=task,
            categories=get_categories(),
            default_due_date=default_due_date
        )

    try:
        title, description, due_date, category_id = read_task_form()
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("edit_task", task_id=task_id))

    execute_query("""
        UPDATE tasks
        SET title = %s,
            description = %s,
            due_date = %s,
            category_id = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s
    """, (
        title, description, due_date, category_id,
        task_id, session["user_id"]
    ))

    flash("Изменения успешно сохранены.", "success")
    return redirect(url_for("home", view="tasks"))


# Изменение статуса задачи
@app.route("/tasks/<int:task_id>/status", methods=["POST"])
@login_required
def change_status(task_id):
    new_status = request.form.get("status", "")

    if new_status not in STATUSES:
        flash("Некорректный статус задачи.", "error")
        return redirect(url_for("home", view="tasks"))

    updated_rows = execute_query("""
        UPDATE tasks
        SET status = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s
    """, (new_status, task_id, session["user_id"]))

    if updated_rows:
        flash("Статус задачи обновлён.", "success")
    else:
        flash("Задача не найдена.", "error")

    return redirect(url_for("home", view="tasks"))


# Удаление задачи
@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    deleted_rows = execute_query("""
        DELETE FROM tasks
        WHERE id = %s AND user_id = %s
    """, (task_id, session["user_id"]))

    if deleted_rows:
        flash("Задача успешно удалена.", "success")
    else:
        flash("Задача не найдена.", "error")

    return redirect(url_for("home", view="tasks"))


# Старый адрес статистики
@app.route("/statistics")
@login_required
def statistics():
    return redirect(url_for("home", view="stats"))


# Запуск приложения
if __name__ == "__main__":
    initialize_database()
    app.run(host="0.0.0.0", port=5000, debug=True)
