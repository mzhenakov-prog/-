import asyncio
import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

# --- токены тренировочные ---
BOT_TOKEN = "8381032154:AAFsAnTVBGRrHWvedMweeXHsrJTjKgEWUXM"
TMDB_API_KEY = "fdc70aa152320f85d8acdfda64b69b36"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- база данных рефералов ---
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

# --- клавиатура ---
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
    referrer = int(args[1]) if len(args) > 1 else None
    await add_user(message.from_user.id, referrer)
    await message.answer("🎬 Напиши название фильма", reply_markup=menu)

# --- рефералы ---
@dp.message(lambda msg: msg.text == "👥 Рефералы")
async def refs(message: types.Message):
    count = await get_ref_count(message.from_user.id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    await message.answer(f"👥 Твои рефералы: {count}\n\n🔗 Твоя ссылка:\n{link}")

# --- поиск фильмов ---
async def search_movie_api(query, session):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}&language=ru-RU"
    async with session.get(url) as resp:
        return await resp.json()

@dp.message()
async def search_movie(message: types.Message):
    async with aiohttp.ClientSession() as session:
        data = await search_movie_api(message.text, session)

    results = data.get("results", [])[:10]
    if not results:
        await message.answer("❌ Ничего не найдено")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for film in results:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=film["title"], callback_data=f"film_{film['id']}")
        ])

    await message.answer("🎬 Выбери фильм:", reply_markup=kb)

# --- выбор фильма ---
async def get_film_details(film_id, session):
    url = f"https://api.themoviedb.org/3/movie/{film_id}?api_key={TMDB_API_KEY}&language=ru-RU"
    async with session.get(url) as resp:
        return await resp.json()

@dp.callback_query(lambda c: c.data.startswith("film_"))
async def show_film(callback: types.CallbackQuery):
    film_id = callback.data.split("_")[1]

    async with aiohttp.ClientSession() as session:
        film = await get_film_details(film_id, session)

    title = film["title"]
    overview = film.get("overview") or "Нет описания"
    rating = film.get("vote_average")
    poster = f"https://image.tmdb.org/t/p/w500{film['poster_path']}"
    watch_url = f"https://yandex.kz/search/?text={title}+смотреть+онлайн"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🎬 Смотреть фильм", url=watch_url)]]
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
