import asyncio
import logging
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
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
BOT_TOKEN = "8381032154:AAFsAnTVBGRrHWvedMweeXHsrJTjKgEWUXM"
TMDB_API_KEY = "fdc70aa152320f85d8acdfda64b69b36"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
DB_PATH = "bot_database.db"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
class SearchState(StatesGroup):
    waiting_for_query = State()
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                referred_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(referred_id)
            )
        """)
        await db.commit()
async def register_user(user_id: int, username: str, full_name: str, referred_by: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            existing = await cursor.fetchone()
        if not existing:
            await db.execute(
                "INSERT INTO users (user_id, username, full_name, referred_by) VALUES (?, ?, ?, ?)",
                (user_id, username, full_name, referred_by)
            )
            if referred_by and referred_by != user_id:
                try:
                    await db.execute(
                        "INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                        (referred_by, user_id)
                    )
                except Exception:
                    pass
            await db.commit()
            return True
        return False
async def get_referral_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
async def search_movies(query: str) -> list:
    results = []
    async with aiohttp.ClientSession() as session:
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "ru-RU",
            "include_adult": "false",
            "page": "1",
        }
        async with session.get(f"{TMDB_BASE_URL}/search/multi", params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                items = data.get("results", [])
                for item in items:
                    media_type = item.get("media_type", "")
                    if media_type in ("movie", "tv"):
                        title = item.get("title") or item.get("name") or "Без названия"
                        year = ""
                        date_str = item.get("release_date") or item.get("first_air_date") or ""
                        if date_str and len(date_str) >= 4:
                            year = f" ({date_str[:4]})"
                        results.append({
                            "id": item.get("id"),
                            "title": title,
                            "year": year,
                            "media_type": media_type,
                            "overview": item.get("overview", ""),
                            "vote_average": item.get("vote_average", 0),
                            "poster_path": item.get("poster_path"),
                        })
                    if len(results) >= 10:
                        break
    if len(results) < 10:
        params2 = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "en-US",
            "include_adult": "false",
            "page": "1",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{TMDB_BASE_URL}/search/multi", params=params2) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("results", [])
                    existing_ids = {r["id"] for r in results}
                    for item in items:
                        media_type = item.get("media_type", "")
                        if media_type in ("movie", "tv") and item.get("id") not in existing_ids:
                            title = item.get("title") or item.get("name") or "No title"
                            year = ""
                            date_str = item.get("release_date") or item.get("first_air_date") or ""
                            if date_str and len(date_str) >= 4:
                                year = f" ({date_str[:4]})"
                            results.append({
                                "id": item.get("id"),
                                "title": title,
                                "year": year,
                                "media_type": media_type,
                                "overview": item.get("overview", ""),
                                "vote_average": item.get("vote_average", 0),
                                "poster_path": item.get("poster_path"),
                            })
                            existing_ids.add(item.get("id"))
                        if len(results) >= 10:
                            break
    return results
async def get_movie_details(movie_id: int, media_type: str) -> dict:
    endpoint = "movie" if media_type == "movie" else "tv"
    async with aiohttp.ClientSession() as session:
        params = {"api_key": TMDB_API_KEY, "language": "ru-RU"}
        async with session.get(f"{TMDB_BASE_URL}/{endpoint}/{movie_id}", params=params) as resp:
            if resp.status == 200:
                return await resp.json()
    return {}
def get_main_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Поиск фильма")],
            [KeyboardButton(text="👥 Рефералы")],
        ],
        resize_keyboard=True,
        persistent=True,
    )
    return keyboard
def stars_rating(rating: float) -> str:
    filled = int(round(rating / 2))
    filled = max(0, min(5, filled))
    return "⭐" * filled + "☆" * (5 - filled)
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = message.from_user
    referred_by = None
    args = message.text.strip().split()
    if len(args) > 1:
        try:
            referred_by = int(args[1].replace("ref_", ""))
        except (ValueError, IndexError):
            referred_by = None
    is_new = await register_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        referred_by=referred_by,
    )
    await state.clear()
    welcome_text = (
        f"🎬 <b>Привет, {user.first_name}!</b>\n\n"
        "Добро пожаловать в <b>CineBot</b> — твой персональный помощник по поиску фильмов и сериалов!\n\n"
        "🔍 <b>Что умею:</b>\n"
        "• Искать фильмы и сериалы по названию\n"
        "• Показывать описание, рейтинг и постер\n"
        "• Давать ссылку для просмотра онлайн\n"
        "• Реферальная система — приглашай друзей!\n\n"
        "Нажми <b>«🔍 Поиск фильма»</b>, чтобы начать."
    )
    if is_new and referred_by:
        welcome_text += "\n\n🎁 <i>Вы пришли по реферальной ссылке!</i>"
    await message.answer(welcome_text, reply_markup=get_main_keyboard())
@dp.message(F.text == "🔍 Поиск фильма")
@dp.message(Command("search"))
async def start_search(message: Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_query)
    await message.answer(
        "🔍 <b>Введите название фильма или сериала:</b>\n\n"
        "<i>Например: Дюна, Интерстеллар, Игра престолов...</i>",
    )
@dp.message(SearchState.waiting_for_query)
async def handle_search_query(message: Message, state: FSMContext):
    query = message.text.strip()
    if not query:
        await message.answer("Пожалуйста, введите название фильма.")
        return
    await state.clear()
    searching_msg = await message.answer("🔄 <b>Ищу фильмы...</b>")
    results = await search_movies(query)
    if not results:
        await searching_msg.edit_text(
            "😔 <b>Ничего не найдено.</b>\n\n"
            "Попробуйте другое название или проверьте правописание.\n"
            "Нажмите <b>«🔍 Поиск фильма»</b>, чтобы попробовать снова."
        )
        return
    text = f"🎬 <b>Результаты поиска по запросу «{query}»:</b>\n\n"
    for i, movie in enumerate(results, 1):
        type_icon = "🎬" if movie["media_type"] == "movie" else "📺"
        rating = f"⭐ {movie['vote_average']:.1f}" if movie["vote_average"] else ""
        text += f"{i}. {type_icon} <b>{movie['title']}</b>{movie['year']} {rating}\n"
    text += "\n<i>Выберите фильм из списка:</i>"
    buttons = []
    row = []
    for i, movie in enumerate(results, 1):
        btn = InlineKeyboardButton(
            text=str(i),
            callback_data=f"movie_{movie['id']}_{movie['media_type']}"
        )
        row.append(btn)
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await searching_msg.edit_text(text, reply_markup=keyboard)
@dp.callback_query(F.data.startswith("movie_"))
async def show_movie_details(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    movie_id = int(parts[1])
    media_type = parts[2]
    loading_msg = await callback.message.answer("⏳ <b>Загружаю информацию о фильме...</b>")
    details = await get_movie_details(movie_id, media_type)
    if not details:
        await loading_msg.edit_text("❌ Не удалось загрузить информацию о фильме. Попробуйте позже.")
        return
    title = details.get("title") or details.get("name") or "Без названия"
    original_title = details.get("original_title") or details.get("original_name") or ""
    overview = details.get("overview") or "Описание недоступно."
    vote_avg = details.get("vote_average", 0)
    vote_count = details.get("vote_count", 0)
    date_str = details.get("release_date") or details.get("first_air_date") or ""
    year = date_str[:4] if date_str and len(date_str) >= 4 else "Н/Д"
    poster_path = details.get("poster_path")
    genres_list = details.get("genres", [])
    genres = ", ".join(g["name"] for g in genres_list[:4]) if genres_list else "Н/Д"
    if media_type == "movie":
        runtime = details.get("runtime")
        duration_str = f"⏱ <b>Длительность:</b> {runtime} мин.\n" if runtime else ""
    else:
        seasons = details.get("number_of_seasons")
        episodes = details.get("number_of_episodes")
        duration_str = ""
        if seasons:
            duration_str = f"📺 <b>Сезонов:</b> {seasons}"
            if episodes:
                duration_str += f" ({episodes} эп.)"
            duration_str += "\n"
    if overview and len(overview) > 800:
        overview = overview[:800] + "..."
    stars = stars_rating(vote_avg)
    rating_str = f"{stars} <b>{vote_avg:.1f}/10</b> ({vote_count:,} голосов)" if vote_count else "Нет рейтинга"
    text = f"🎬 <b>{title}</b>\n"
    if original_title and original_title != title:
        text += f"<i>{original_title}</i>\n"
    text += (
        f"\n📅 <b>Год:</b> {year}\n"
        f"🎭 <b>Жанр:</b> {genres}\n"
        f"{duration_str}"
        f"⭐ <b>Рейтинг:</b> {rating_str}\n\n"
        f"📝 <b>Описание:</b>\n{overview}"
    )
    import urllib.parse
    encoded_query = urllib.parse.quote(f"{title} {year} смотреть онлайн бесплатно")
    watch_url = f"https://www.google.com/search?q={encoded_query}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Смотреть фильм", url=watch_url)],
        [InlineKeyboardButton(text="🔍 Новый поиск", callback_data="new_search")],
    ])
    poster_url = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None
    await loading_msg.delete()
    if poster_url:
        try:
            await callback.message.answer_photo(photo=poster_url, caption=text, reply_markup=keyboard)
        except Exception:
            await callback.message.answer(text, reply_markup=keyboard)
    else:
        await callback.message.answer(text, reply_markup=keyboard)
@dp.callback_query(F.data == "new_search")
async def callback_new_search(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SearchState.waiting_for_query)
    await callback.message.answer(
        "🔍 <b>Введите название фильма или сериала:</b>\n\n"
        "<i>Например: Дюна, Интерстеллар, Игра престолов...</i>",
    )
@dp.message(F.text == "👥 Рефералы")
@dp.message(Command("referrals"))
async def show_referrals(message: Message):
    user = message.from_user
    await register_user(user.id, user.username or "", user.full_name or "")
    ref_count = await get_referral_count(user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n<code>{ref_link}</code>\n\n"
        f"👤 <b>Приглашено пользователей:</b> {ref_count}\n\n"
        "📌 <b>Как это работает?</b>\n"
        "Поделитесь своей ссылкой с друзьями.\n"
        "Когда они запустят бота по вашей ссылке — они будут засчитаны как ваши рефералы.\n\n"
        "<i>Нажмите на ссылку выше, чтобы скопировать её.</i>"
    )
    share_btn = InlineKeyboardButton(
        text="📤 Поделиться ссылкой",
        url=f"https://t.me/share/url?url={ref_link}&text=Смотри%20фильмы%20и%20сериалы%20с%20этим%20ботом!",
    )
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[share_btn]]))
@dp.message()
async def handle_unknown(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == SearchState.waiting_for_query:
        await handle_search_query(message, state)
    else:
        await message.answer("Воспользуйтесь кнопками меню ниже 👇", reply_markup=get_main_keyboard())
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="search", description="Найти фильм"),
        BotCommand(command="referrals", description="Реферальная программа"),
    ])
async def main():
    await init_db()
    await set_commands()
    logger.info("Bot started successfully!")
    await dp.start_polling(bot, skip_updates=True)
if __name__ == "__main__":
    asyncio.run(main())
