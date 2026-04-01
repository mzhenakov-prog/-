import telebot
from telebot import types
import requests

# ТВОИ ОБНОВЛЕННЫЕ ДАННЫЕ
TOKEN = '8381032154:AAFsAnTVBGRrHWvedMweeXHsrJTjKgEWUXM'
TMDB_API_KEY = 'fdc70aa152320f85d8acdfda64b69b36'

bot = telebot.TeleBot(TOKEN)

# База данных в оперативной памяти (сбросится при перезапуске сервера)
user_db = {} 

def search_movie_tmdb(query):
    """Поиск по безграничной базе TMDB"""
    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "ru-RU"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get('results'):
            # Берем самый первый (релевантный) результат
            movie = data['results'][0]
            title = movie.get('title', 'Без названия')
            rating = movie.get('vote_average', 0)
            year = movie.get('release_date', '????')[:4]
            overview = movie.get('overview', 'Описание на русском языке отсутствует.')
            m_id = movie.get('id')
            
            # Ссылка на карточку фильма
            link = f"https://www.themoviedb.org/movie/{m_id}"
            
            return (f"🎬 *{title}* ({year})\n"
                    f"⭐ Рейтинг: {rating}/10\n\n"
                    f"📝 *Описание:*\n{overview[:500]}...\n\n"
                    f"🔗 [Подробнее и просмотр здесь]({link})")
    except Exception as e:
        print(f"Ошибка API: {e}")
    return None

# ГЛАВНОЕ МЕНЮ
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔍 Поиск фильма", "👥 Моя ссылка")
    markup.add("📊 Моя статистика")
    return markup

# КОМАНДА /START + РЕФЕРАЛКА
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    name = message.from_user.first_name
    
    if uid not in user_db:
        user_db[uid] = {'count': 0, 'name': name}
        
        # Обработка реферального кода
        args = message.text.split()
        if len(args) > 1 and args[1].isdigit():
            ref_id = int(args[1])
            if ref_id in user_db and ref_id != uid:
                user_db[ref_id]['count'] += 1
                try:
                    bot.send_message(ref_id, f"💎 Ура! По твоей ссылке зашел новый пользователь: {name}")
                except:
                    pass

    bot.send_message(
        message.chat.id, 
        f"🍿 Привет, {name}! Напиши название любого фильма, и я его найду.",
        reply_markup=get_main_menu()
    )

# ЛОГИКА КНОПОК И ПОИСКА
@bot.message_handler(func=lambda m: True)
def handle_all(message):
    uid = message.from_user.id
    
    if message.text == "🔍 Поиск фильма":
        bot.send_message(message.chat.id, "Просто напиши мне название фильма (например: Брат или Начало) 👇")
    
    elif message.text == "👥 Моя ссылка":
        bot_user = bot.get_me().username
        ref_link = f"https://t.me/{bot_user}?start={uid}"
        bot.send_message(message.chat.id, f"🔗 Твоя ссылка для приглашения друзей:\n\n`{ref_link}`", parse_mode="Markdown")
    
    elif message.text == "📊 Моя статистика":
        # Защита на случай, если юзера нет в базе
        if uid not in user_db: user_db[uid] = {'count': 0, 'name': message.from_user.first_name}
        count = user_db[uid]['count']
        bot.send_message(message.chat.id, f"👤 Имя: {user_db[uid]['name']}\n👥 Приглашено друзей: {count}")
    
    else:
        # Если это не кнопка, значит это запрос на поиск фильма
        status_msg = bot.send_message(message.chat.id, "🔎 Ищу в базе данных...")
        movie_data = search_movie_tmdb(message.text)
        
        if movie_data:
            bot.edit_message_text(movie_data, message.chat.id, status_msg.message_id, parse_mode="Markdown", disable_web_page_preview=False)
        else:
            bot.edit_message_text("❌ К сожалению, ничего не найдено. Попробуй уточнить название.", message.chat.id, status_msg.message_id)

# ЗАПУСК
if __name__ == '__main__':
    print("Бот успешно запущен на новом токене!")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
