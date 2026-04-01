import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from tmdbv3api import TMDb, Movie

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8381032154:AAEQdqCbxcGOuzunPWhPZbXaCjzaPpJbuhM'
TMDB_API_KEY = 'fdc70aa152320f85d8acdfda64b69b36'
ADMIN_ID = 5298604296

# Каналы для подписки (Бот должен быть там админом!)
CHANNELS = [
    {"user_id": "@lyubimkatt", "link": "https://t.me/lyubimkatt"},
    {"user_id": "@kinoo_rum", "link": "https://t.me/kinoo_rum"}
]

# Настройка TMDB (Поиск фильмов)
tmdb = TMDb()
tmdb.api_key = TMDB_API_KEY
tmdb.language = 'ru'
movie_search = Movie()

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

async def check_sub(user_id):
    """Проверка, подписан ли пользователь на каналы"""
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["user_id"], user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            return False
    return True

@dp.message(Command("start"))
async def start(message: types.Message):
    # Логика рефералки (простой лог в консоль)
    args = message.text.split()
    if len(args) > 1:
        logging.info(f"Реферал: {message.from_user.id} пришел от {args[1]}")

    if not await check_sub(message.from_user.id):
        builder = InlineKeyboardBuilder()
        for ch in CHANNELS:
            builder.row(types.InlineKeyboardButton(text="Подписаться", url=ch["link"]))
        builder.row(types.InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub"))
        
        await message.answer(
            "🍿 Привет! Чтобы пользоваться ботом, подпишись на наши каналы:",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer("✅ Доступ открыт! Напиши название фильма (например: 'Интерстеллар')")

@dp.callback_query(F.data == "check_sub")
async def callback_check(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.edit_text("✅ Подписка подтверждена! Какой фильм ищем?")
    else:
        await callback.answer("❌ Ты подписался не на все каналы!", show_alert=True)

@dp.message(F.text.lower() == "панель")
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        me = await bot.get_me()
        ref_link = f"https://t.me/{me.username}?start={ADMIN_ID}"
        await message.answer(
            f"👑 **Админ-панель**\n\nТвоя ссылка для рекламы:\n`{ref_link}`",
            parse_mode="Markdown"
        )

@dp.message()
async def search_movie(message: types.Message):
    if not await check_sub(message.from_user.id):
        return await start(message)
    
    query = message.text
    search_results = movie_search.search(query)

    if search_results:
        movie = search_results[0]
        title = movie.title
        date = getattr(movie, 'release_date', '----')
        rating = getattr(movie, 'vote_average', 0)
        overview = movie.overview if movie.overview else "Описание отсутствует."
        poster = f"https://image.tmdb.org/t/p/w500{movie.poster_path}" if movie.poster_path else None

        text = (
            f"🎬 **{title}** ({date[:4]})\n\n"
            f"⭐️ **Рейтинг:** {rating}/10\n\n"
            f"📝 **Описание:** {overview[:450]}...\n"
        )
        
        builder = InlineKeyboardBuilder()
        # Ссылка на просмотр (твоя ссылка на канал или плеер)
        builder.row(types.InlineKeyboardButton(text="🍿 СМОТРЕТЬ ФИЛЬМ", url="https://t.me/kinoo_rum"))

        if poster:
            await message.answer_photo(poster, caption=text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        else:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        await message.answer("❌ Фильм не найден. Попробуй другое название.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
