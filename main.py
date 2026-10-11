import logging
import uuid
import asyncio
import time
import urllib.parse
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ============ ВСТАВЬ СВОИ ЗНАЧЕНИЯ ============
TELEGRAM_TOKEN = "8883364704:AAGUZPOmNLu1WQIQeAJ00_G7YW8dIzhN3tk"
GIGACHAT_AUTH_KEY = "MDFhMTJiNmMtZTcyOC03MGRkLTg1MWYtZDZjNjE4YTk1NjczOmQ5MGRmMmZlLTI3NWUtNGQwNC1hN2E1LThhMmJiNzI0MWIzMg=="
# ==============================================

GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
GIGACHAT_FILE_URL = "https://gigachat.devices.sberbank.ru/api/v1/files/{file_id}/content"

history = {}
awaiting_mode = {}
user_locks = {}
logging.basicConfig(level=logging.INFO)

_access_token = None

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎨 Нарисовать картинку")],
        [KeyboardButton("🔍 Поиск в интернете")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


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
    response = requests.post(GIGACHAT_AUTH_URL, headers=headers, data=data, verify=False, timeout=30)
    response.raise_for_status()
    _access_token = response.json()["access_token"]
    return _access_token


def request_with_retry(func, max_attempts=3):
    """Повторяет запрос до 3 раз при ошибке 500"""
    last_error = None
    for attempt in range(max_attempts):
        try:
            return func()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 500:
                last_error = e
                if attempt < max_attempts - 1:
                    time.sleep(2)  # Пауза 2 секунды перед повтором
                    continue
            raise
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_attempts - 1:
                time.sleep(2)
                continue
            raise
    raise last_error


def ask_gigachat(messages):
    def _call():
        token = get_gigachat_token()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {"model": "GigaChat", "messages": messages, "temperature": 0.7}
        response = requests.post(GIGACHAT_API_URL, headers=headers, json=payload, verify=False, timeout=60)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    return request_with_retry(_call)


def generate_image_gigachat(prompt):
    def _call():
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
    return request_with_retry(_call)


def web_search(query):
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        r = requests.get(url, params=params, timeout=15)
        data = r.json()

        results = []
        if data.get("AbstractText"):
            results.append(f"Кратко: {data['AbstractText']}")
            if data.get("AbstractURL"):
                results.append(f"Источник: {data['AbstractURL']}")

        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"• {topic['Text']}")

        if not results:
            results.append(f"Прямых ответов нет. Полный поиск: https://duckduckgo.com/?q={urllib.parse.quote(query)}")

        return "\n".join(results)
    except Exception as e:
        return f"Ошибка поиска: {e}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    awaiting_mode[update.effective_user.id] = None
    await update.message.reply_text(
        "Привет! Я ИИ-бот на GigaChat. Умею:\n"
        "💬 Отвечать на текст\n"
        "🎨 Рисовать картинки\n"
        "🔍 Искать в интернете\n\n"
        "Кнопки внизу — выбери, что нужно!",
        reply_markup=MAIN_KEYBOARD
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_user.id] = []
    awaiting_mode[update.effective_user.id] = None
    await update.message.reply_text("История очищена.", reply_markup=MAIN_KEYBOARD)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()

    async with user_locks[user_id]:
        if text == "🎨 Нарисовать картинку":
            awaiting_mode[user_id] = "image"
            await update.message.reply_text("✍️ Напиши, что нарисовать. Например: собака на коте")
            return

        if text == "🔍 Поиск в интернете":
            awaiting_mode[user_id] = "search"
            await update.message.reply_text("🔍 Что искать? Напиши запрос.")
            return

        if awaiting_mode.get(user_id) == "image":
            awaiting_mode[user_id] = None
            await update.message.reply_text("🎨 Рисую... 10-20 секунд.")
            try:
                image_bytes = generate_image_gigachat(text)
                if image_bytes:
                    await update.message.reply_photo(photo=image_bytes, reply_markup=MAIN_KEYBOARD)
                else:
                    await update.message.reply_text("Не удалось сгенерировать. Попробуй другой запрос.", reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                await update.message.reply_text(f"Ошибка картинки: {e}", reply_markup=MAIN_KEYBOARD)
            return

        if awaiting_mode.get(user_id) == "search":
            awaiting_mode[user_id] = None
            await update.message.reply_text(f"🔍 Ищу: {text}...")
            search_results = web_search(text)
            messages = [
                {"role": "system", "content": "Ты помощник. Используй результаты поиска, чтобы ответить на вопрос. Отвечай кратко на русском."},
                {"role": "user", "content": f"Вопрос: {text}\n\nРезультаты:\n{search_results}"},
            ]
            try:
                answer = ask_gigachat(messages)
                await update.message.reply_text(answer, reply_markup=MAIN_KEYBOARD)
            except Exception as e:
                await update.message.reply_text(f"Ошибка ИИ: {e}", reply_markup=MAIN_KEYBOARD)
            return

        if user_id not in history:
            history[user_id] = []

        history[user_id].append({"role": "user", "content": text})
        messages = [{"role": "system", "content": "Ты дружелюбный помощник. Отвечай на русском языке."}]
        messages += history[user_id][-20:]

        try:
            answer = ask_gigachat(messages)
            history[user_id].append({"role": "assistant", "content": answer})
            await update.message.reply_text(answer, reply_markup=MAIN_KEYBOARD)
        except Exception as e:
            await update.message.reply_text(f"Ошибка ИИ: {e}", reply_markup=MAIN_KEYBOARD)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
