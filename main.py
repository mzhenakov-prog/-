import os
import asyncio
import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from dotenv import load_dotenv

# --- загрузка env ---
load_dotenv()

BOT_TOKEN = os.getenv("8381032154:AAFsAnTVBGRrHWvedMweeXHsrJTjKgEWUXM")
TMDB_API_KEY = os.getenv("fdc70aa152320f85d8acdfda64b69b36")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

session = aiohttp.ClientSession()

# --- база данных ---
DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            referrer INTEGER
        )
        """)
        await db.commit()

async def add_user(user_id, referrer=None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, referrer) VALUES (?, ?)",
            (user_id, referrer)
        )
        await db.commit()

async def get_ref_count(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE referrer=?",
            (user_id,)
        )
        result = await cursor.fetchone()
        return result[0]

# --- меню ---
menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👥 Рефералы")]
    ],
    resize_keyboard=True
)

# --- старт ---
@dp.message(CommandStart())
async def start(message: types.Message):
    args = message.text.split()

    referrer = None
    if len(args) > 1:
        try:
            referrer = int(args[1])
        except:
            referrer = None

    await add_user(message.from_user.id, referrer)

    await message.answer("🎬 Напиши название фильма", reply_markup=menu)

# --- рефералы ---
@dp.message(lambda msg: msg.text == "👥 Рефералы")
async def refs(message: types.Message):
    count = await get_ref_count(message.from_user.id)

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"

    await message.answer(
        f"👥 Твои рефералы: {count}\n\n🔗 Твоя ссылка:\n{link}"
    )

# --- поиск фильмов ---
@dp.message()
async def search_movie(message: types.Message):
    query = message.text

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}&language=ru-RU"

    async with session.get(url) as resp:
        data = await resp.json()

    results = data.get("results", [])[:10]

    if not results:
        await message.answer("❌ Ничего не найдено")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for film in results:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=film["title"],
                callback_data=f"film_{film['id']}"
            )
        ])

    await message.answer("🎬 Выбери фильм:", reply_markup=kb)

# --- выбор фильма ---
@dp.callback_query(lambda c: c.data.startswith("film_"))
async def show_film(callback: types.CallbackQuery):
    film_id = callback.data.split("_")[1]

    url = f"https://api.themoviedb.org/3/movie/{film_id}?api_key={TMDB_API_KEY}&language=ru-RU"

    async with session.get(url) as resp:
        film = await resp.json()

    title = film["title"]
    overview = film["overview"] or "Нет описания"
    rating = film["vote_average"]
    poster = f"https://image.tmdb.org/t/p/w500{film['poster_path']}"

    # ссылка на просмотр
    watch_url = f"https://yandex.kz/search/?text={title}+смотреть+онлайн"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Смотреть фильм", url=watch_url)]
        ]
    )

    text = f"🎬 <b>{title}</b>\n\n⭐ {rating}\n\n📄 {overview}"

    await callback.message.answer_photo(
        photo=poster,
        caption=text,
        reply_markup=kb,
        parse_mode="HTML"
    )

    await callback.answer()

# --- запуск ---
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
