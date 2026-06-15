import logging
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from fastapi import FastAPI, Request
import uvicorn
import os

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота (замени на свой)
BOT_TOKEN = "8062420977:AAH58hcYSJi0SYn48jB6xJTwNRpJwBmoxEU"

# Публичный URL от pinggy.io (ОБЯЗАТЕЛЬНО ЗАПОЛНИ!)
WEBHOOK_URL = "https://nqfyr-78-37-19-176.run.pinggy-free.link  "  # ВСТАВЬ СВОЙ URL!

# Если URL не заполнен — бот не запустится
if not WEBHOOK_URL:
    logger.error("❌ WEBHOOK_URL не задан! Вставь свой адрес от pinggy.io в переменную WEBHOOK_URL")
    exit(1)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Обработчики команд ---
@dp.message(Command("start"))
async def start(message: types.Message):
    logger.info(f"Получена команда /start от {message.from_user.id}")
    await message.answer("✅ Бот работает через вебхук! Всё отлично.")

@dp.message()
async def echo(message: types.Message):
    logger.info(f"Получено сообщение: {message.text}")
    await message.answer(f"Вы написали: {message.text}")

# --- Настройка FastAPI с lifespan (новый синтаксис) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"✅ Вебхук установлен: {WEBHOOK_URL}")
    else:
        logger.info(f"ℹ️ Вебхук уже был установлен: {WEBHOOK_URL}")
    yield
    # Shutdown
    await bot.session.close()
    logger.info("Бот остановлен")

app = FastAPI(lifespan=lifespan)
WEBHOOK_PATH = "/webhook"

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    json_data = await request.json()
    update = types.Update(**json_data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running"}

# --- Запуск ---
if __name__ == "__main__":
    logger.info("🚀 Запуск бота в режиме вебхука...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")