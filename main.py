import asyncio
import logging
import urllib.parse
import aiosqlite
import aiohttp
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
async def check_subscriptions(user_id: int) -> list:
    not_subscribed = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status in ("left", "kicked"):
                not_subscribed.append(channel)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        except Exception as e:
            logger.error(f"Check subscription error: {e}")
    return not_subscribed
def subscription_keyboard(not_subscribed: list) -> InlineKeyboardMarkup:
    buttons = []
    for ch in not_subscribed:
        buttons.append([InlineKeyboardButton(text=f"👉 Подписаться на {ch['name']}", url=ch["url"])])
    buttons.append([InlineKeyboardButton(text="✅ Я подписался — проверить", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
async def require_subscription(message: Message) -> bool:
    not_subscribed = await check_subscriptions(message.from_user.id)
    if not_subscribed:
        text = "🔒 <b>Для использования бота подпишитесь на наши каналы:</b>\n\n"
        for ch in not_subscribed:
            text += f"• {ch['name']} — {ch['url']}\n"
        text += "\nПосле подписки нажмите кнопку ниже 👇"
        await message.answer(text, reply_markup=subscription_keyboard(not_subscribed))
        return False
    return True
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT,
                full_name TEXT, referred_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL, referred_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(referred_id)
            )
        """)
        await db.commit()
async def register_user(user_id, username, full_name, referred_by=None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            if await cur.fetchone():
                return False
        await db.execute(
            "INSERT INTO users (user_id, username, full_name, referred_by) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, referred_by)
        )
        if referred_by and referred_by != user_id:
            await db.execute(
                "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                (referred_by, user_id)
            )
        await db.commit()
    return True
async def get_referral_count(user_id) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0
async def get_referral_list(user_id) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT u.full_name, u.username, r.created_at FROM referrals r
               JOIN users u ON u.user_id = r.referred_id
               WHERE r.referrer_id = ? ORDER BY r.created_at DESC LIMIT 20""",
            (user_id,)
        ) as cur:
            return await cur.fetchall()
async def get_total_users() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
    return row[0] if row else 0
async def search_movies(query: str) -> list:
    results, ids_seen = [], set()
    for lang in ("ru-RU", "en-US"):
        if len(results) >= 10:
            break
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{TMDB_BASE_URL}/search/multi",
                    params={"api_key": TMDB_API_KEY, "query": query,
                            "language": lang, "include_adult": "false", "page": "1"}
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            for item in data.get("results", []):
                if len(results) >= 10:
                    break
                media_type = item.get("media_type", "")
                if media_type not in ("movie", "tv"):
                    continue
                item_id = item.get("id")
                if item_id in ids_seen:
                    continue
                ids_seen.add(item_id)
                title = item.get("title") or item.get("name") or "Без названия"
                date_str = item.get("release_date") or item.get("first_air_date") or ""
                year = f" ({date_str[:4]})" if len(date_str) >= 4 else ""
                results.append({"id": item_id, "title": title, "year": year,
                                 "media_type": media_type, "vote_average": item.get("vote_average", 0)})
        except Exception as e:
            logger.error(f"Search error: {e}")
    return results
async def get_movie_details(movie_id: int, media_type: str) -> dict:
    endpoint = "movie" if media_type == "movie" else "tv"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TMDB_BASE_URL}/{endpoint}/{movie_id}",
                params={"api_key": TMDB_API_KEY, "language": "ru-RU"}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        logger.error(f"Details error: {e}")
    return {}
def stars_rating(rating: float) -> str:
    filled = max(0, min(5, int(round(rating / 2))))
    return "⭐" * filled + "☆" * (5 - filled)
def build_movie_text(details: dict, media_type: str) -> str:
    title = details.get("title") or details.get("name") or "Без названия"
    original = details.get("original_title") or details.get("original_name") or ""
    overview = details.get("overview") or "Описание недоступно."
    vote_avg = details.get("vote_average", 0)
    vote_count = details.get("vote_count", 0)
    date_str = details.get("release_date") or details.get("first_air_date") or ""
    year = date_str[:4] if len(date_str) >= 4 else "Н/Д"
    genres = ", ".join(g["name"] for g in details.get("genres", [])[:4]) or "Н/Д"
    if media_type == "movie":
        rt = details.get("runtime")
        dur = f"⏱ <b>Длительность:</b> {rt} мин.\n" if rt else ""
    else:
        s, e = details.get("number_of_seasons"), details.get("number_of_episodes")
        dur = (f"📺 <b>Сезонов:</b> {s}" + (f" ({e} эп.)" if e else "") + "\n") if s else ""
    rating_str = f"{stars_rating(vote_avg)} <b>{vote_avg:.1f}/10</b> ({vote_count:,} гол.)" if vote_count else "Нет рейтинга"
    text = f"🎬 <b>{title}</b>\n"
    if original and original != title:
        text += f"<i>{original}</i>\n"
    text += f"\n📅 <b>Год:</b> {year}\n🎭 <b>Жанр:</b> {genres}\n{dur}⭐ <b>Рейтинг:</b> {rating_str}\n\n📝 <b>Описание:</b>\n{overview}"
    return text
