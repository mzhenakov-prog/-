import telebot
import requests
import os

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = '8381032154:AAEQdqCbxcGOuzunPWhPZbXaCjzaPpJbuhM'
TMDB_API_KEY = 'fdc70aa152320f85d8acdfda64b69b36'

bot = telebot.TeleBot(BOT_TOKEN)
TMDB_URL = 'https://api.themoviedb.org/3'
IMAGE_URL = 'https://image.tmdb.org/t/p/w500'

# ========== ПОИСК ФИЛЬМА ==========
def search_movie(query):
    try:
        url = f"{TMDB_URL}/search/movie"
        params = {
            'api_key': TMDB_API_KEY,
            'query': query,
            'language': 'ru-RU',
            'page': 1
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        results = data.get('results', [])
        if not results:
            return None
        
        movie = results[0]
        return {
            'name': movie.get('title', 'Без названия'),
            'year': movie.get('release_date', '')[:4] if movie.get('release_date') else '—',
            'rating': movie.get('vote_average', 0),
            'description': movie.get('overview', 'Описание отсутствует'),
            'poster': f"{IMAGE_URL}{movie.get('poster_path')}" if movie.get('poster_path') else None
        }
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

def get_stars(rating):
    if rating <= 0:
        return "Нет рейтинга"
    stars = int((rating / 2) + 0.5)
    return '⭐' * stars

# ========== КОМАНДЫ ==========
@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🎬 *КИНО БОТ*\n\nВведи название фильма", parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def handle(m):
    wait = bot.send_message(m.chat.id, "🔎 *Ищу...*", parse_mode='Markdown')
    movie = search_movie(m.text)
    bot.delete_message(m.chat.id, wait.message_id)
    
    if not movie:
        bot.send_message(m.chat.id, "❌ Фильм не найден")
        return
    
    text = f"🎬 *{movie['name']}* ({movie['year']})\n"
    text += f"⭐ *Рейтинг:* {movie['rating']}/10 {get_stars(movie['rating'])}\n\n"
    text += f"📖 *Описание:*\n{movie['description'][:500]}"
    
    if movie['poster']:
        bot.send_photo(m.chat.id, movie['poster'], caption=text, parse_mode='Markdown')
    else:
        bot.send_message(m.chat.id, text, parse_mode='Markdown')

if __name__ == '__main__':
    print("Кино бот запущен!")
    bot.infinity_polling()
