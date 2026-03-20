import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    # URL берется из переменных окружения (например, на Railway или Render)
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def init_db():
    """Создает таблицу пользователей, если её еще нет"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            tax_rate REAL DEFAULT 10.0,
            username TEXT
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

def get_user_tax(user_id):
    """Получает налог конкретного пользователя (по умолчанию 10.0)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT tax_rate FROM users WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else 10.0

def set_user_tax(user_id, rate, username=None):
    """Сохраняет или обновляет налог пользователя"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, tax_rate, username) 
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET tax_rate = EXCLUDED.tax_rate, username = EXCLUDED.username;
    ''', (user_id, rate, username))
    conn.commit()
    cur.close()
    conn.close()