import asyncio
import logging
import urllib.parse
import aiosqlite
import aiohttp
import socket
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    BotCommand
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8381032154:AAFsAnTVBGRrHWvedMweeXHsrJTjKgEWUXM"
TMDB_API_KEY = "fdc70aa152320f85d8acdfda64b69b36"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
DB_PATH = "bot_database.db"
ADMIN_ID = 5298604296 # Ваш ID

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

# --- API ТЕХНОЛОГИИ ---
async def search_movies(query: str) -> list:
    results = []
    connector = aiohttp.TCPConnector(family=socket.AF_INET, verify_ssl=False)
    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
        try:
            params = {"api_key": TMDB_API_KEY, "query": query, "language": "ru-RU"}
            async with session.get(f"{TMDB_BASE_URL}/search/multi", params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("results", [])[:5]:
                        if item.get("media_type") in ("movie", "tv"):
                            results.append(item)
        except Exception as e: logger.error(f"Search error: {e}")
    return results

async def get_movie_details(movie_id: int, media_type: str) -> dict:
    connector = aiohttp.TCPConnector(family=socket.AF_INET, verify_ssl=False)
    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
        try:
            params = {"api_key": TMDB_API_KEY, "language": "ru-RU", "append_to_response": "credits"}
            async with session.get(f"{TMDB_BASE_URL}/{media_type}/{movie_id}", params=params) as resp:
                if resp.status == 200: return await resp.json()
        except Exception as e: logger.error(f"Details error: {e}")
    return {}

# --- КЛАВИАТУРЫ ---
def get_main_kb(user_id):
    buttons = [[KeyboardButton(text="🔍 Поиск фильма")]]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="👥 Реферальная система")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def cmd_start(m: Message):
    ref_id = None
    if len(m.text.split()) > 1 and m.text.split()[1].startswith("ref_"):
        try: ref_id = int(m.text.split()[1].replace("ref_", ""))
        except: pass
    
    await register_user(m.from_user.id, m.from_user.username, m.from_user.full_name, ref_id)
    await m.answer(f"🎬 Привет! Я помогу найти фильм, покажу актеров и дам ссылку на Google.", 
                   reply_markup=get_main_kb(m.from_user.id))

@dp.message(F.text == "👥 Реферальная система")
async def show_ref_menu(m: Message):
    if m.from_user.id != ADMIN_ID: return
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1:
            total_users = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (ADMIN_ID,)) as c2:
            total_refs = (await c2.fetchone())[0]

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{ADMIN_ID}"
    
    text = (f"<b>📊 Статистика:</b>\n\n"
            f"👤 Всего в боте: {total_users}\n"
            f"🤝 Ваших рефералов: {total_refs}\n\n"
            f"🔗 Ваша ссылка:\n<code>{link}</code>")
    await m.answer(text)

@dp.message(F.text == "🔍 Поиск фильма")
async def start_search(m: Message):
    await m.answer("🔎 Введите название фильма:")

@dp.message(F.text)
async def handle_query(m: Message):
    res = await search_movies(m.text)
    if not res:
        await m.answer("😔 Ничего не найдено.")
        return
    
    kb = []
    for item in res:
        name = item.get("title") or item.get("name")
        kb.append([InlineKeyboardButton(text=name, callback_data=f"det_{item['id']}_{item['media_type']}")])
    await m.answer("Выберите результат:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("det_"))
async def show_details(c: CallbackQuery):
    _, mid, mtype = c.data.split("_")
    d = await get_movie_details(mid, mtype)
    if not d: return

    title = d.get("title") or d.get("name")
    cast = ", ".join([a.get("name") for a in d.get("credits", {}).get("cast", [])[:4]])
    text = (f"🎬 <b>{title}</b>\n\n"
            f"⭐ Рейтинг: {d.get('vote_average', 0):.1f}\n"
            f"👥 В ролях: {cast}\n\n"
            f"📝 {d.get('overview', 'Нет описания.')[:500]}...")
    
    q = urllib.parse.quote(f"{title} {str(d.get('release_date', ''))[:4]} смотреть онлайн")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Найти в Google", url=f"https://www.google.com/search?q={q}")],
        [InlineKeyboardButton(text="🔍 Новый поиск", callback_data="reset")]
    ])
    
    if d.get("poster_path"):
        await c.message.answer_photo(f"{TMDB_IMAGE_BASE}{d['poster_path']}", caption=text, reply_markup=kb)
    else:
        await c.message.answer(text, reply_markup=kb)
    await c.answer()

@dp.callback_query(F.data == "reset")
async def reset_search(c: CallbackQuery):
    await c.message.answer("🔎 Введите название:")
    await c.answer()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
