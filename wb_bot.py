import logging
import asyncio
import math
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import os
from dotenv import load_dotenv

load_dotenv() # Загружает переменные из .env
TOKEN = os.getenv("API_TOKEN,WB_API_KEY")
# --- НАСТРОЙКИ ---
API_TOKEN = os.getenv("API_TOKEN")
WB_API_KEY = os.getenv("WB_API_KEY")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(
        "wb_final.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


class CalcState(StatesGroup):
    main_mode = State()
    work_mode = State()
    category_step = State()
    target_profit = State()
    price = State()
    dims = State()
    cost = State()

# --- API WB (Интеграция по Swagger + Фикс нулевых процентов) ---


def get_wb_commission(query):
    url = "https://common-api.wildberries.ru/api/v1/tariffs/commission"
    params = {"locale": "ru"}
    headers = {"Authorization": WB_API_KEY}

    try:
        logger.info(f"📡 Запрос тарифов. Поиск: {query}")
        res = requests.get(url, headers=headers, params=params, timeout=10)

        if res.status_code == 200:
            data = res.json()
            all_cats = data.get('report', [])  # Поле из твоих логов

            if not all_cats:
                return "EMPTY"

            search_root = query.lower().strip()
            if len(search_root) > 4:
                search_root = search_root[:-1]

            found = []
            for c in all_cats:
                s_name = str(c.get('subjectName', '')).lower()
                p_name = str(c.get('parentName', '')).lower()

                if search_root in s_name or search_root in p_name:
                    found.append(c)

            logger.info(f"✅ Найдено совпадений: {len(found)}")
            return found[:10]
        return None
    except Exception as e:
        logger.exception(f"💥 Ошибка API: {e}")
        return None


# --- КЛАВИАТУРЫ ---
main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Считать прибыль"),
     KeyboardButton(text="🎯 Цель по прибыли")]
], resize_keyboard=True)

mode_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="FBO"), KeyboardButton(text="FBS")]
], resize_keyboard=True)

# --- ЛОГИКА ---


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(CalcState.main_mode)
    await message.answer("🚀 **WB Калькулятор Армения**\nВыберите режим:", reply_markup=main_kb, parse_mode="Markdown")


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
    await message.answer("🔎 Введите название товара (напр: Брюки) или % комиссии числом:")

@dp.message(CalcState.category_step)
async def process_category(message: types.Message, state: FSMContext):
    user_text = message.text.strip()
    data = await state.get_data()

    # 1. Если нажали на кнопку с процентом (есть символ '|')
    if '|' in user_text:
        try:
            # Извлекаем только число процентов
            comm_part = user_text.split('|')[1].replace('%', '').strip()
            comm_val = float(comm_part)
            await state.update_data(commission=comm_val)
            logger.info(f"✅ Выбрана категория из списка: {user_text} -> {comm_val}%")
            await proceed_to_money(message, state, data)
            return
        except Exception as e:
            logger.error(f"Ошибка парсинга кнопки: {e}")

    # 2. Если ввели просто число (напр: 15)
    clean_val = user_text.replace('%', '').replace(',', '.')
    if clean_val.replace('.', '', 1).isdigit():
        await state.update_data(commission=float(clean_val))
        await proceed_to_money(message, state, data)
        return

    # 3. Если это текстовый запрос для поиска в API
    results = get_wb_commission(user_text)
    
    if results == "EMPTY" or not results:
        await message.answer("❌ Категория не найдена. Введите % вручную (просто число):")
    else:
        kb_btns = []
        work_mode = data.get('work_mode', 'FBO')
        for r in results:
            name = r.get('subjectName', 'Категория')
            # Выбираем комиссию в зависимости от режима
            fbo = r.get('kgvpSupplier', 0)
            fbs = r.get('kgvpMarketplace', 0)
            gen = r.get('commission', 0)
            
            final_comm = (fbs if work_mode == "FBS" else fbo) or gen or 0
            kb_btns.append([KeyboardButton(text=f"{name} | {final_comm}%")])
        
        markup = ReplyKeyboardMarkup(keyboard=kb_btns, resize_keyboard=True)
        await message.answer(f"Выберите категорию (режим {work_mode}):", reply_markup=markup)

@dp.message(F.text.contains('|'))
async def catch_btn(message: types.Message, state: FSMContext):
    try:
        comm = float(message.text.split('|')[1].replace('%', '').strip())
        await state.update_data(commission=comm)
        data = await state.get_data()
        await proceed_to_money(message, state, data)
    except:
        await message.answer("Введите число.")


async def proceed_to_money(message, state, data):
    if data['main_mode'] == "🎯 Цель по прибыли":
        await state.set_state(CalcState.target_profit)
        await message.answer("💰 Какую чистую прибыль хотите получить?", reply_markup=ReplyKeyboardRemove())
    else:
        await state.set_state(CalcState.price)
        await message.answer("💵 Введите цену продажи на сайте:", reply_markup=ReplyKeyboardRemove())


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
        await message.answer("📏 Габариты (Д Ш В в см) через пробел:")
    except:
        await message.answer("Введите число.")


@dp.message(CalcState.dims)
async def process_dims(message: types.Message, state: FSMContext):
    try:
        dims = list(map(float, message.text.split()))
        await state.update_data(volume=(dims[0]*dims[1]*dims[2])/1000)
        await state.set_state(CalcState.cost)
        await message.answer("📦 Себестоимость (закупка + доставка):")
    except:
        await message.answer("Введите 3 числа.")


@dp.message(CalcState.cost)
async def final_calc(message: types.Message, state: FSMContext):
    try:
        cost = float(message.text.replace(',', '.'))
        data = await state.get_data()
        vol = data['volume']
        comm_pct = data['commission'] / 100
        tax_pct = 0.10  # Налог 10%

        # Расчет логистики (65.6 база + 7 за доп литр)
        log_total = 65.6 + (max(0, math.ceil(vol - 1)) * 7)
        storage = (0.16 * 30) if data['work_mode'] == "FBO" else 0
        fixed = cost + log_total + storage + 5.0 + 1.7
        if data['work_mode'] == "FBS":
            fixed += 15

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
            profit = price - (price*tax_pct) - (price*comm_pct) - fixed
            res = (
                f"📊 **ОТЧЕТ О ПРИБЫЛИ**\n"
                f"──────────────────────────\n"
                f"Цена: {price:,.0f} ₽ | Прибыль: **{profit:,.1f} ₽**\n"
                f"📈 ROI: `{(profit/cost*100):.1f}%`"
            )
        await message.answer(res, parse_mode="Markdown", reply_markup=main_kb)
        await state.clear()
        await state.set_state(CalcState.main_mode)
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.answer("⚠ Ошибка данных.")


async def main(): await dp.start_polling(bot)
if __name__ == "__main__":
    asyncio.run(main())
