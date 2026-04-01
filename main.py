import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
API_TOKEN = '8381032154:AAEQdqCbxcGOuzunPWhPZbXaCjzaPpJbuhM'
TMDB_API_KEY = 'fdc70aa152320f85d8acdfda64b69b36'
ADMIN_ID = 5298604296

CHANNELS = [
    {"user_id": "@lyubimkatt", "link": "https://t.me/lyubimkatt"},
    {"user_id": "@kinoo_rum", "link": "https://t.me/kinoo_rum"}
]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

async def check_sub(user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel["user_id"], user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception:
            continue 
    return True

async def get_movie_data(query):
    """Прямой асинхронный запрос к TMDB"""
    url = f"https://api.themoviedb.org/3/search/movie"
    params = {
        'api_key': TMDB_API_KEY,
        'query': query,
        'language': 'ru'
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data['results']:
                        return data['results'][0]
        except Exception as e:
            logging.error(f"Ошибка сети: {e}")
    return None

@dp.message(Command("start"))
async def start(message: types.Message):
    if not await check_sub(message.from_user.id):
        builder = InlineKeyboardBuilder()
        for ch in CHANNELS:
            builder.row(types.InlineKeyboardButton(text="Подписаться", url=ch["link"]))
        builder.row(types.InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub"))
        await message.answer("🍿 Чтобы искать фильмы, подпишись на наши каналы:", reply_markup=builder.as_markup())
    else:
        await message.answer("🍿 Доступ открыт! Напиши название фильма.")

@dp.callback_query(F.data == "check_sub")
async def callback_check(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.edit_text("✅ Спасибо! Какой фильм ищем?")
    else:
        await callback.answer("❌ Вы не подписаны!", show_alert=True)

@dp.message(F.text.lower() == "панель")
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        me = await bot.get_me()
        await message.answer(f"👑 **Админ-панель**\n\nТвоя ссылка:\n`https://t.me/{me.username}?start={ADMIN_ID}`")

@dp.message()
async def search_movie(message: types.Message):
    if not await check_sub(message.from_user.id):
        return await start(message)
    
    movie = await get_movie_data(message.text)
    if movie:
        title = movie.get('title')
        date = movie.get('release_date', '----')
        rating = movie.get('vote_average', 0)
        overview = movie.get('overview', 'Описание отсутствует.')
        poster_path = movie.get('poster_path')
        
        text = f"🎬 **{title}** ({date[:4]})\n\n⭐️ **Рейтинг:** {rating}/10\n\n📝 **Описание:** {overview[:450]}..."
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(text="🍿 СМОТРЕТЬ ФИЛЬМ", url="https://t.me/kinoo_rum"))

        if poster_path:
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            await message.answer_photo(poster_url, caption=text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        else:
            await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        await message.answer("❌ Фильм не найден. Попробуй другое название.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
