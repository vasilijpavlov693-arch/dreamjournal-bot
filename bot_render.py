import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from fastapi import FastAPI, Request
import uvicorn
import os

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен из переменных окружения на Render
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # URL из переменных окружения

if not BOT_TOKEN or not WEBHOOK_URL:
    raise Exception("BOT_TOKEN or WEBHOOK_URL not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("✅ Бот работает на Render!")

@app.post("/webhook")
async def webhook(request: Request):
    update = types.Update(**await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(url=WEBHOOK_URL + "/webhook")
    logging.info(f"Webhook set to {WEBHOOK_URL}/webhook")

@app.get("/")
async def root():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)