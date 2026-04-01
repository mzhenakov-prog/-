import telebot
from telebot import types

# Твой токен вставлен
TOKEN = '8381032154:AAEQdqCbxcGOuzunPWhPZbXaCjzaPpJbuhM'
bot = telebot.TeleBot(TOKEN)

# Пример базы (сюда можно добавить свои ссылки и названия)
FILMS_DB = [
    {"name": "Интерстеллар", "url": "https://example.com/interstellar"},
    {"name": "Один дома", "url": "https://example.com/home-alone"},
    {"name": "Начало", "url": "https://example.com/inception"},
    {"name": "Джентльмены", "url": "https://example.com/gentlemen"},
]

# Функция для главного меню (кнопки)
def get_main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_search = types.InlineKeyboardButton("🔍 Найти фильм", callback_data="instruction_search")
    btn_list = types.InlineKeyboardButton("📜 Список всех фильмов", callback_data="all_films")
    markup.add(btn_search, btn_list)
    return markup

# Команда /start
@bot.message_handler(commands=['start'])
def start_message(message):
    bot.send_message(
        message.chat.id, 
        "🍿 Привет! Я помогу тебе найти фильм.\n\n"
        "Нажми на кнопку или просто напиши название фильма в чат.",
        reply_markup=get_main_keyboard()
    )

# Обработка нажатий на кнопки (чтобы не было "Не найдено")
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "instruction_search":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Просто напиши название фильма (например, 'Один дома') прямо сюда 👇")
    
    elif call.data == "all_films":
        bot.answer_callback_query(call.id)
        titles = "\n• ".join([f["name"] for f in FILMS_DB])
        bot.send_message(call.message.chat.id, f"У меня в базе сейчас:\n• {titles}")

# Логика поиска по тексту
@bot.message_handler(content_types=['text'])
def search_films(message):
    query = message.text.lower().strip()
    results = [f for f in FILMS_DB if query in f['name'].lower()]

    if results:
        for film in results:
            text = f"✅ **Найдено:** {film['name']}\n🔗 [Смотреть фильм]({film['url']})"
            bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=False)
    else:
        bot.send_message(
            message.chat.id, 
            "❌ К сожалению, ничего не нашлось. Проверь название или попробуй другой фильм.",
            reply_markup=get_main_keyboard()
        )

# Запуск бота
if __name__ == '__main__':
    print("Бот успешно запущен и готов к работе!")
    bot.infinity_polling()
