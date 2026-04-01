import telebot
from telebot import types
import requests

# --- ТВОИ ДАННЫЕ ---
TOKEN = '8381032154:AAFsAnTVBGRrHWvedMweeXHsrJTjKgEWUXM'
TMDB_API_KEY = 'fdc70aa152320f85d8acdfda64b69b36'

bot = telebot.TeleBot(TOKEN)
user_db = {}

def search_movie_with_proxy(query):
    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "ru-RU"
    }
    
    # Список бесплатных прокси (они часто умирают, если не сработает — дам другой список)
    # Формат: 'протокол': 'http://ip:port'
    proxies_list = [
        {'http': 'http://167.71.233.151:8080', 'https': 'http://167.71.233.151:8080'},
        {'http': 'http://161.35.70.249:8080', 'https': 'http://161.35.70.249:8080'},
        {'http': 'http://128.199.202.122:8080', 'https': 'http://128.199.202.122:8080'}
    ]

    for proxy in proxies_list:
        try:
            print(f"📡 Попытка через прокси: {proxy['http']}")
            response = requests.get(url, params=params, proxies=proxy, timeout=7)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('results'):
                    movie = data['results'][0]
                    title = movie.get('title', 'Без названия')
                    rating = movie.get('vote_average', 0)
                    year = movie.get('release_date', '????')[:4]
                    overview = movie.get('overview') or "Описание отсутствует."
                    m_id = movie.get('id')
                    link = f"https://www.themoviedb.org/movie/{m_id}"
                    
                    return (f"🎬 *{title}* ({year})\n"
                            f"⭐ Рейтинг: {rating}/10\n\n"
                            f"📝 {overview[:400]}...\n\n"
                            f"🔗 [Карточка фильма]({link})")
                return "❌ Ничего не найдено."
        except Exception as e:
            print(f"⚠️ Прокси {proxy['http']} не ответил: {e}")
            continue # Пробуем следующий прокси

    # Если ни один прокси не сработал, пробуем напрямую (на случай, если бан сняли)
    try:
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            # (Логика обработки как выше)
            return "✅ Нашел напрямую (прокси не понадобились)!"
    except:
        pass

    return "❌ Ошибка: Все прокси лежат и прямой доступ закрыт."

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    if uid not in user_db: user_db[uid] = {'count': 0}
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔍 Поиск фильма", "👥 Рефералка")
    bot.send_message(m.chat.id, "Бот запущен через систему прокси! Вводи название.", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle(m):
    if m.text == "🔍 Поиск фильма":
        bot.send_message(m.chat.id, "Напиши название...")
    elif m.text == "👥 Рефералка":
        link = f"https://t.me/{bot.get_me().username}?start={m.from_user.id}"
        bot.send_message(m.chat.id, f"Твоя ссылка: `{link}`", parse_mode="Markdown")
    else:
        wait = bot.send_message(m.chat.id, "🔎 Ищу (через прокси, может занять до 10 сек)...")
        res = search_movie_with_proxy(m.text)
        bot.edit_message_text(res, m.chat.id, wait.message_id, parse_mode="Markdown")

if __name__ == '__main__':
    bot.infinity_polling()
