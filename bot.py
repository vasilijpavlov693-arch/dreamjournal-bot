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

# Настройка логирования
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

logger.info("🚀 Запуск бота...")

# --- Проверка переменных ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)

# --- Инициализация бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logger.info("✅ Бот инициализирован")

# --- Команда /start ---
@dp.message(Command("start"))
async def start_command(message: Message):
    user_name = message.from_user.first_name
    await message.answer(
        f"Привет, {user_name}! 🎙️\n\n"
        "Отправь голосовое сообщение, и я расшифрую его через Replicate API."
    )
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

# --- Обработчик голосовых сообщений (временный) ---
@dp.message(lambda message: message.voice)
async def handle_voice(message: types.Message):
    await message.answer("🎤 Голосовое получено! Обработка временно отключена для теста.")

# --- Минимальный веб-сервер для Render (ОБЯЗАТЕЛЬНО) ---
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

def run_web_server():
    """Запускает веб-сервер на порту 10000 (или PORT из переменных)"""
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