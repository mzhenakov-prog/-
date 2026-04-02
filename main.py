import asyncio
import logging
import urllib.parse
import aiosqlite
import aiohttp
import socket
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8381032154:AAFsAnTVBGRrHWvedMweeXHsrJTjKgEWUXM"
TMDB_API_KEY = "fdc70aa152320f85d8acdfda64b69b36"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
DB_PATH = "bot_database.db"
ADMIN_ID = 5298604296 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, 
            referred_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, 
            referred_id INTEGER UNIQUE)""")
        await db.commit()

async def register_user(user_id, username, full_name, referred_by=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            if await cur.fetchone(): return False
        await db.execute("INSERT INTO users (user_id, username, full_name, referred_by) VALUES (?, ?, ?, ?)",
                         (user_id, username, full_name, referred_by))
        if referred_by and referred_by != user_id:
            await db.execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                             (referred_by, user_id))
        await db.commit()
    return True

# --- ФУНКЦИИ ПОИСКА (С ФИКСОМ ОШИБКИ 111) ---
async def search_movies(query: str) -> list:
    # trust_env=False игнорирует локальные прокси (127.0.0.1) из логов
    connector = aiohttp.TCPConnector(family=socket.AF_INET, verify_ssl=False)
    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
        try:
            params = {"api_key": TMDB_API_KEY, "query": query, "language": "ru-RU", "include_adult": "false"}
            async with session.get(f"{TMDB_BASE_URL}/search/multi", params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return [i for i in data.get("results", []) if i.get("media_type") in ("movie", "tv")][:5]
                logger.error(f"TMDB Error: {resp.status}")
        except Exception as e:
            logger.error(f"Сетевая ошибка ( Errno 111?): {e}")
    return []

async def get_movie_details(movie_id: int, media_type: str) -> dict:
    connector = aiohttp.TCPConnector(family=socket.AF_INET, verify_ssl=False)
    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
        try:
            params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "append_to_response": "credits"}
            async with session.get(f"{TMDB_BASE_URL}/{media_type}/{movie_id}", params=params) as resp:
                if resp.status == 200: return await resp.json()
        except Exception as e: logger.error(f"Ошибка деталей: {e}")
    return {}

# --- ИНТЕРФЕЙС ---
def main_kb(user_id):
    buttons = [[KeyboardButton(text="🔍 Поиск фильма")]]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="👥 Рефералы")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@dp.message(CommandStart())
async def start(m: Message):
    ref_id = None
    if len(m.text.split()) > 1 and "ref_" in m.text:
        try: ref_id = int(m.text.split()[1].replace("ref_", ""))
        except: pass
    await register_user(m.from_user.id, m.from_user.username, m.from_user.full_name, ref_id)
    await m.answer("🍿 Привет! Напиши название фильма, и я найду его описание, актеров и рейтинг.", 
                   reply_markup=main_kb(m.from_user.id))

@dp.message(F.text == "👥 Рефералы")
async def refs_menu(m: Message):
    if m.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1:
            total = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (ADMIN_ID,)) as c2:
            count = (await c2.fetchone())[0]
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{ADMIN_ID}"
    await m.answer(f"<b>📊 Статистика</b>\n\nЮзеров всего: {total}\nРефералов: {count}\n\n🔗 Ссылка:\n<code>{link}</code>")

@dp.message(F.text == "🔍 Поиск фильма")
async def search_prompt(m: Message):
    await m.answer("🔎 Введите название:")

@dp.message(F.text)
async def handle_query(m: Message):
    if m.text.startswith("/"): return
    status = await m.answer("🔄 Ищу...")
    results = await search_movies(m.text)
    await status.delete()
    if not results:
        await m.answer("😔 Ничего не найдено. Проверь название или попробуй позже.")
        return
    kb = []
    for item in results:
        name = item.get("title") or item.get("name")
        year = (item.get("release_date") or item.get("first_air_date") or "??")[:4]
        kb.append([InlineKeyboardButton(text=f"{name} ({year})", callback_data=f"m_{item['id']}_{item['media_type']}")])
    await m.answer("🎬 Выберите вариант:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("m_"))
async def movie_info(c: CallbackQuery):
    _, mid, mtype = c.data.split("_")
    d = await get_movie_details(mid, mtype)
    if not d: return
    title = d.get("title") or d.get("name")
    year = (d.get("release_date") or d.get("first_air_date") or "Н/Д")[:4]
    actors = ", ".join([a.get("name") for a in d.get("credits", {}).get("cast", [])[:4]]) or "Нет данных"
    text = (f"🎬 <b>{title} ({year})</b>\n\n"
            f"⭐ Рейтинг: <b>{d.get('vote_average', 0):.1f}/10</b>\n"
            f"👥 В ролях: <i>{actors}</i>\n\n"
            f"📝 {d.get('overview', 'Описание отсутствует.')[:500]}...")
    q = urllib.parse.quote(f"{title} {year} смотреть онлайн")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Найти в Google", url=f"https://www.google.com/search?q={q}")],
        [InlineKeyboardButton(text="🔎 Новый поиск", callback_data="reset")]
    ])
    await c.message.delete()
    if d.get("poster_path"):
        await c.message.answer_photo(f"{TMDB_IMAGE_BASE}{d['poster_path']}", caption=text, reply_markup=kb)
    else:
        await c.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "reset")
async def reset_cb(c: CallbackQuery):
    await c.message.answer("🔎 Введите название фильма:")

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
