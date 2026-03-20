import psycopg2
import os
from dotenv import load_dotenv

# Загружаем переменные окружения (DATABASE_URL)
load_dotenv()

def get_connection():
    """Устанавливает соединение с базой данных PostgreSQL"""
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def init_db():
    """
    Инициализирует структуру базы данных.
    Создает таблицу users, если она еще не существует.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Таблица пользователей с настройками налога, токенами и флагом уведомлений
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            tax_rate REAL DEFAULT 10.0,
            wb_token_standard TEXT,
            wb_token_statistic TEXT,
            notifications_on BOOLEAN DEFAULT TRUE,
            last_report_date DATE
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

def get_user_tax(user_id):
    """Получает налоговую ставку пользователя (по умолчанию 10.0)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT tax_rate FROM users WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else 10.0

def set_user_tax(user_id, rate, username=None):
    """Обновляет или создает запись пользователя с новой налоговой ставкой"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, tax_rate, username) 
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE 
        SET tax_rate = EXCLUDED.tax_rate, 
            username = COALESCE(EXCLUDED.username, users.username);
    ''', (user_id, rate, username))
    conn.commit()
    cur.close()
    conn.close()

def save_tokens(user_id, token_std=None, token_stat=None):
    """
    Сохраняет API-токены Wildberries (Стандартный и Статистика).
    Использует COALESCE, чтобы не затереть существующий токен, если передается только один.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, wb_token_standard, wb_token_statistic)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE 
        SET wb_token_standard = COALESCE(EXCLUDED.wb_token_standard, users.wb_token_standard),
            wb_token_statistic = COALESCE(EXCLUDED.wb_token_statistic, users.wb_token_statistic);
    ''', (user_id, token_std, token_stat))
    conn.commit()
    cur.close()
    conn.close()

def get_user_tokens(user_id):
    """Возвращает все токены и налоговую ставку пользователя"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT wb_token_standard, wb_token_statistic, tax_rate FROM users WHERE user_id = %s", (user_id,))
    res = cur.fetchone()
    cur.close()
    conn.close()
    return res if res else (None, None, 10.0)

def get_all_active_users():
    """
    Возвращает список пользователей, у которых привязан токен статистики 
    и включены уведомления. Используется для утренней рассылки.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT user_id, wb_token_statistic 
        FROM users 
        WHERE wb_token_statistic IS NOT NULL AND notifications_on = TRUE
    ''')
    users = cur.fetchall()
    cur.close()
    conn.close()
    return users