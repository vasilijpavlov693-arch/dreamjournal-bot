import os
import sys
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message

# Настройка логирования для Render
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

logger.info("🚀 Запуск бота...")

# --- Проверка обязательных переменных ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ ОШИБКА: Переменная окружения BOT_TOKEN не найдена!")
    logger.error("Добавьте BOT_TOKEN в Environment Variables на Render")
    sys.exit(1)  # Выход с ошибкой

# --- Инициализация бота ---
try:
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    logger.info("✅ Бот инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации бота: {e}")
    sys.exit(1)

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

# --- Запуск поллинга ---
async def main():
    logger.info("🔄 Запуск режима long polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске: {e}")
        sys.exit(1)
