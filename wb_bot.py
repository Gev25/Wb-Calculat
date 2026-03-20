import logging
import asyncio
import math
import os
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# Библиотека для запуска задач по расписанию
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests

# Импорт функций из твоих файлов
from database import init_db, get_user_tax, set_user_tax, save_tokens, get_all_active_users
from wb_api import get_daily_stats

load_dotenv()

# --- НАСТРОЙКИ ---
API_TOKEN = os.getenv("API_TOKEN")
WB_API_KEY = os.getenv("WB_API_KEY")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("wb_final.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Asia/Yerevan") # Время Еревана

class CalcState(StatesGroup):
    main_mode = State()
    work_mode = State()
    category_step = State()
    target_profit = State()
    price = State()
    dims = State()
    cost = State()
    waiting_for_tax = State()
    waiting_for_token = State()

# --- КЛАВИАТУРЫ ---
main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Считать прибыль"), KeyboardButton(text="🎯 Цель по прибыли")],
    [KeyboardButton(text="🔗 Привязать магазин"), KeyboardButton(text="⚙️ Настроить налог")]
], resize_keyboard=True)

mode_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="FBO"), KeyboardButton(text="FBS")]
], resize_keyboard=True)

# --- АВТОМАТИЧЕСКИЕ ОТЧЕТЫ ---
async def send_daily_reports():
    """Рассылка статистики всем пользователям с токенами"""
    users = get_all_active_users() # Берем из database.py
    for user_id, token_stat in users:
        stats = get_daily_stats(token_stat) # Запрос к API из wb_api.py
        if stats:
            text = (
                f"☀️ **Ежедневный отчет WB**\n"
                f"──────────────────────────\n"
                f"📦 Заказов вчера: **{stats['count']}** шт.\n"
                f"💰 Сумма: **{stats['sum']:,.0f} ₽**\n"
                f"──────────────────────────\n"
                f"Используйте калькулятор для расчета новых товаров!"
            )
            try:
                await bot.send_message(user_id, text, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Ошибка отправки отчета пользователю {user_id}: {e}")

# --- API WB (Комиссии) ---
def get_wb_commission(query):
    url = "https://common-api.wildberries.ru/api/v1/tariffs/commission"
    params = {"locale": "ru"}
    headers = {"Authorization": WB_API_KEY}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        if res.status_code == 200:
            all_cats = res.json().get('report', [])
            search_root = query.lower().strip()
            found = [c for c in all_cats if search_root in str(c.get('subjectName', '')).lower()]
            return found[:10]
        return None
    except Exception as e:
        logger.error(f"Ошибка API Комиссий: {e}")
        return None

# --- ОБРАБОТЧИКИ КОМАНД ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    tax = get_user_tax(message.from_user.id) #
    await message.answer(
        f"🚀 **WB Калькулятор Армения**\nВаш налог: **{tax}%**\nВыберите режим:", 
        reply_markup=main_kb, 
        parse_mode="Markdown"
    )
    await state.set_state(CalcState.main_mode)

@dp.message(F.text == "🔗 Привязать магазин")
async def start_token(message: types.Message, state: FSMContext):
    await message.answer("Отправьте ваш API токен (категория 'Статистика'):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CalcState.waiting_for_token)

@dp.message(CalcState.waiting_for_token)
async def process_token(message: types.Message, state: FSMContext):
    token = message.text.strip()
    save_tokens(message.from_user.id, token_stat=token) # Сохраняем в Postgres
    await message.answer("✅ Токен сохранен! Теперь я буду присылать отчеты в 09:00.", reply_markup=main_kb)
    await state.set_state(CalcState.main_mode)

@dp.message(F.text == "⚙️ Настроить налог")
async def start_set_tax(message: types.Message, state: FSMContext):
    await message.answer("Введите вашу налоговую ставку (только число):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CalcState.waiting_for_tax)

@dp.message(CalcState.waiting_for_tax)
async def process_set_tax(message: types.Message, state: FSMContext):
    try:
        new_tax = float(message.text.replace(',', '.'))
        set_user_tax(message.from_user.id, new_tax) #
        await message.answer(f"✅ Налог сохранен: {new_tax}%", reply_markup=main_kb)
        await state.set_state(CalcState.main_mode)
    except:
        await message.answer("Введите корректное число.")

# --- ЛОГИКА КАЛЬКУЛЯТОРА (Твой оригинальный код с улучшениями) ---

@dp.message(CalcState.main_mode)
async def process_main_mode(message: types.Message, state: FSMContext):
    if message.text not in ["📊 Считать прибыль", "🎯 Цель по прибыли"]: return
    await state.update_data(main_mode=message.text)
    await state.set_state(CalcState.work_mode)
    await message.answer("Выберите тип поставки:", reply_markup=mode_kb)

@dp.message(CalcState.work_mode)
async def process_work_mode(message: types.Message, state: FSMContext):
    await state.update_data(work_mode=message.text)
    await state.set_state(CalcState.category_step)
    await message.answer("🔎 Введите название товара для поиска комиссии:", reply_markup=ReplyKeyboardRemove())

@dp.message(CalcState.category_step)
async def process_category(message: types.Message, state: FSMContext):
    user_text = message.text.strip()
    data = await state.get_data()

    if '|' in user_text:
        comm_val = float(user_text.split('|')[1].replace('%', '').strip())
        await state.update_data(commission=comm_val)
        await proceed_to_money(message, state, data)
        return

    results = get_wb_commission(user_text) #
    if not results:
        await message.answer("❌ Категория не найдена. Введите % комиссии числом:")
    else:
        kb_btns = []
        mode = data.get('work_mode', 'FBO')
        for r in results:
            val = (r.get('kgvpMarketplace') if mode == "FBS" else r.get('kgvpSupplier')) or r.get('commission', 0)
            kb_btns.append([KeyboardButton(text=f"{r.get('subjectName')} | {val}%")])
        await message.answer("Выберите подкатегорию:", reply_markup=ReplyKeyboardMarkup(keyboard=kb_btns, resize_keyboard=True))

async def proceed_to_money(message, state, data):
    is_target = data['main_mode'] == "🎯 Цель по прибыли"
    await state.set_state(CalcState.target_profit if is_target else CalcState.price)
    text = "💰 Желаемая чистая прибыль:" if is_target else "💵 Цена продажи на сайте:"
    await message.answer(text, reply_markup=ReplyKeyboardRemove())

@dp.message(CalcState.target_profit)
@dp.message(CalcState.price)
async def process_money(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(',', '.'))
        curr_state = await state.get_state()
        if "target_profit" in str(curr_state): await state.update_data(target_profit=val)
        else: await state.update_data(price=val)
        await state.set_state(CalcState.dims)
        await message.answer("📏 Габариты (Д Ш В в см) через пробел:")
    except: await message.answer("Пожалуйста, введите число.")

@dp.message(CalcState.dims)
async def process_dims(message: types.Message, state: FSMContext):
    try:
        dims = list(map(float, message.text.split()))
        await state.update_data(volume=(dims[0]*dims[1]*dims[2])/1000)
        await state.set_state(CalcState.cost)
        await message.answer("📦 Себестоимость (закупка + доставка до склада):")
    except: await message.answer("Введите 3 числа (например: 10 20 5).")

@dp.message(CalcState.cost)
async def final_calc(message: types.Message, state: FSMContext):
    try:
        cost = float(message.text.replace(',', '.'))
        data = await state.get_data()
        user_tax = get_user_tax(message.from_user.id)
        tax_pct, comm_pct, vol = user_tax / 100, data['commission'] / 100, data['volume']

        # Расчет логистики WB Армения
        log_total = 65.6 + (max(0, math.ceil(vol - 1)) * 7)
        storage = (0.16 * 30) if data['work_mode'] == "FBO" else 0
        fixed = cost + log_total + storage + 6.7 # 5.0 + 1.7 доп. расходы
        if data['work_mode'] == "FBS": fixed += 15

        if data['main_mode'] == "🎯 Цель по прибыли":
            target = data['target_profit']
            rec_price = (target + fixed) / (1 - tax_pct - comm_pct)
            res = (
                f"🎯 **РЕЗУЛЬТАТ ПЛАНИРОВАНИЯ**\n"
                f"──────────────────────────\n"
                f"Цель прибыли: **{target:,.0f} ₽**\n"
                f"💰 **ЦЕНА НА САЙТЕ: {rec_price:,.0f} ₽**\n"
                f"──────────────────────────\n"
                f"📈 ROI: `{(target/cost*100):.1f}%`"
            )
        else:
            price = data['price']
            profit = price - (price * tax_pct) - (price * comm_pct) - fixed
            res = (
                f"📊 **ОТЧЕТ О ПРИБЫЛИ**\n"
                f"──────────────────────────\n"
                f"Цена: {price:,.0f} ₽ | Прибыль: **{profit:,.1f} ₽**\n"
                f"Налог ({user_tax}%): **{(price*tax_pct):,.1f} ₽**\n"
                f"📈 ROI: `{(profit/cost*100):.1f}%`"
            )
        
        await message.answer(res, parse_mode="Markdown", reply_markup=main_kb)
        await state.set_state(CalcState.main_mode)
    except Exception as e:
        logger.error(f"Ошибка расчета: {e}")
        await message.answer("⚠ Ошибка в данных. Начните расчет заново.")

# --- ЗАПУСК ---
async def main():
    init_db() #
    # Добавляем задачу: каждый день в 09:00 по Еревану
    scheduler.add_job(send_daily_reports, "cron", hour=9, minute=0)
    scheduler.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())