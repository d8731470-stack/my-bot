import logging
import base64
import urllib.parse
import uuid
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============ ВСТАВЬ СВОИ ЗНАЧЕНИЯ ============
TELEGRAM_TOKEN = "8883364704:AAGUZPOmNLu1WQIQeAJ00_G7YW8dIzhN3tk"
GIGACHAT_AUTH_KEY = "MDFhMTJiNmMtZTcyOC03MGRkLTg1MWYtZDZjNjE4YTk1NjczOmQ5MGRmMmZlLTI3NWUtNGQwNC1hN2E1LThhMmJiNzI0MWIzMg=="
# ==============================================

GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

history = {}
waiting_for_image_prompt = {}  # Кто ждёт ввода промпта для картинки
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
    payload = {
        "model": "GigaChat",
        "messages": messages,
        "temperature": 0.7,
    }
    response = requests.post(GIGACHAT_API_URL, headers=headers, json=payload, verify=False)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


# Клавиатура с кнопкой-иконкой
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("🎨 Нарисовать картинку")]
    ],
    resize_keyboard=True
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    await update.message.reply_text(
        "Привет! Я ИИ-бот на GigaChat. Умею:\n"
        "💬 Отвечать на текст\n"
        "🎨 Рисовать картинки (кнопка внизу)\n\n"
        "Просто напиши что-нибудь!",
        reply_markup=main_keyboard
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    await update.message.reply_text("История диалога очищена.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Если пользователь нажал на кнопку "Нарисовать картинку"
    if text == "🎨 Нарисовать картинку":
        waiting_for_image_prompt[user_id] = True
        await update.message.reply_text(
            "✏️ Напишите текст, что хотите сгенерировать.\n"
            "Например: кот обнимает собаку",
            reply_markup=main_keyboard
        )
        return

    # Если пользователь ждёт ввода промпта для картинки
    if waiting_for_image_prompt.get(user_id):
        waiting_for_image_prompt[user_id] = False
        await generate_image_by_prompt(update, text)
        return

    # Обычный диалог с GigaChat
    if user_id not in history:
        history[user_id] = []

    history[user_id].append({"role": "user", "content": text})

    messages = [{"role": "system", "content": "Ты дружелюбный помощник. Отвечай на русском языке."}]
    messages += history[user_id][-20:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        answer = ask_gigachat(messages)
        history[user_id].append({"role": "assistant", "content": answer})
        await update.message.reply_text(answer, reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"Ошибка ИИ: {e}")


async def generate_image_by_prompt(update: Update, prompt: str):
    """Генерирует картинку по текстовому промпту"""
    await update.message.chat.send_action(action=ChatAction.UPLOAD_PHOTO)

    # Переводим промпт на английский через GigaChat
    english_prompt = prompt
    try:
        translate_messages = [
            {"role": "system", "content": "You are a translator for an image generation service. Translate the user's text to English. Add descriptive style words (photorealistic, high detail, 4k) at the end. Reply ONLY with the translated prompt, no explanations."},
            {"role": "user", "content": prompt}
        ]
        english_prompt = ask_gigachat(translate_messages).strip()
    except Exception as e:
        logging.warning(f"Translation failed: {e}")

    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(english_prompt)}?width=1024&height=1024&nologo=true"

    try:
        await update.message.reply_photo(photo=url, caption=f"🎨 {prompt}", reply_markup=main_keyboard)
    except Exception as e:
        await update.message.reply_text(f"Ошибка картинки: {e}", reply_markup=main_keyboard)


async def img_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старая команда /img — оставим для совместимости"""
    prompt = " ".join(context.args)
    if not prompt:
        waiting_for_image_prompt[update.effective_user.id] = True
        await update.message.reply_text("✏️ Напишите текст, что хотите сгенерировать:")
        return
    await generate_image_by_prompt(update, prompt)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("img", img_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
