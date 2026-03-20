import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    # Подключаемся к PostgreSQL по URL из .env
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def init_db():
    """Создает таблицу пользователей, если её нет"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            tax_rate REAL DEFAULT 6.0,
            last_calc_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
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
    return result[0] if result else 6.0

def set_user_tax(user_id, rate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, tax_rate) 
        VALUES (%s, %s) 
        ON CONFLICT (user_id) DO UPDATE SET tax_rate = EXCLUDED.tax_rate
    ''', (user_id, rate))
    conn.commit()
    cur.close()
    conn.close()