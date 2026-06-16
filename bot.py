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
from openai import OpenAI


# Настройка логирования
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

logger.info("🚀 Запуск бота...")

# --- Проверка переменных ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    logger.error("❌ ОШИБКА: GROQ_API_KEY не найден! Получите бесплатный ключ на console.groq.com")
    sys.exit(1)

# --- Инициализация бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logger.info("✅ Бот инициализирован")

# --- Инициализация клиента Groq ---
groq_client = Groq(api_key=GROQ_API_KEY)

# --- Команда /start ---
@dp.message(Command("start"))
async def start_command(message: Message):
    user_name = message.from_user.first_name
    await message.answer(
        f"Привет, {user_name}! 🎙️\n\n"
        "Отправь голосовое сообщение, и я расшифрую его через Groq Whisper (бесплатно!)."
    )
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

# --- Обработчик голосовых сообщений (Groq) ---
@dp.message(lambda message: message.voice)
async def handle_voice(message: types.Message):
    await processing_msg.edit_text("✨ Превращаю сон в красивую историю через Cloudflare...")

# URL вашего развернутого Worker
WORKER_API_URL = "https://ai-worker-proxy.vasilijpavlov693.workers.dev/"
# Пароль (PROXY_AUTH_TOKEN), который вы установили в Cloudflare
WORKER_AUTH_TOKEN = "1q2w-#E$R"

# Инициализируем клиент для работы с Worker'ом
client = OpenAI(
    base_url=WORKER_API_URL,
    api_key=WORKER_AUTH_TOKEN,
)

# Отправляем запрос к прокси, который перенаправит его в Gemini
response = client.chat.completions.create(
    model="gemini-2.0-flash",  # или "super-brain" — зависит от настройки прокси
    messages=[
        {"role": "system", "content": "Ты — писатель и поэт. Преврати следующий сырой пересказ сна в красивый, поэтичный и образный рассказ на русском языке. Добавь атмосферу и метафоры. Сохрани суть сна."},
        {"role": "user", "content": raw_text}
    ],
    temperature=0.7
)

polished_dream = response.choices[0].message.content
    await bot.send_chat_action(message.chat.id, action="typing")
    processing_msg = await message.answer("🎧 Слушаю ваш голосовой...")

    temp_audio_path = None
    
    try:
        # 1. Скачиваем голосовое
        file = await bot.get_file(message.voice.file_id)
        temp_audio_path = f"voice_{message.from_user.id}_{message.message_id}.ogg"
        await bot.download_file(file.file_path, temp_audio_path)
        
        await processing_msg.edit_text("📤 Отправляю аудио в Groq API...")
        
        # 2. Отправляем в Groq Whisper (бесплатно!)
        with open(temp_audio_path, "rb") as audio_file:
            transcription = groq_client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",  # Бесплатная модель
                language="ru",
                response_format="text"
            )
        
        # 3. Извлекаем текст
        transcribed_text = transcription if isinstance(transcription, str) else transcription.text
        
        if not transcribed_text or transcribed_text.strip() == "":
            raise Exception("Whisper не вернул текст")
        
        # 4. Удаляем временный файл
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        await processing_msg.delete()
        await message.answer(
            f"📝 *Расшифровка:*\n\n_{transcribed_text}_",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        # Очистка
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        logger.error(f"Ошибка распознавания: {e}")
        await processing_msg.edit_text(
            f"❌ *Ошибка распознавания:*\n`{str(e)[:150]}`\n\n"
            f"Попробуйте:\n"
            f"• Записать голосовое чётче\n"
            f"• Уменьшить длительность (до 30 секунд)",
            parse_mode="Markdown"
        )

# --- Эхо для текстовых сообщений (временная функция) ---
@dp.message()
async def echo_message(message: Message):
    if message.text:
        await message.answer(f"Ты написал: {message.text}")
        logger.info(f"Получен текст от {message.from_user.id}: {message.text}")

# --- Минимальный веб-сервер для Render ---
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

def run_web_server():
    """Запускает веб-сервер на порту 10000"""
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🌐 Запуск веб-сервера на порту {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

# --- Запуск веб-сервера в фоновом потоке ---
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