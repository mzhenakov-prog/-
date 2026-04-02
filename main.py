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
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# Конфигурация (Рекомендуется использовать .env)
BOT_TOKEN = "8381032154:AAFsAnTVBGRrHWvedMweeXHsrJTjKgEWUXM"
TMDB_API_KEY = "fdc70aa152320f85d8acdfda64b69b36"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
DB_PATH = "bot_database.db"

ADMIN_ID = 5298604296

REQUIRED_CHANNELS = [
    {"id": -1003861409701, "url": "https://t.me/kinoo_rum",  "name": "🎬 Kino Rum"},
    {"id": -1001888094511, "url": "https://t.me/lyubimkatt", "name": "❤️ Lyubimkat"},
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# --- Системные функции ---

async def check_subscriptions(user_id: int) -> list:
    not_subscribed = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status in ("left", "kicked"):
                not_subscribed.append(channel)
        except Exception as e:
            logger.error(f"Subscription check error: {e}")
    return not_subscribed

def subscription_keyboard(not_subscribed: list) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"👉 {ch['name']}", url=ch["url"])] for ch in not_subscribed]
    buttons.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def require_subscription(message: Message) -> bool:
    if message.from_user.id == ADMIN_ID:
        return True
    not_subscribed = await check_subscriptions(message.from_user.id)
    if not_subscribed:
        await message.answer(
            "🔒 <b>Подпишитесь на каналы для доступа:</b>",
            reply_markup=subscription_keyboard(not_subscribed)
        )
        return False
    return True

# --- База данных ---

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, 
            referred_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, 
            referred_id INTEGER UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
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

# --- API TMDB (Поиск) ---

async def search_movies(query: str) -> list:
    results, ids_seen = [], set()
    # Фикс Errno 111: принудительный IPv4, отключение прокси и SSL
    connector = aiohttp.TCPConnector(family=socket.AF_INET, verify_ssl=False)
    
    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
        for lang in ("ru-RU", "en-US"):
            try:
                params = {"api_key": TMDB_API_KEY, "query": query, "language": lang, "include_adult": "false"}
                async with session.get(f"{TMDB_BASE_URL}/search/multi", params=params, timeout=10) as resp:
                    if resp.status != 200: continue
                    data = await resp.json()
                    for item in data.get("results", []):
                        if item.get("media_type") in ("movie", "tv") and len(results) < 10:
                            mid = item["id"]
                            if mid not in ids_seen:
                                ids_seen.add(mid)
                                title = item.get("title") or item.get("name") or "Без названия"
                                date = item.get("release_date") or item.get("first_air_date") or ""
                                results.append({
                                    "id": mid, "title": title, "year": f" ({date[:4]})" if date else "",
                                    "media_type": item["media_type"], "vote": item.get("vote_average", 0)
                                })
            except Exception as e:
                logger.error(f"Network error: {e}")
    return results

async def get_movie_details(movie_id: int, media_type: str) -> dict:
    connector = aiohttp.TCPConnector(family=socket.AF_INET, verify_ssl=False)
    async with aiohttp.ClientSession(connector=connector, trust_env=False) as session:
        try:
            params = {"api_key": TMDB_API_KEY, "language": "ru-RU"}
            async with session.get(f"{TMDB_BASE_URL}/{media_type}/{movie_id}", params=params) as resp:
                if resp.status == 200: return await resp.json()
        except Exception as e:
            logger.error(f"Details error: {e}")
    return {}

# --- Текстовый блок и логика сообщений ---

def build_movie_text(d: dict, m_type: str) -> str:
    title = d.get("title") or d.get("name") or "Без названия"
    overview = d.get("overview") or "Описание отсутствует."
    vote = d.get("vote_average", 0)
    genres = ", ".join(g["name"] for g in d.get("genres", [])[:3])
    date = d.get("release_date") or d.get("first_air_date") or "Н/Д"
    
    text = (f"🎬 <b>{title}</b>\n\n"
            f"📅 <b>Год:</b> {date[:4]}\n"
            f"🎭 <b>Жанр:</b> {genres}\n"
            f"⭐ <b>Рейтинг:</b> {vote:.1f}/10\n\n"
            f"📝 <b>Описание:</b>\n{overview}")
    return text[:1024] # Ограничение Telegram для подписей

@dp.message(CommandStart())
async def start(m: Message):
    ref = int(m.text.split()[1].replace("ref_", "")) if len(m.text.split()) > 1 else None
    await register_user(m.from_user.id, m.from_user.username, m.from_user.full_name, ref)
    if await require_subscription(m):
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔍 Поиск фильма")]], resize_keyboard=True)
        await m.answer("👋 Привет! Напиши название фильма или нажми кнопку ниже.", reply_markup=kb)

@dp.callback_query(F.data == "check_sub")
async def check_cb(c: CallbackQuery):
    if not await check_subscriptions(c.from_user.id):
        await c.message.delete()
        await c.message.answer("✅ Подписка подтверждена! Что будем искать?")
    else:
        await c.answer("❌ Вы всё еще не подписаны!", show_alert=True)

@dp.message(F.text == "🔍 Поиск фильма")
async def search_btn(m: Message):
    await m.answer("🔎 Введите название фильма:")

@dp.message(F.text)
async def handle_search(m: Message):
    if not await require_subscription(m): return
    msg = await m.answer("🔄 Ищу...")
    res = await search_movies(m.text)
    if not res:
        await msg.edit_text("😔 Ничего не найдено.")
        return
    
    kb_list = []
    text = "<b>Результаты поиска:</b>\n\n"
    for i, item in enumerate(res, 1):
        text += f"{i}. {item['title']}{item['year']}\n"
        kb_list.append([InlineKeyboardButton(text=f"Смотреть {i}", callback_data=f"mv_{item['id']}_{item['media_type']}")])
    
    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("mv_"))
async def details_cb(c: CallbackQuery):
    _, mid, mtype = c.data.split("_")
    d = await get_movie_details(mid, mtype)
    if not d: return
    
    text = build_movie_text(d, mtype)
    q = urllib.parse.quote(f"{d.get('title') or d.get('name')} {d.get('release_date')[:4] if d.get('release_date') else ''} смотреть онлайн")
    url = f"https://www.google.com/search?q={q}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Смотреть онлайн", url=url)],
        [InlineKeyboardButton(text="🔍 Новый поиск", callback_data="new_search")]
    ])
    
    if d.get("poster_path"):
        await c.message.answer_photo(f"{TMDB_IMAGE_BASE}{d['poster_path']}", caption=text, reply_markup=kb)
    else:
        await c.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "new_search")
async def new_search_cb(c: CallbackQuery):
    await c.message.answer("🔎 Введите название:")

async def main():
    await init_db()
    await bot.set_my_commands([BotCommand(command="start", description="Запуск"), BotCommand(command="search", description="Поиск")])
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