def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    kb = [[KeyboardButton(text="🔍 Поиск фильма")]]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="👥 Рефералы")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, persistent=True)
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    referred_by = None
    args = message.text.strip().split()
    if len(args) > 1:
        try:
            referred_by = int(args[1].replace("ref_", ""))
        except ValueError:
            pass
    is_new = await register_user(user.id, user.username or "", user.full_name or "", referred_by)
    if user.id != ADMIN_ID:
        not_sub = await check_subscriptions(user.id)
        if not_sub:
            text = f"👋 <b>Привет, {user.first_name}!</b>\n\nДля использования бота подпишитесь на наши каналы:\n\n"
            for ch in not_sub:
                text += f"• {ch['name']} — {ch['url']}\n"
            text += "\nПосле подписки нажмите кнопку ниже 👇"
            await message.answer(text, reply_markup=subscription_keyboard(not_sub))
            return
    text = f"🎬 <b>Привет, {user.first_name}!</b>\n\nДобро пожаловать в <b>CineBot</b>!\nНапишите название фильма — найду сразу 🔍"
    if is_new and referred_by:
        text += "\n\n🎁 <i>Вы пришли по реферальной ссылке!</i>"
    await message.answer(text, reply_markup=main_keyboard(user.id))
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    await callback.answer()
    not_sub = await check_subscriptions(callback.from_user.id)
    if not_sub:
        text = "❌ <b>Вы ещё не подписались на все каналы:</b>\n\n"
        for ch in not_sub:
            text += f"• {ch['name']} — {ch['url']}\n"
        text += "\nПодпишитесь и нажмите кнопку снова 👇"
        await callback.message.edit_text(text, reply_markup=subscription_keyboard(not_sub))
    else:
        await callback.message.delete()
        await callback.message.answer(
            "✅ <b>Отлично! Теперь можете пользоваться ботом.</b>\n\nНапишите название фильма 🎬",
            reply_markup=main_keyboard(callback.from_user.id)
        )
@dp.message(F.text == "👥 Рефералы")
@dp.message(Command("referrals"))
async def show_referrals(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return
    count = await get_referral_count(ADMIN_ID)
    ref_list = await get_referral_list(ADMIN_ID)
    total = await get_total_users()
    info = await bot.get_me()
    link = f"https://t.me/{info.username}?start=ref_{ADMIN_ID}"
    text = (
        "👥 <b>Реферальная панель</b>\n\n"
        f"🔗 <b>Ваша ссылка:</b>\n<code>{link}</code>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Всего пользователей: <b>{total}</b>\n"
        f"• По реф. ссылке: <b>{count}</b>\n"
    )
    if ref_list:
        text += "\n<b>Последние рефералы:</b>\n"
        for name, username, joined in ref_list:
            date = str(joined)[:10] if joined else ""
            display = f"@{username}" if username else name or "Пользователь"
            text += f"• {display} — {date}\n"
    else:
        text += "\n<i>Пока никто не перешёл по вашей ссылке.</i>"
    buttons = [
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={link}&text=Ищи%20фильмы%20бесплатно!")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_refs")],
    ]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
@dp.callback_query(F.data == "refresh_refs")
async def refresh_refs(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer("Обновлено!")
    await show_referrals(callback.message)
@dp.message(F.text)
async def handle_text(message: Message):
    if message.from_user.id != ADMIN_ID:
        if not await require_subscription(message):
            return
    query = message.text.strip()
    loading = await message.answer("🔄 <b>Ищу...</b>")
    results = await search_movies(query)
    if not results:
        await loading.edit_text("😔 <b>Ничего не найдено.</b>\n\nПопробуйте другое название.")
        return
    text = f"🎬 <b>Результаты по запросу «{query}»:</b>\n\n"
    for i, m in enumerate(results, 1):
        icon = "🎬" if m["media_type"] == "movie" else "📺"
        rating = f" ⭐{m['vote_average']:.1f}" if m["vote_average"] else ""
        text += f"{i}. {icon} <b>{m['title']}</b>{m['year']}{rating}\n"
    text += "\n<i>Нажмите на номер фильма:</i>"
    buttons, row = [], []
    for i, m in enumerate(results, 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"mv_{m['id']}_{m['media_type']}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    await loading.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
@dp.callback_query(F.data.startswith("mv_"))
async def show_details(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    movie_id, media_type = int(parts[1]), parts[2]
    loading = await callback.message.answer("⏳ <b>Загружаю...</b>")
    details = await get_movie_details(movie_id, media_type)
    if not details:
        await loading.edit_text("❌ Не удалось загрузить. Попробуйте позже.")
        return
    text = build_movie_text(details, media_type)
    title = details.get("title") or details.get("name") or ""
    date_str = details.get("release_date") or details.get("first_air_date") or ""
    year = date_str[:4] if len(date_str) >= 4 else ""
    watch_url = "https://www.google.com/search?q=" + urllib.parse.quote(f"{title} {year} смотреть онлайн бесплатно")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Смотреть фильм", url=watch_url)],
        [InlineKeyboardButton(text="🔍 Новый поиск", callback_data="new_search")],
    ])
    poster_path = details.get("poster_path")
    await loading.delete()
    if poster_path:
        caption = text if len(text) <= 1020 else text[:1020] + "..."
        try:
            await callback.message.answer_photo(photo=f"{TMDB_IMAGE_BASE}{poster_path}", caption=caption, reply_markup=keyboard)
            return
        except Exception as e:
            logger.warning(f"Photo failed: {e}")
    await callback.message.answer(text[:4000], reply_markup=keyboard)
@dp.callback_query(F.data == "new_search")
async def new_search(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🔍 Введите название фильма или сериала:")
async def main():
    await init_db()
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="search", description="Найти фильм"),
    ])
    logger.info("Bot started!")
    await dp.start_polling(bot, skip_updates=True)
if __name__ == "__main__":
    asyncio.run(main())
