import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    # Таблица пользователей с настройками и токенами
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            tax_rate REAL DEFAULT 10.0,
            wb_token_standard TEXT,
            wb_token_statistic TEXT,
            notifications_on BOOLEAN DEFAULT TRUE,
            last_report_date DATE
        );
    ''')
    # Таблица для истории уведомлений о заказах (чтобы не дублировать)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sent_orders (
            order_id TEXT PRIMARY KEY,
            user_id BIGINT
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

def add_new_user(user_id, username, first_name):
    """Регистрирует или обновляет данные пользователя"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, username, first_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE 
        SET username = EXCLUDED.username, 
            first_name = EXCLUDED.first_name;
    ''', (user_id, username, first_name))
    conn.commit()
    cur.close()
    conn.close()

def get_user_tax(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT tax_rate FROM users WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else 10.0

def set_user_tax(user_id, rate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET tax_rate = %s WHERE user_id = %s", (rate, user_id))
    conn.commit()
    cur.close()
    conn.close()

def save_tokens(user_id, token_std=None, token_stat=None):
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

def get_all_active_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, wb_token_statistic FROM users WHERE wb_token_statistic IS NOT NULL AND notifications_on = TRUE")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return users