import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
    FSInputFile
)

# ═══════════════════ НАСТРОЙКИ ═══════════════════
# Токен будет браться из панели Bothost, либо из текста ниже
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТОКЕН_БОТА_ФИДБЕКА_СЮДА")

# ID группы, КУДА БУДУТ ПРИХОДИТЬ ФИДБЕКИ (например: -1001234567890)
# Обязательно добавь этого бота в ту группу!
FEEDBACK_GROUP_ID = -1001234567890 

# Прокси на Bothost не нужен
PROXY_URL = None 

# ─────────────── ПУТИ К КАРТИНКАМ ───────────────
DATA_DIR = "/app/data" if os.path.exists("/app/data") else "."
IMG_DIR = os.path.join(DATA_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)
IMG_FEEDBACK = FSInputFile(os.path.join(IMG_DIR, "feedback.jpg"))

log = logging.getLogger("feedback_bot")

# ─────────────── СОСТОЯНИЯ ───────────────
class FBState(StatesGroup):
    waiting_for_msg = State()

router = Router()

# ─────────────── КЛАВИАТУРЫ ───────────────
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 FeedBack", callback_data="fb:write")]
    ])

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отменить", callback_data="fb:cancel")]
    ])

# ─────────────── ТЕКСТЫ ───────────────
MAIN_TEXT = (
    "👋 <b>Добро пожаловать!</b>\n\n"
    "Это официальный бот для связи с проектом <b>Veperp</b>.\n\n"
    "Здесь вы можете оставить свой отзыв, предложение или сообщить о проблеме. "
    "Нажмите кнопку ниже, чтобы написать нам. 👇"
)

# ─────────────── ХЕНДЛЕРЫ ───────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    try:
        await msg.answer_photo(
            photo=IMG_FEEDBACK, 
            caption=MAIN_TEXT, 
            reply_markup=kb_main()
        )
    except Exception as e:
        # Если картинки нет, шлем просто текст
        log.error(f"Ошибка загрузки фото: {e}")
        await msg.answer(MAIN_TEXT, reply_markup=kb_main())

@router.callback_query(F.data == "fb:write")
async def cb_write(cb: CallbackQuery, state: FSMContext):
    await state.set_state(FBState.waiting_for_msg)
    await cb.message.edit_text(
        "✍️ <b>Напишите ваше сообщение</b>\n\n"
        "Вы можете отправить текст, фотографию, видео или файл. "
        "Мы обязательно его прочитаем.",
        reply_markup=kb_cancel()
    )
    await cb.answer()

@router.callback_query(F.data == "fb:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
    await cb.message.answer_photo(
        photo=IMG_FEEDBACK, 
        caption=MAIN_TEXT, 
        reply_markup=kb_main()
    )
    await cb.answer("Отменено")

@router.message(FBState.waiting_for_msg)
async def process_feedback(msg: Message, state: FSMContext):
    # Меняем состояние, чтобы не спамил
    await state.clear()
    
    # Показываем пользователю, что сообщение отправляется
    status_msg = await msg.answer("⏳ Отправляем ваше сообщение...")

    try:
        # Формируем шапку для админов в группе
        user_link = f"<a href='tg://user?id={msg.from_user.id}'>{msg.from_user.full_name}</a>"
        username = f"@{msg.from_user.username}" if msg.from_user.username else "—"
        
        header = (
            f"📩 <b>Новый FeedBack</b>\n\n"
            f"От: {user_link}\n"
            f"Username: {username}\n"
            f"ID: <code>{msg.from_user.id}</code>\n\n"
            f"<b>Сообщение:</b>"
        )
        
        # Отправляем шапку в группу
        await msg.bot.send_message(FEEDBACK_GROUP_ID, header, parse_mode="HTML")
        
        # Копируем само сообщение (текст/фото/видео) в группу
        await msg.copy_to(chat_id=FEEDBACK_GROUP_ID)
        
        # Меняем сообщение пользователю
        await status_msg.edit_text(
            "✅ <b>Сообщение успешно отправлено!</b>\n\n"
            "Спасибо за ваш отзыв. Команда проекта Veperp свяжется с вами, если это потребуется."
        )
        
        # (Опционально) Возвращаем кнопку в меню через пару секунд
        await asyncio.sleep(2)
        await msg.answer("Вы можете отправить еще одно сообщение или вернуться в меню:", reply_markup=kb_main())

    except Exception as e:
        log.error(f"Не удалось переслать фидбек: {e}")
        await status_msg.edit_text(
            "❌ <b>Произошла ошибка при отправке.</b>\n\n"
            "Пожалуйста, попробуйте позже или напишите администратору напрямую."
        )

# ─────────────── ТОЧКА ВХОДА ───────────────
async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    )
    
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else AiohttpSession()
    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    me = await bot.get_me()
    log.info("Бот фидбека подключен: @%s", me.username)
    
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
