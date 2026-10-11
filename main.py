import logging
import urllib.parse
import uuid
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# ============ ВСТАВЬ СВОИ ЗНАЧЕНИЯ ============
TELEGRAM_TOKEN = "8883364704:AAEhTMF3RaROHUYgcm7KHwTl_3Zno_tKKLg"
GIGACHAT_AUTH_KEY = "MDFhMTJiNmMtZTcyOC03MGRkLTg1MWYtZDZjNjE4YTk1NjczOmQ5MGRmMmZlLTI3NWUtNGQwNC1hN2E1LThhMmJiNzI0MWIzMg=="
# ==============================================

GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_FILE_URL = "https://gigachat.devices.sberbank.ru/api/v1/files/{file_id}/content"

history = {}
awaiting_image = {}  # Кто сейчас ждёт ввода для картинки
logging.basicConfig(level=logging.INFO)

_access_token = None


def get_gigachat_token():
    global _access_token
    if _access_token:
        return _access_token
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {GIGACHAT_AUTH_KEY}",
    }
    data = {"scope": "GIGACHAT_API_PERS"}
    response = requests.post(GIGACHAT_AUTH_URL, headers=headers, data=data, verify=False)
    response.raise_for_status()
    _access_token = response.json()["access_token"]
    return _access_token


def ask_gigachat(messages):
    token = get_gigachat_token()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {"model": "GigaChat", "messages": messages, "temperature": 0.7}
    response = requests.post(GIGACHAT_API_URL, headers=headers, json=payload, verify=False)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def generate_image_gigachat(prompt):
    token = get_gigachat_token()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": "Ты — художник. Нарисуй то, что просит пользователь."},
            {"role": "user", "content": prompt},
        ],
        "function_call": "auto",
    }
    r = requests.post(GIGACHAT_API_URL, headers=headers, json=payload, verify=False, timeout=60)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]

    if "<img src=\"" not in content:
        return None
    start = content.find("<img src=\"") + len("<img src=\"")
    end = content.find("\"", start)
    file_id = content[start:end]

    file_headers = {"Accept": "application/jpg", "Authorization": f"Bearer {token}"}
    img_response = requests.get(GIGACHAT_FILE_URL.format(file_id=file_id), headers=file_headers, verify=False, timeout=60)
    img_response.raise_for_status()
    return img_response.content


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    
    # Кнопка под сообщением
    keyboard = [[InlineKeyboardButton("🎨 Нарисовать картинку", callback_data="draw")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Привет! Я ИИ-бот на GigaChat. Умею:\n"
        "💬 Отвечать на текст\n"
        "🎨 Рисовать картинки\n\n"
        "Нажми на кнопку ниже или просто напиши что-нибудь!",
        reply_markup=reply_markup
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    await update.message.reply_text("История диалога очищена.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку"""
    query = update.callback_query
    await query.answer()  # Обязательно ответить на callback [citation:3]
    
    if query.data == "draw":
        awaiting_image[query.from_user.id] = True
        await query.message.reply_text("✍️ Напиши, что нарисовать. Например: собака сидит на коте")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Если пользователь нажал кнопку и ждёт ввода для картинки
    if awaiting_image.get(user_id):
        awaiting_image[user_id] = False
        await update.message.reply_text("🎨 Рисую... Это займёт 10-20 секунд.")
        try:
            image_bytes = generate_image_gigachat(text)
            if image_bytes:
                await update.message.reply_photo(photo=image_bytes)
            else:
                await update.message.reply_text("Не удалось сгенерировать. Попробуй другой запрос.")
        except Exception as e:
            await update.message.reply_text(f"Ошибка картинки: {e}")
        return

    # Обычный текстовый ответ
    if user_id not in history:
        history[user_id] = []

    history[user_id].append({"role": "user", "content": text})
    messages = [{"role": "system", "content": "Ты дружелюбный помощник. Отвечай на русском языке."}]
    messages += history[user_id][-20:]

    try:
        answer = ask_gigachat(messages)
        history[user_id].append({"role": "assistant", "content": answer})
        
        # Показываем кнопку и после обычного ответа
        keyboard = [[InlineKeyboardButton("🎨 Нарисовать картинку", callback_data="draw")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(answer, reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(f"Ошибка ИИ: {e}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
