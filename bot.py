import os
import sys
import logging
import asyncio
import threading
import aiohttp
from io import BytesIO
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InputFile, BufferedInputFile
from fastapi import FastAPI
import uvicorn
from groq import Groq
from supabase import create_client, Client
from huggingface_hub import InferenceClient

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

logger.info("🚀 Запуск бота...")

# --- Проверка переменных ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")

if not BOT_TOKEN:
    logger.error("❌ ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)
if not GROQ_API_KEY:
    logger.error("❌ ОШИБКА: GROQ_API_KEY не найден!")
    sys.exit(1)
if not SUPABASE_URL or not SUPABASE_KEY:
    logger.warning("⚠️ Supabase не настроен. База данных не будет работать.")

# --- Инициализация бота и клиентов ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logger.info("✅ Бот инициализирован")

groq_client = Groq(api_key=GROQ_API_KEY)

# --- Инициализация Supabase ---
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Supabase подключен")

# --- Инициализация Hugging Face ---
if not HUGGINGFACE_TOKEN:
    logger.warning("⚠️ HUGGINGFACE_TOKEN не найден. Генерация картинок недоступна.")

# ========== ФУНКЦИИ РАБОТЫ С БАЗОЙ ==========

async def register_user(telegram_id: int, username: str = None):
    """Добавляет нового пользователя в таблицу users, если его там нет."""
    if not supabase:
        return
    try:
        response = supabase.table("users").select("id").eq("telegram_id", telegram_id).execute()
        if not response.data:
            supabase.table("users").insert({
                "telegram_id": telegram_id,
                "username": username
            }).execute()
            logger.info(f"✅ Новый пользователь {telegram_id} добавлен в базу!")
        else:
            logger.info(f"ℹ️ Пользователь {telegram_id} уже существует")
    except Exception as e:
        logger.error(f"❌ Ошибка базы данных: {e}")

async def save_dream(user_id: int, raw_text: str, polished_text: str):
    """Сохраняет сон в базу данных"""
    if not supabase:
        return
    try:
        user_response = supabase.table("users").select("id").eq("telegram_id", user_id).execute()
        if user_response.data:
            db_user_id = user_response.data[0]['id']
            supabase.table("dreams").insert({
                "user_id": db_user_id,
                "raw_text": raw_text,
                "polished_text": polished_text
            }).execute()
            logger.info(f"✅ Сон пользователя {user_id} сохранен!")
        else:
            logger.warning(f"⚠️ Пользователь {user_id} не найден в базе")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения сна: {e}")

async def get_user_subscription(telegram_id: int) -> str:
    """Возвращает статус подписки пользователя ('free' или 'premium')"""
    if not supabase:
        return "free"
    try:
        response = supabase.table("users").select("subscription_status").eq("telegram_id", telegram_id).execute()
        if response.data:
            return response.data[0].get("subscription_status", "free")
        return "free"
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса подписки: {e}")
        return "free"

async def set_user_subscription(telegram_id: int, status: str) -> bool:
    """Устанавливает статус подписки ('free' или 'premium')"""
    if not supabase:
        return False
    try:
        supabase.table("users").update({"subscription_status": status}).eq("telegram_id", telegram_id).execute()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка обновления подписки: {e}")
        return False

# ========== ГЕНЕРАЦИЯ КАРТИНОК ==========

async def generate_image(prompt: str) -> BytesIO | None:
    """Генерирует изображение через бесплатный Inference API Hugging Face."""
    HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
    if not HF_TOKEN:
        logger.warning("⚠️ HUGGINGFACE_TOKEN не найден.")
        return None

    try:
        client = InferenceClient(token=HF_TOKEN)
        enhanced_prompt = f"Dreamy surreal atmosphere, soft watercolor style, mystical and ethereal. {prompt[:150]}"
        
        logger.info("🎨 Отправка запроса в HF Serverless API...")

        # Выполняем синхронный вызов в асинхронном контексте
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.text_to_image(
            prompt=enhanced_prompt,
            model="black-forest-labs/FLUX.1-schnell")
        )

        # Проверяем тип результата и преобразуем в байты
        if result:
            # Если это объект Pillow Image, преобразуем его в BytesIO
            if hasattr(result, 'save'):
                img_bytes = BytesIO()
                result.save(img_bytes, format='PNG')
                img_bytes.seek(0)
                logger.info("✅ Картинка преобразована в BytesIO")
                return img_bytes
            # Если это уже байты
            elif isinstance(result, bytes):
                logger.info(f"✅ Картинка получена (байты), размер: {len(result)} байт")
                return BytesIO(result)
            # Если это уже BytesIO
            elif isinstance(result, BytesIO):
                result.seek(0)
                logger.info(f"✅ Картинка получена (BytesIO), размер: {len(result.getvalue())} байт")
                return result
            else:
                logger.warning(f"⚠️ Неизвестный тип результата: {type(result)}")
                return None
        else:
            logger.error("❌ API не вернул данные")
            return None

    except Exception as e:
        logger.error(f"❌ Ошибка генерации через HF API: {e}")
        return None
