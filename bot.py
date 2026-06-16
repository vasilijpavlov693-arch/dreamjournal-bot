import replicate
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
    # Показываем статус "печатает..."
    await bot.send_chat_action(message.chat.id, action="typing")
    
    # Отправляем сообщение о начале обработки
    processing_msg = await message.answer("🎧 Слушаю ваш голосовой...")

    temp_audio_path = None
    
    try:
        # 1. Скачиваем голосовое сообщение от пользователя
        file = await bot.get_file(message.voice.file_id)
        temp_audio_path = f"voice_{message.from_user.id}_{message.message_id}.ogg"
        await bot.download_file(file.file_path, temp_audio_path)
        
        # Обновляем статус
        await processing_msg.edit_text("📤 Отправляю аудио в Replicate API...")
        
        # 2. Инициализируем клиент Replicate (токен из переменных окружения)
        replicate_client = replicate.Client(api_token=os.getenv("REPLICATE_API_TOKEN"))
        
        # 3. Отправляем аудио в Replicate Whisper
        # Важно: читаем файл как байты, чтобы избежать ошибки "BufferedReader is not JSON serializable"
        with open(temp_audio_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
        
        # 4. Вызываем модель Whisper через Replicate
        # Модель: openai/whisper (используем последнюю стабильную версию)
        output = replicate_client.run(
            "openai/whisper:4d50797290df275329f394e1482ced229332b8ad3c5b4e1e4d4c7f9d2f8a5c0b",
            input={
                "audio": audio_bytes,  # Передаём байты
                "model": "large-v3",   # Самая точная модель
                "language": "ru",      # Язык распознавания
                "task": "transcribe",  # Простая транскрибация
                "temperature": 0       # Минимум случайности
            }
        )
        
        # 5. Извлекаем текст из ответа Replicate
        if isinstance(output, dict):
            transcribed_text = output.get("text", "")
        elif isinstance(output, str):
            transcribed_text = output
        else:
            # На случай, если вернётся другой формат
            transcribed_text = str(output)
        
        # Проверяем, что текст не пустой
        if not transcribed_text or transcribed_text.strip() == "":
            raise Exception("Whisper не вернул текст. Возможно, аудио слишком короткое или шумное.")
        
        # 6. Удаляем временный файл
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        # 7. Отправляем результат пользователю
        await processing_msg.delete()
        
        response_text = (
            f"📝 *Расшифровка вашего голосового:*\n\n"
            f"_{transcribed_text}_\n\n"
            f"💡 Отправьте новое голосовое, чтобы продолжить."
        )
        
        await message.answer(response_text, parse_mode="Markdown")
        
    except Exception as e:
        # Очистка временного файла в случае ошибки
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        # Логируем ошибку
        logging.error(f"Ошибка распознавания: {e}")
        
        # Отправляем понятное сообщение об ошибке пользователю
        error_text = (
            f"❌ *Ошибка распознавания:*\n"
            f"`{str(e)[:150]}`\n\n"
            f"Попробуйте:\n"
            f"• Записать голосовое чётче\n"
            f"• Уменьшить длительность (до 30 секунд)\n"
            f"• Проверить интернет"
        )
        await processing_msg.edit_text(error_text, parse_mode="Markdown")
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