import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
    FSInputFile
)
import aiosqlite

from common import BOT_TOKEN_FEEDBACK, LOG_CHAT_ID, PROXY_URL, log

DATA_DIR = "/app/data" if os.path.exists("/app/data") else "."
IMG_DIR = os.path.join(DATA_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)
IMG_FEEDBACK = FSInputFile(os.path.join(IMG_DIR, "feedback.jpg"))

DB_PATH = os.path.join(DATA_DIR, "feedback.db")

class FBState(StatesGroup):
    waiting_for_msg = State()

router = Router()

async def init_fb_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS fb_links(
            group_msg_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL)""")
        await db.commit()

async def save_link(group_msg_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO fb_links(group_msg_id, user_id) VALUES(?,?)", (group_msg_id, user_id))
        await db.commit()

async def get_user_id(group_msg_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM fb_links WHERE group_msg_id=?", (group_msg_id,))
        row = await cur.fetchone()
        return row[0] if row else None

def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 FeedBack", callback_data="fb:write")]
    ])

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отменить", callback_data="fb:cancel")]
    ])

MAIN_TEXT = (
    "👋 <b>Добро пожаловать!</b>\n\n"
    "Это официальный бот для связи с проектом <b>Veperp</b>.\n\n"
    "Здесь вы можете оставить свой отзыв, предложение или сообщить о проблеме. "
    "Нажмите кнопку ниже, чтобы написать нам. 👇"
)

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    try:
        await msg.answer_photo(photo=IMG_FEEDBACK, caption=MAIN_TEXT, reply_markup=kb_main())
    except Exception as e:
        log.error(f"Ошибка загрузки фото: {e}")
        await msg.answer(MAIN_TEXT, reply_markup=kb_main())

@router.callback_query(F.data == "fb:write")
async def cb_write(cb: CallbackQuery, state: FSMContext):
    await state.set_state(FBState.waiting_for_msg)
    await cb.message.edit_text(
        "✍️ <b>Напишите ваше сообщение</b>\n\n"
        "Вы можете отправить текст, фотографию, видео или файл. Мы обязательно его прочитаем.",
        reply_markup=kb_cancel()
    )
    await cb.answer()

@router.callback_query(F.data == "fb:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await cb.message.delete()
    except Exception: pass
    await cb.message.answer_photo(photo=IMG_FEEDBACK, caption=MAIN_TEXT, reply_markup=kb_main())
    await cb.answer("Отменено")

# ─────────────── ПРИЕМ ФИДБЕКА ОТ ЮЗЕРА ───────────────
@router.message(FBState.waiting_for_msg)
async def process_feedback(msg: Message, state: FSMContext):
    await state.clear()
    status_msg = await msg.answer("⏳ Отправляем ваше сообщение...")

    try:
        user_link = f"<a href='tg://user?id={msg.from_user.id}'>{msg.from_user.full_name}</a>"
        username = f"@{msg.from_user.username}" if msg.from_user.username else "скрыт"
        
        header = (
            f"📩 <b>Новый FeedBack</b>\n\n"
            f"👤 <b>От:</b> {user_link}\n"
            f"🔗 <b>Юзернейм:</b> {username}\n"
            f"🆔 <b>ID:</b> <code>{msg.from_user.id}</code>\n\n"
            f"💬 <b>Сообщение:</b>\n"
            f"<i>(Чтобы ответить, сделайте Reply на ЭТО сообщение)</i>"
        )
        
        # Сохраняем в БД шапку
        header_msg = await msg.bot.send_message(LOG_CHAT_ID, header, parse_mode="HTML")
        await save_link(header_msg.message_id, msg.from_user.id)
        
        # Сохраняем в БД само скопированное сообщение
        copied_msg = await msg.copy_to(chat_id=LOG_CHAT_ID)
        await save_link(copied_msg.message_id, msg.from_user.id)
        
        await status_msg.edit_text(
            "✅ <b>Сообщение успешно отправлено!</b>\n\n"
            "Спасибо за ваш отзыв. Команда проекта Veperp свяжется с вами."
        )
        
        await asyncio.sleep(2)
        await msg.answer("Вы можете отправить еще одно сообщение или вернуться в меню:", reply_markup=kb_main())

    except Exception as e:
        log.error(f"Не удалось переслать фидбек: {e}")
        await status_msg.edit_text(f"❌ <b>Ошибка:</b>\n<code>{e}</code>")

# ─────────────── ОТВЕТ АДМИНА ИЗ ГРУППЫ ───────────────
@router.message(F.chat.id == LOG_CHAT_ID, F.reply_to_message)
async def handle_admin_reply(msg: Message):
    log.info(f"Поймал сообщение в группе. Reply на msg_id: {msg.reply_to_message.message_id}")
    
    # Ищем ID пользователя в базе, на чье сообщение ответил админ
    target_user_id = await get_user_id(msg.reply_to_message.message_id)
    
    if not target_user_id:
        # Если это не наш фидбек, просто игнорируем
        return
        
    try:
        await msg.copy_to(chat_id=target_user_id)
        await msg.reply("✅ Ответ успешно отправлен пользователю!")
        log.info(f"Ответ отправлен юзеру {target_user_id}")
    except Exception as e:
        await msg.reply(f"❌ Ошибка: пользователь заблокировал бота.\n<code>{e}</code>")
        log.error(f"Ошибка отправки юзеру {target_user_id}: {e}")

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    await init_fb_db() # Инициализация базы фидбека
    
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else AiohttpSession()
    bot = Bot(token=BOT_TOKEN_FEEDBACK, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
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
