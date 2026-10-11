import logging
import base64
import urllib.parse
import uuid
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============ ВСТАВЬ СВОИ ЗНАЧЕНИЯ ============
TELEGRAM_TOKEN = "8883364704:AAGUZPOmNLu1WQIQeAJ00_G7YW8dIzhN3tk"
GIGACHAT_AUTH_KEY = "MDFhMTJiNmMtZTcyOC03MGRkLTg1MWYtZDZjNjE4YTk1NjczOmQ5MGRmMmZlLTI3NWUtNGQwNC1hN2E1LThhMmJiNzI0MWIzMg=="
# ==============================================

GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

history = {}
logging.basicConfig(level=logging.INFO)

# Кэш токена доступа GigaChat
_access_token = None

def get_gigachat_token():
    """Получает access token для GigaChat"""
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
    """Отправляет сообщения в GigaChat и возвращает ответ"""
    token = get_gigachat_token()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "model": "GigaChat",
        "messages": messages,
        "temperature": 0.7,
    }
    response = requests.post(GIGACHAT_API_URL, headers=headers, json=payload, verify=False)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    await update.message.reply_text(
        "Привет! Я ИИ-бот на GigaChat. Умею:\n"
        "💬 Отвечать на текст\n"
        "🎨 Рисовать картинки (команда /img)\n\n"
        "Просто напиши что-нибудь!"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    await update.message.reply_text("История диалога очищена.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in history:
        history[user_id] = []

    history[user_id].append({"role": "user", "content": text})

    messages = [{"role": "system", "content": "Ты дружелюбный помощник. Отвечай на русском языке."}]
    messages += history[user_id][-20:]

    try:
        answer = ask_gigachat(messages)
        history[user_id].append({"role": "assistant", "content": answer})
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Ошибка ИИ: {e}")


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Напиши так: /img кот в космосе")
        return
    await update.message.reply_text("🎨 Рисую...")
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=1024&height=1024&nologo=true"
    try:
        await update.message.reply_photo(photo=url)
    except Exception as e:
        await update.message.reply_text(f"Ошибка картинки: {e}")


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("img", generate_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
