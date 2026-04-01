import telebot
from telebot import types
import os

# Берем токен из Секретов (рекомендую) или вставляем напрямую
TOKEN = os.getenv("BOT_TOKEN") or "8381032154:AAEQdqCbxcGOuzunPWhPZbXaCjzaPpJbuhM"
bot = telebot.TeleBot(TOKEN)

# --- ИМИТАЦИЯ БАЗЫ ДАННЫХ ФИЛЬМОВ ---
FILMS_DB = [
    {
        "name": "Интерстеллар",
        "desc": "Группа исследователей отправляется в путешествие сквозь черную дыру.",
        "rating": "⭐ 8.6",
        "url": "https://www.kinopoisk.ru/film/447301/"
    },
    {
        "name": "Один дома",
        "desc": "Мальчик остается один дома на Рождество и сражается с грабителями.",
        "rating": "⭐ 8.3",
        "url": "https://www.kinopoisk.ru/film/8124/"
    }
]

# --- РЕФЕРАЛЬНАЯ СИСТЕМА (в памяти) ---
user_data = {} # {user_id: {'referrals': 0, 'invited_by': None}}

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔍 Поиск фильма", "🎁 Реферальная программа")
    markup.add("📜 Весь список")
    return markup

# --- ОБРАБОТКА /START ---
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    # Реферальная логика
    if user_id not in user_data:
        user_data[user_id] = {'referrals': 0, 'invited_by': None}
        
        # Проверяем, пришел ли по ссылке (/start 12345)
        args = message.text.split()
        if len(args) > 1:
            referrer_id = int(args[1])
            if referrer_id != user_id and referrer_id in user_data:
                user_data[user_id]['invited_by'] = referrer_id
                user_data[referrer_id]['referrals'] += 1
                bot.send_message(referrer_id, "🔔 По вашей ссылке зарегистрировался новый пользователь!")

    bot.send_message(
        message.chat.id, 
        f"🎬 Добро пожаловать! Я бот проекта **bot-kino-2**.\n\nИщи фильмы, смотри рейтинги и приглашай друзей!",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# --- РЕФЕРАЛЬНЫЙ КАБИНЕТ ---
@bot.message_handler(func=lambda m: m.text == "🎁 Реферальная программа")
def ref_system(message):
    user_id = message.from_user.id
    count = user_data.get(user_id, {}).get('referrals', 0)
    ref_link = f"https://t.me/{(bot.get_me()).username}?start={user_id}"
    
    text = (
        f"👥 **Ваша реферальная система**\n\n"
        f"Приглашено друзей: `{count}`\n"
        f"Ваша ссылка для приглашения:\n`{ref_link}`"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- ПОИСК И СПИСОК ---
@bot.message_handler(func=lambda m: m.text == "📜 Весь список")
def list_all(message):
    response = "🎬 **Доступные фильмы:**\n\n"
    for f in FILMS_DB:
        response += f"• {f['name']} ({f['rating']})\ /start_search\n"
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔍 Поиск фильма")
def search_instruction(message):
    bot.send_message(message.chat.id, "Просто напиши название фильма мне в чат 👇")

# --- ЛОГИКА ПОИСКА ПО ТЕКСТУ ---
@bot.message_handler(content_types=['text'])
def find_film(message):
    query = message.text.lower().strip()
    results = [f for f in FILMS_DB if query in f['name'].lower()]

    if results:
        for f in results:
            text = (
                f"🎬 **{f['name']}**\n"
                f"📊 Рейтинг: {f['rating']}\n\n"
                f"📝 Описание: {f['desc']}\n\n"
                f"🔗 [Смотреть фильм]({f['url']})"
            )
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Ничего не найдено. Проверь название или загляни в 'Весь список'.")

if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
