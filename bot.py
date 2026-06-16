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
        "Я твой голосовой дневник снов.\n"
        "Отправь мне голосовое сообщение, и я расшифрую его.\n\n"
        "✨ Бот работает!"
    )
    logger.info(f"Пользователь {message.from_user.id} запустил бота")

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
    """Запускает веб-сервер в отдельном потоке"""
    port = int(os.getenv("PORT", 10000))  # Render задаёт порт через переменную PORT
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