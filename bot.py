import os
import sys
import logging
import asyncio
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from fastapi import FastAPI
import uvicorn
from groq import Groq
import google.generativeai as genai

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

logger.info("🚀 Запуск бота...")

# --- Проверка переменных ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not BOT_TOKEN:
    logger.error("❌ ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)
if not GROQ_API_KEY:
    logger.error("❌ ОШИБКА: GROQ_API_KEY не найден! Получите бесплатный ключ на console.groq.com")
    sys.exit(1)
if not GEMINI_API_KEY:
    logger.error("❌ ОШИБКА: GEMINI_API_KEY не найден! Получите бесплатный ключ на aistudio.google.com")
    sys.exit(1)

# --- Инициализация бота и клиентов ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logger.info("✅ Бот инициализирован")

groq_client = Groq(api_key=GROQ_API_KEY)

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.0-flash')


# --- Команда /start ---
@dp.message(Command("start"))
async def start_command(message: Message):
    user_name = message.from_user.first_name
    await message.answer(
        f"Привет, {user_name}! 🎙️🌙\n\n"
        "Я — твой волшебный дневник снов.\n"
        "Просто отправь мне голосовое сообщение с рассказом о своём сне, "
        "и я не только расшифрую его, но и превращу в красивую историю."
    )
    logger.info(f"Пользователь {message.from_user.id} запустил бота")


# --- Обработчик голосовых сообщений ---
@dp.message(lambda message: message.voice)
async def handle_voice(message: types.Message):
    await bot.send_chat_action(message.chat.id, action="typing")
    processing_msg = await message.answer("🎧 Слушаю твой сон...")

    temp_audio_path = None

    try:
        # 1. Скачиваем голосовое
        file = await bot.get_file(message.voice.file_id)
        temp_audio_path = f"voice_{message.from_user.id}_{message.message_id}.ogg"
        await bot.download_file(file.file_path, temp_audio_path)

        await processing_msg.edit_text("📤 Расшифровываю через Groq...")

        # 2. Распознавание речи через Groq Whisper
        with open(temp_audio_path, "rb") as audio_file:
            transcription = groq_client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",
                language="ru",
                response_format="text"
            )

        raw_text = transcription if isinstance(transcription, str) else transcription.text

        if not raw_text or raw_text.strip() == "":
            raise Exception("Не удалось распознать речь. Попробуй говорить чётче.")

        # 3. Удаляем временный файл
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

        await processing_msg.edit_text("✨ Превращаю сон в красивую историю через Gemini...")

        # 4. Обработка текста через Gemini
        prompt = (
            "Ты — писатель и поэт. Преврати следующий сырой пересказ сна в красивый, "
            "поэтичный и образный рассказ на русском языке. Добавь атмосферу, метафоры "
            "и немного таинственности. Сохрани суть сна, но сделай его литературным.\n\n"
            f"Сон пользователя:\n{raw_text}"
        )

        gemini_response = gemini_model.generate_content(prompt)
        polished_dream = gemini_response.text

        if not polished_dream:
            polished_dream = raw_text

        # 5. Отправляем результат
        await processing_msg.delete()

        response_text = (
            f"🌙 *Твой сон в красивом пересказе:*\n\n"
            f"{polished_dream}\n\n"
            f"---\n"
            f"📝 *Исходная расшифровка:*\n"
            f"_{raw_text}_"
        )

        await message.answer(response_text, parse_mode="Markdown")

    except Exception as e:
        # Очистка
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

        logger.error(f"Ошибка обработки: {e}")
        await processing_msg.edit_text(
            f"❌ *Что-то пошло не так:*\n`{str(e)[:150]}`\n\n"
            f"Попробуй записать голосовое ещё раз.",
            parse_mode="Markdown"
        )


# --- Эхо для текстовых сообщений ---
@dp.message()
async def echo_message(message: Message):
    if message.text:
        await message.answer(
            "📝 Ты прислал текст. Чтобы записать сон, отправь, пожалуйста, **голосовое сообщение**."
        )


# --- Минимальный веб-сервер для Render ---
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Dream Journal Bot is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

def run_web_server():
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🌐 Запуск веб-сервера на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

web_thread = threading.Thread(target=run_web_server, daemon=True)
web_thread.start()
logger.info("✅ Веб-сервер запущен в фоновом потоке")


# --- Основная функция бота (Long Polling) ---
async def main():
    logger.info("🔄 Запуск режима long polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)