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
from supabase import create_client, Client

# --- Инициализация Supabase ---
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

async def save_dream(user_id: int, raw_text: str, polished_text: str):
    """Сохраняет сон в базу данных"""
    try:
        # Сначала найдем telegram_id пользователя
        user_response = supabase.table("users").select("id").eq("telegram_id", user_id).execute()
        if user_response.data:
            db_user_id = user_response.data[0]['id']
            
            # Сохраняем сон
            supabase.table("dreams").insert({
                "user_id": db_user_id,
                "raw_text": raw_text,
                "polished_text": polished_text
            }).execute()
            print(f"✅ Сон пользователя {user_id} сохранен!")
        else:
            print(f"⚠️ Пользователь {user_id} не найден в базе")
    except Exception as e:
        print(f"❌ Ошибка сохранения сна: {e}")

# --- Функция для регистрации пользователя ---
async def register_user(telegram_id: int, username: str = None):
    """Добавляет нового пользователя в таблицу users, если его там нет."""
    try:
        # Проверяем, есть ли уже такой пользователь
        response = supabase.table("users").select("id").eq("telegram_id", telegram_id).execute()
        
        if not response.data:  # Если пользователь не найден
            # Добавляем нового
            supabase.table("users").insert({
                "telegram_id": telegram_id,
                "username": username
            }).execute()
            print(f"✅ Новый пользователь {telegram_id} добавлен в базу!")
        else:
            print(f"ℹ️ Пользователь {telegram_id} уже существует")
    except Exception as e:
        print(f"❌ Ошибка базы данных: {e}")

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

logger.info("🚀 Запуск бота...")

# --- Проверка переменных ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN:
    logger.error("❌ ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)
if not GROQ_API_KEY:
    logger.error("❌ ОШИБКА: GROQ_API_KEY не найден! Получите бесплатный ключ на console.groq.com")
    sys.exit(1)
# --- Инициализация бота и клиентов ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logger.info("✅ Бот инициализирован")

groq_client = Groq(api_key=GROQ_API_KEY)

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
    await register_user(message.from_user.id, message.from_user.username)

# ========== МОДИФИЦИРОВАННЫЙ ОБРАБОТЧИК ГОЛОСОВЫХ ==========
@dp.message(lambda message: message.voice)
async def handle_voice(message: types.Message):
    await bot.send_chat_action(message.chat.id, action="typing")
    processing_msg = await message.answer("🎧 Слушаю твой сон...")

    temp_audio_path = None

    try:
        # 1. Проверяем подписку ДО обработки
        user_status = await get_user_subscription(message.from_user.id)
        is_premium = user_status == "premium"

        # 2. Скачиваем голосовое
        file = await bot.get_file(message.voice.file_id)
        temp_audio_path = f"voice_{message.from_user.id}_{message.message_id}.ogg"
        await bot.download_file(file.file_path, temp_audio_path)

        await processing_msg.edit_text("📤 Расшифровываю через Groq...")

        # 3. Распознавание речи (общее для всех)
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

        # 4. Удаляем временный файл
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

        # 5. БАЗОВАЯ ФУНКЦИЯ (для всех): просто расшифровка
        if not is_premium:
            await processing_msg.delete()
            await message.answer(
                f"📝 *Расшифровка:*\n\n_{raw_text}_\n\n"
                f"💡 Хочешь красивую обработку и анализ? Используй команду /subscribe (временно бесплатно!)",
                parse_mode="Markdown"
            )
            return

        # 6. ПРЕМИУМ-ФУНКЦИЯ: литературная обработка
        await processing_msg.edit_text("✨ Превращаю сон в красивую историю...")

        prompt = (
            "Ты — писатель и поэт. Преврати следующий сырой пересказ сна в красивый, "
            "поэтичный и образный рассказ на русском языке. Добавь атмосферу, метафоры "
            "и немного таинственности. Сохрани суть сна, но сделай его литературным.\n\n"
            f"Сон пользователя:\n{raw_text}"
        )

        llm_response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Ты — писатель и поэт, пишешь на русском языке."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=1024
        )

        polished_dream = llm_response.choices[0].message.content
        if not polished_dream:
            polished_dream = raw_text

        # Сохраняем сон в базу (только для премиум-пользователей)
        await save_dream(message.from_user.id, raw_text, polished_dream)

        await processing_msg.delete()
        await message.answer(
            f"🌙 *Твой сон в красивом пересказе:*\n\n"
            f"{polished_dream}\n\n"
            f"---\n"
            f"📝 *Исходная расшифровка:*\n"
            f"_{raw_text}_",
            parse_mode="Markdown"
        )

    except Exception as e:
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

        logger.error(f"Ошибка обработки: {e}")
        await processing_msg.edit_text(
            f"❌ *Что-то пошло не так:*\n`{str(e)[:150]}`\n\n"
            f"Попробуй записать голосовое ещё раз.",
            parse_mode="Markdown"
        )


# ========== ВРЕМЕННЫЕ КОМАНДЫ ДЛЯ ТЕСТА (УДАЛИТЬ ПОТОМ) ==========

@dp.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    """ВРЕМЕННО: Выдаёт премиум-подписку пользователю"""
    user_id = message.from_user.id
    if await set_user_subscription(user_id, "premium"):
        await message.answer("✅ **Подписка PREMIUM активирована!**\n\nТеперь вам доступны все функции бота.", parse_mode="Markdown")
    else:
        await message.answer("❌ Ошибка активации подписки. Попробуйте позже.")

@dp.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message):
    """ВРЕМЕННО: Отменяет премиум-подписку пользователя"""
    user_id = message.from_user.id
    if await set_user_subscription(user_id, "free"):
        await message.answer("✅ **Подписка PREMIUM отключена.**\n\nВы вернулись на бесплатный тариф.", parse_mode="Markdown")
    else:
        await message.answer("❌ Ошибка отключения подписки. Попробуйте позже.")

@dp.message(Command("status"))
async def cmd_status(message: Message):
    """Показывает текущий статус подписки"""
    user_id = message.from_user.id
    status = await get_user_subscription(user_id)
    status_text = "🔓 **Бесплатный тариф**" if status == "free" else "🔒 **PREMIUM**"
    await message.answer(f"Ваш статус: {status_text}", parse_mode="Markdown")



# --- Эхо для текстовых сообщений ---
@dp.message()
async def echo_message(message: Message):
    if message.text:
        await message.answer(
            "📝 Ты прислал текст. Чтобы записать сон, отправь, пожалуйста, *голосовое сообщение*."
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


# ========== СИСТЕМА ПОДПИСКИ ==========

async def get_user_subscription(telegram_id: int) -> str:
    """Возвращает статус подписки пользователя ('free' или 'premium')"""
    try:
        response = supabase.table("users").select("subscription_status").eq("telegram_id", telegram_id).execute()
        if response.data:
            return response.data[0].get("subscription_status", "free")
        return "free"
    except Exception as e:
        print(f"❌ Ошибка получения статуса подписки: {e}")
        return "free"

async def set_user_subscription(telegram_id: int, status: str) -> bool:
    """Устанавливает статус подписки ('free' или 'premium')"""
    try:
        supabase.table("users").update({"subscription_status": status}).eq("telegram_id", telegram_id).execute()
        return True
    except Exception as e:
        print(f"❌ Ошибка обновления подписки: {e}")
        return False

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)