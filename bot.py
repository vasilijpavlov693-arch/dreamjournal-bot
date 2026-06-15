import os
import sys
import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

logger.info("🚀 Запуск бота...")

# --- Проверка переменных ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не найден!")
    sys.exit(1)

if not REPLICATE_API_TOKEN:
    logger.warning("⚠️ REPLICATE_API_TOKEN не найден. Распознавание голоса не будет работать.")

# --- Инициализация бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ID модели Whisper на Replicate
WHISPER_MODEL = "openai/whisper:4d50797290df275329f394e1482ced229332b8ad3c5b4e1e4d4c7f9d2f8a5c0b"


# --- Команда /start ---
@dp.message(Command("start"))
async def start_command(message: Message):
    user_name = message.from_user.first_name
    await message.answer(
        f"🎙️ Привет, {user_name}!\n\n"
        "Я твой голосовой дневник снов.\n\n"
        "📤 **Как работать со мной:**\n"
        "1. Нажми на иконку микрофона 🎤\n"
        "2. Запиши свой сон (15-30 секунд)\n"
        "3. Отправь мне голосовое сообщение\n\n"
        "✨ Я расшифрую его и пришлю текст!\n\n"
        "🔮 В планах: красивое оформление снов и генерация картинок.",
        parse_mode="Markdown"
    )
    logger.info(f"Пользователь {message.from_user.id} запустил бота")


# --- Обработчик голосовых сообщений ---
@dp.message(lambda message: message.voice)
async def handle_voice(message: Message):
    if not REPLICATE_API_TOKEN:
        await message.answer("❌ Распознавание голоса временно недоступно. API ключ не настроен.")
        return

    # Отправляем статус "печатает"
    await bot.send_chat_action(message.chat.id, action="typing")
    
    processing_msg = await message.answer("🎧 Слушаю твой сон...")

    temp_audio_path = None
    
    try:
        # 1. Скачиваем голосовое сообщение
        file = await bot.get_file(message.voice.file_id)
        temp_audio_path = f"voice_{message.from_user.id}_{message.message_id}.ogg"
        await bot.download_file(file.file_path, temp_audio_path)
        
        await processing_msg.edit_text("🔄 Отправляю на распознавание...")
        
        # 2. Отправляем в Replicate Whisper
        # Replicate работает с публичными URL, поэтому загружаем файл на transfer.sh
        # (простой способ отправить файл в Replicate)
        
        with open(temp_audio_path, "rb") as f:
            files = {"audio": f}
            headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}"}
            
            # Создаём prediction
            response = requests.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers,
                json={
                    "version": WHISPER_MODEL.split(":")[1],
                    "input": {
                        "audio": open(temp_audio_path, "rb"),
                        "model": "large-v3",
                        "language": "ru",
                        "task": "transcribe"
                    }
                }
            )
            
            if response.status_code != 201:
                raise Exception(f"Replicate API error: {response.text}")
            
            prediction = response.json()
            
            # Ждём завершения
            while prediction["status"] not in ["succeeded", "failed"]:
                import time
                time.sleep(1)
                status_response = requests.get(
                    prediction["urls"]["get"],
                    headers=headers
                )
                prediction = status_response.json()
            
            if prediction["status"] == "failed":
                raise Exception("Replicate failed to process audio")
            
            transcribed_text = prediction["output"]["text"]
        
        # 3. Очистка и отправка результата
        os.remove(temp_audio_path)
        await processing_msg.delete()
        
        await message.answer(
            f"📝 *Расшифровка твоего сна:*\n\n"
            f"_{transcribed_text}_\n\n"
            f"💡 Чтобы записать следующий сон, просто отправь голосовое сообщение.",
            parse_mode="Markdown"
        )
        logger.info(f"Распознан голос от {message.from_user.id}: {transcribed_text[:50]}...")
        
    except Exception as e:
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
        
        logger.error(f"Ошибка распознавания: {e}")
        await processing_msg.edit_text(
            f"❌ *Ошибка распознавания:*\n{str(e)[:200]}\n\n"
            f"Попробуй:\n"
            f"• Записать голосовое чётче\n"
            f"• Уменьшить длительность (до 30 секунд)\n"
            f"• Проверить интернет",
            parse_mode="Markdown"
        )


# --- Эхо для текстовых сообщений (для отладки) ---
@dp.message()
async def echo_message(message: Message):
    if message.text:
        await message.answer(f"📝 Ты написал: {message.text}\n\nОтправь мне голосовое сообщение о своём сне!")


# --- Запуск бота ---
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
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)