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
async def handle_voice(message: types.Message):
    await bot.send_chat_action(message.chat.id, action="typing")
    processing_msg = await message.answer("🎧 Обрабатываю голосовое через Replicate...")

    temp_audio_path = None

    try:
        # 1. Скачиваем голосовое
        file = await bot.get_file(message.voice.file_id)
        temp_audio_path = f"voice_{message.from_user.id}_{message.message_id}.ogg"
        await bot.download_file(file.file_path, temp_audio_path)

        await processing_msg.edit_text("📤 Отправляю аудио в Replicate API...")

        # 2. Читаем файл как байты (ЭТО ВАЖНО!)
        with open(temp_audio_path, "rb") as audio_file:
            audio_bytes = audio_file.read()

        # 3. Отправляем в Replicate
        output = replicate_client.run(
            WHISPER_MODEL,
            input={
                "audio": audio_bytes,  # Передаём байты, а не объект файла
                "model": "large-v3",
                "language": "ru",
                "task": "transcribe"
            }
        )

        # 4. Извлекаем текст
        if isinstance(output, dict):
            transcribed_text = output.get("text", "")
        elif isinstance(output, str):
            transcribed_text = output
        else:
            transcribed_text = str(output)

        if not transcribed_text or transcribed_text.strip() == "":
            raise Exception("Whisper не вернул текст")

        # 5. Удаляем временный файл
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

        await processing_msg.delete()
        await message.answer(
            f"📝 *Расшифровка:*\n\n_{transcribed_text}_",
            parse_mode="Markdown"
        )

    except Exception as e:
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

        logger.error(f"Ошибка: {e}")
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