# ========== КОМАНДЫ БОТА ==========

@dp.message(Command("start"))
async def start_command(message: Message):
    user_name = message.from_user.first_name
    await register_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Привет, {user_name}! 🎙️🌙\n\n"
        "Я — твой волшебный дневник снов.\n"
        "Просто отправь мне голосовое сообщение с рассказом о своём сне, "
        "и я расшифрую его.\n\n"
        "✨ Премиум-функции (красивая обработка и картинки) доступны по команде /subscribe (временно бесплатно!)"
    )

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

# ========== ОСНОВНОЙ ОБРАБОТЧИК ГОЛОСОВЫХ ==========

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
                f"💡 Хочешь красивое описание и иллюстрацию? Используй команду /subscribe (временно бесплатно!)",
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

        # 7. Сохраняем сон в базу
        await save_dream(message.from_user.id, raw_text, polished_dream)

        # 8. Отправка текста и картинки
        await processing_msg.edit_text("🎨 Генерирую иллюстрацию к твоему сну...")

        # Генерируем картинку
        image_bytes = await generate_image(f"A dream about: {raw_text[:200]}")

        try:
            # Отправляем текст сна
            await message.answer(
                f"🌙 *Твой сон в красивом пересказе:*\n\n{polished_dream}",
                parse_mode="Markdown"
            )
            
            # Отправляем картинку отдельно (без подписи)
            if image_bytes:
                if isinstance(image_bytes, BytesIO):
                    image_bytes.seek(0)
                    photo_file = BufferedInputFile(
                        image_bytes.getvalue(),
                        filename="dream.png"
                    )
                elif isinstance(image_bytes, bytes):
                    photo_file = BufferedInputFile(
                        image_bytes,
                        filename="dream.png"
                    )
                else:
                    photo_file = None
                
                if photo_file:
                    await message.answer_photo(
                        photo=photo_file,
                        caption=None
                    )
                else:
                    await message.answer("⚠️ Не удалось сгенерировать картинку для этого сна.")
            else:
                await message.answer("⚠️ Не удалось сгенерировать картинку для этого сна.")
                
        except Exception as e:
            logger.error(f"Ошибка отправки картинки: {e}")
            await message.answer("⚠️ Произошла ошибка при отправке картинки, но твой сон готов.")
    
    except Exception as e:
    # Обработка ошибок
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
    
    # Используем e только внутри except
    error_message = str(e) if 'e' in locals() else "Неизвестная ошибка"
    logger.error(f"Ошибка обработки: {error_message}")
    
    await processing_msg.edit_text(
        f"❌ *Что-то пошло не так:*\n`{error_message[:150]}`\n\n"
        f"Попробуй записать голосовое ещё раз.",
        parse_mode="Markdown"
    )
# ========== ОБРАБОТЧИК ТЕКСТА (должен быть ПОСЛЕ всех команд) ==========

@dp.message(lambda message: message.text and not message.text.startswith('/'))
async def echo_message(message: Message):
    await message.answer(
        "📝 Ты прислал текст. Чтобы записать сон, отправь, пожалуйста, **голосовое сообщение**."
    )

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========

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

# ========== ЗАПУСК БОТА ==========

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