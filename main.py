import telebot
from telebot import types
import os
import requests

# Конфигурация токенов
TOKEN = '8381032154:AAEQdqCbxcGOuzunPWhPZbXaCjzaPpJbuhM'
TMDB_API_KEY = 'Fdc70aa152320f85d8acdfda64b69b36'

bot = telebot.TeleBot(TOKEN)

# Реферальная система (хранение в памяти)
# В продакшене лучше использовать БД, но для текущих задач Amvera этого хватит
user_db = {} # {user_id: {'count': 0, 'name': 'Имя', 'invited_by': None}}

# --- ФУНКЦИЯ ПОИСКА TMDB ---
def get_movie_details(query):
    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "ru-RU",
        "page": 1
    }
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if data.get('results'):
            movie = data['results'][0]
            title = movie.get('title', 'Без названия')
            rating = movie.get('vote_average', 0)
            date = movie.get('release_date', '????')[:4]
            overview = movie.get('overview', 'Описание на русском языке пока отсутствует.')
            m_id = movie.get('id')
            link = f"https://www.themoviedb.org/movie/{m_id}"
            
            text = (
                f"🎬 **{title}** ({date})\n"
                f"⭐ Рейтинг: {rating}/10\n\n"
                f"📝 **Описание:**\n{overview[:600]}...\n\n"
                f"🔗 [Смотреть инфо о фильме]({link})"
            )
            return text
    except Exception as e:
        print(f"Ошибка API: {e}")
    return None

# --- КЛАВИАТУРА ---
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🔍 Поиск фильма"), types.KeyboardButton("👥 Моя ссылка"))
    markup.add(types.KeyboardButton("📊 Моя статистика"))
    return markup

# --- КОМАНДА /START + РЕФЕРАЛКА ---
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if user_id not in user_db:
        user_db[user_id] = {'count': 0, 'name': user_name, 'invited_by': None}
        
        # Проверка реферального хвоста: /start 12345
        args = message.text.split()
        if len(args) > 1 and args[1].isdigit():
            referrer_id = int(args[1])
            if referrer_id in user_db and referrer_id != user_id:
                user_db[user_id]['invited_by'] = referrer_id
                user_db[referrer_id]['count'] += 1
                bot.send_message(referrer_id, f"💎 Новый реферал! {user_name} зашел по твоей ссылке.")

    bot.send_message(
        message.chat.id, 
        f"🍿 Привет, {user_name}! Я бот с безграничной базой фильмов.\n\n"
        "Напиши название любого фильма, и я его найду!",
        reply_markup=main_keyboard()
    )

# --- ОБРАБОТКА КНОПОК ---
@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    uid = message.from_user.id

    if message.text == "🔍 Поиск фильма":
        bot.send_message(message.chat.id, "Просто отправь мне название фильма текстом 👇")
    
    elif message.text == "👥 Моя ссылка":
        bot_user = bot.get_me().username
        link = f"https://t.me/{bot_user}?start={uid}"
        bot.send_message(message.chat.id, f"🔗 Твоя ссылка для приглашений:\n`{link}`", parse_mode="Markdown")
    
    elif message.text == "📊 Моя статистика":
        count = user_db.get(uid, {}).get('count', 0)
        bot.send_message(message.chat.id, f"👤 Имя: {user_db[uid]['name']}\n👥 Приглашено друзей: {count}")

    else:
        # Если это не кнопка, значит это поисковый запрос
        wait_msg = bot.send_message(message.chat.id, "Ищу в базе TMDB... 🔎")
        movie_info = get_movie_details(message.text)
        
        if movie_info:
            bot.edit_message_text(movie_info, message.chat.id, wait_msg.message_id, parse_mode="Markdown", disable_web_page_preview=False)
        else:
            bot.edit_message_text("❌ Ничего не найдено. Попробуй другое название.", message.chat.id, wait_msg.message_id)

if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
