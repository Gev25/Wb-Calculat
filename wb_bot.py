import logging
import asyncio
import math
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Импорт из твоих файлов
from database import init_db, get_user_tax, set_user_tax, save_tokens, get_all_active_users, add_new_user
from wb_api import get_daily_stats

load_dotenv()

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = os.getenv("API_TOKEN")
WB_API_KEY = os.getenv("WB_API_KEY")
ADMIN_ID = 1381500667  # Твой ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(
        "wb_final.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Asia/Yerevan")


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
    [KeyboardButton(text="📊 Считать прибыль"),
     KeyboardButton(text="🎯 Цель по прибыли")],
    [KeyboardButton(text="🔗 Привязать магазин"),
     KeyboardButton(text="⚙️ Настроить налог")]
], resize_keyboard=True)

mode_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="FBO"), KeyboardButton(text="FBS")]
], resize_keyboard=True)

# --- ФУНКЦИИ ПЛАНИРОВЩИКА ---


async def send_daily_reports():
    users = get_all_active_users()
    for user_id, token_stat in users:
        stats = get_daily_stats(token_stat)
        if stats:
            text = (f"☀️ **Ежедневный отчет WB**\n"
                    f"──────────────────────────\n"
                    f"📦 Заказов вчера: **{stats['count']}** шт.\n"
                    f"💰 Сумма: **{stats['sum']:,.0f} ₽**\n"
                    f"──────────────────────────\n")
            try:
                await bot.send_message(user_id, text, parse_mode="Markdown")
            except:
                pass

# --- ОБРАБОТЧИКИ ---


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    # 1. Сохраняем нового пользователя в БД
    add_new_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )

    # 2. Уведомление администратору (Тебе)
    try:
        admin_msg = (f"👤 **Новый пользователь!**\n"
                     f"Имя: {message.from_user.first_name}\n"
                     f"Юзер: @{message.from_user.username}\n"
                     f"ID: `{message.from_user.id}`")
        await bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка уведомления админа: {e}")

    # 3. Ответ пользователю
    tax = get_user_tax(message.from_user.id)
    await message.answer(
        f"🚀 **WB Калькулятор (Армения)**\nВаш налог: **{tax}%**\nВыберите режим:",
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
    save_tokens(message.from_user.id, token_stat=message.text.strip())
    await message.answer("✅ Токен статистики сохранен! Отчеты будут приходить в 09:00.", reply_markup=main_kb)
    await state.set_state(CalcState.main_mode)


@dp.message(F.text == "⚙️ Настроить налог")
async def start_set_tax(message: types.Message, state: FSMContext):
    await message.answer("Введите налоговую ставку (число):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(CalcState.waiting_for_tax)


@dp.message(CalcState.waiting_for_tax)
async def process_set_tax(message: types.Message, state: FSMContext):
    try:
        new_tax = float(message.text.replace(',', '.'))
        set_user_tax(message.from_user.id, new_tax)
        await message.answer(f"✅ Налог {new_tax}% сохранен.", reply_markup=main_kb)
        await state.set_state(CalcState.main_mode)
    except:
        await message.answer("Введите число.")

# --- API КОМИССИЙ ---


def get_wb_commission(query):
    url = "https://common-api.wildberries.ru/api/v1/tariffs/commission"
    headers = {"Authorization": WB_API_KEY}
    try:
        res = requests.get(url, headers=headers, params={
                           "locale": "ru"}, timeout=10)
        if res.status_code == 200:
            all_cats = res.json().get('report', [])
            search = query.lower().strip()
            return [c for c in all_cats if search in str(c.get('subjectName', '')).lower()][:10]
        return None
    except:
        return None

# --- ШАГИ КАЛЬКУЛЯТОРА ---


@dp.message(CalcState.main_mode)
async def process_main_mode(message: types.Message, state: FSMContext):
    if message.text not in ["📊 Считать прибыль", "🎯 Цель по прибыли"]:
        return
    await state.update_data(main_mode=message.text)
    await state.set_state(CalcState.work_mode)
    await message.answer("Тип поставки:", reply_markup=mode_kb)


@dp.message(CalcState.work_mode)
async def process_work_mode(message: types.Message, state: FSMContext):
    await state.update_data(work_mode=message.text)
    await state.set_state(CalcState.category_step)
    await message.answer("🔎 Введите название товара:", reply_markup=ReplyKeyboardRemove())


@dp.message(CalcState.category_step)
async def process_category(message: types.Message, state: FSMContext):
    user_text = message.text.strip()
    data = await state.get_data()
    if '|' in user_text:
        comm = float(user_text.split('|')[1].replace('%', '').strip())
        await state.update_data(commission=comm)
        is_target = data['main_mode'] == "🎯 Цель по прибыли"
        await state.set_state(CalcState.target_profit if is_target else CalcState.price)
        await message.answer("💰 Введите сумму:", reply_markup=ReplyKeyboardRemove())
        return
    results = get_wb_commission(user_text)
    if not results:
        await message.answer("❌ Категория не найдена. Введите % комиссии числом:")
    else:
        btns = [[KeyboardButton(
            text=f"{r['subjectName']} | {r['kgvpSupplier']}%")] for r in results]
        await message.answer("Выберите из списка:", reply_markup=ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True))


@dp.message(CalcState.target_profit)
@dp.message(CalcState.price)
async def process_money(message: types.Message, state: FSMContext):
    try:
        val = float(message.text.replace(',', '.'))
        if "target_profit" in str(await state.get_state()):
            await state.update_data(target_profit=val)
        else:
            await state.update_data(price=val)
        await state.set_state(CalcState.dims)
        await message.answer("📏 Габариты (Д Ш В) через пробел:")
    except:
        await message.answer("Введите число.")


@dp.message(CalcState.dims)
async def process_dims(message: types.Message, state: FSMContext):
    try:
        d = list(map(float, message.text.split()))
        await state.update_data(volume=(d[0]*d[1]*d[2])/1000)
        await state.set_state(CalcState.cost)
        await message.answer("📦 Себестоимость:")
    except:
        await message.answer("Введите 3 числа.")


@dp.message(CalcState.cost)
async def final_calc(message: types.Message, state: FSMContext):
    try:
        cost = float(message.text.replace(',', '.'))
        data = await state.get_data()
        tax_pct, comm_pct, vol = get_user_tax(
            message.from_user.id)/100, data['commission']/100, data['volume']

        log = 65.6 + (max(0, math.ceil(vol - 1)) * 7)
        fixed = cost + log + \
            (0.16*30 if data['work_mode'] == "FBO" else 15) + 6.7

        if data['main_mode'] == "🎯 Цель по прибыли":
            res_p = (data['target_profit'] + fixed) / (1 - tax_pct - comm_pct)
            msg = f"🎯 Рекомендуемая цена: **{res_p:,.0f} ₽**"
        else:
            p = data['price']
            prof = p - (p*tax_pct) - (p*comm_pct) - fixed
            msg = f"📊 Прибыль: **{prof:,.1f} ₽**\n📈 ROI: `{(prof/cost*100):.1f}%`"

        await message.answer(msg, parse_mode="Markdown", reply_markup=main_kb)
        await state.set_state(CalcState.main_mode)
    except:
        await message.answer("Ошибка в данных.")


async def main():
    init_db()
    scheduler.add_job(send_daily_reports, "cron", hour=9, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
