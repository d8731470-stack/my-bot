import os
import logging
import base64
import urllib.parse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# ============ КЛЮЧИ БЕРУТСЯ ИЗ ПЕРЕМЕННЫХ AMVERA ============
TELEGRAM_TOKEN = os.getenv("8883364704:AAEhTMF3RaROHUYgcm7KHwTl_3Zno_tKKLg")
GROQ_KEY = os.getenv("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")
# =========================================================

# ============ АКТУАЛЬНЫЕ МОДЕЛИ GROQ ============
MODEL_TEXT = "llama-3.3-70b-versatile"
MODEL_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"
# =================================================

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_KEY,
)

history = {}
logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    await update.message.reply_text(
        "Привет! Я ИИ-бот. Умею:\n"
        "💬 Отвечать на текст\n"
        "🖼️ Смотреть фото\n"
        "🎤 Распознавать голосовые\n"
        "🎨 Рисовать картинки (команда /img)\n\n"
        "Просто напиши что-нибудь!"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    await update.message.reply_text("История диалога очищена.")


async def send_to_ai(update, messages, user_id):
    try:
        response = client.chat.completions.create(
            model=MODEL_TEXT,
            messages=messages,
        )
        answer = response.choices[0].message.content
        history[user_id].append({"role": "assistant", "content": answer})
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Ошибка ИИ: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if user_id not in history:
        history[user_id] = []
    history[user_id].append({"role": "user", "content": text})
    messages = [{"role": "system", "content": "Ты дружелюбный помощник. Отвечай на русском языке."}]
    messages += history[user_id][-20:]
    await send_to_ai(update, messages, user_id)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    caption = update.message.caption or "Что на этом фото?"
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    base64_image = base64.b64encode(image_bytes).decode('utf-8')

    if user_id not in history:
        history[user_id] = []

    messages = [
        {"role": "system", "content": "Ты дружелюбный помощник. Отвечай на русском языке."},
        {"role": "user", "content": [
            {"type": "text", "text": caption},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]}
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL_VISION,
            messages=messages,
        )
        answer = response.choices[0].message.content
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text(f"Ошибка с фото: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in history:
        history[user_id] = []
    try:
        voice_file = await update.message.voice.get_file()
        audio_bytes = await voice_file.download_as_bytearray()
        await update.message.reply_text("🎧 Распознаю голос...")
        transcription = client.audio.transcriptions.create(
            file=("voice.ogg", bytes(audio_bytes), "audio/ogg"),
            model="whisper-large-v3-turbo",
            language="ru",
        )
        text = transcription.text
        await update.message.reply_text(f"Ты сказал: «{text}»")
        history[user_id].append({"role": "user", "content": text})
        messages = [{"role": "system", "content": "Ты дружелюбный помощник. Отвечай на русском языке."}]
        messages += history[user_id][-20:]
        await send_to_ai(update, messages, user_id)
    except Exception as e:
        await update.message.reply_text(f"Ошибка распознавания: {e}")


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
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
