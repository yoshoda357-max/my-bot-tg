import asyncio
import logging
import json
import os
import re
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
    FSInputFile, InputMediaPhoto
)

# ─────────────── НАСТРОЙКИ ───────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_ДЛЯ_ЛОКАЛЬНОГО_ТЕСТА")
ADMIN_IDS = [421440916] # ЗАМЕНИ НА СВОЙ ID

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = "/app/data" if os.path.exists("/app/data") else "."
IMG_DIR = os.path.join(DATA_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)
CHANNELS_FILE = os.path.join(DATA_DIR, "channels.json")

router = Router()

class EditStates(StatesGroup):
    waiting_link = State()
    waiting_template = State()

TEMPLATES = {
    "1": {"text": "coc mef and more drugs only here", "img": "img1.jpg"},
    "2": {"text": "best narcoshop", "img": "img2.jpg"},
    "3": {"text": "buy drugs only here", "img": "img3.jpg"}
}

def get_channels():
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("channels", [])
        except Exception as e:
            logging.error(f"Ошибка чтения channels.json: {e}")
    return []

def kb_channels():
    channels = get_channels()
    keyboard = []
    for i, ch in enumerate(channels):
        keyboard.append([InlineKeyboardButton(text=ch, callback_data=f"chan:{i}")])
    
    if not keyboard:
        keyboard.append([InlineKeyboardButton(text="❌ Нет каналов в JSON", callback_data="none")])
        
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def kb_templates():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Шаблон 1 (coc mef...)", callback_data="tpl:1")],
        [InlineKeyboardButton(text="Шаблон 2 (best narcoshop)", callback_data="tpl:2")],
        [InlineKeyboardButton(text="Шаблон 3 (buy drugs...)", callback_data="tpl:3")],
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")]
    ])

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    
    await state.clear()
    await msg.answer(
        "🛠 <b>Панель управления каналами</b>\n\n"
        "Выберите канал, в котором нужно отредактировать сообщение:",
        reply_markup=kb_channels()
    )

@router.callback_query(F.data.startswith("chan:"))
async def cb_channel(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        return

    idx = int(cb.data.split(":", 1)[1])
    channels = get_channels()
    
    if idx >= len(channels):
        return await cb.answer("Ошибка: канал не найден", show_alert=True)
        
    channel = channels[idx]
    await state.update_data(channel_name=channel)
    await state.set_state(EditStates.waiting_link)
    
    await cb.message.edit_text(
        f"📌 Выбран канал: <b>{channel}</b>\n\n"
        "Отправьте ссылку на <b>сообщение</b> внутри этого канала.\n\n"
        "Для публичных: <code>https://t.me/channel_2/123</code>\n"
        "Для приватных: <code>https://t.me/c/123456789/123</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")]])
    )
    await cb.answer()

@router.message(EditStates.waiting_link)
async def process_link(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return

    match = re.search(r't\.me/(?:c/)?([a-zA-Z0-9_]+)/(\d+)', msg.text)
    if not match:
        return await msg.answer("❌ Неверный формат ссылки. Отправьте ссылку вида <code>https://t.me/channel/123</code>")

    channel_from_link = match.group(1)
    message_id = int(match.group(2))
    
    if "t.me/c/" in msg.text:
        chat_id = int(f"-100{channel_from_link}")
        channel_link = f"https://t.me/c/{channel_from_link}"
    else:
        chat_id = f"@{channel_from_link}"
        channel_link = f"https://t.me/{channel_from_link}"

    await state.update_data(chat_id=chat_id, message_id=message_id, channel_link=channel_link)
    await state.set_state(EditStates.waiting_template)

    await msg.answer(
        f"📝 Ссылка принята (ID сообщения: {message_id}).\n\n"
        "Выберите шаблон для замены:",
        reply_markup=kb_templates()
    )

@router.callback_query(EditStates.waiting_template, F.data.startswith("tpl:"))
async def process_template(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        return

    template_id = cb.data.split(":")[1]
    tpl_data = TEMPLATES.get(template_id)
    
    if not tpl_data:
        return await cb.message.edit_text("❌ Ошибка шаблона.")

    data = await state.get_data()
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    channel_link = data.get("channel_link")
    
    final_text = f"{tpl_data['text']}\n\n👉 {channel_link}"
    
    img_path = os.path.join(IMG_DIR, tpl_data['img'])
    if not os.path.exists(img_path):
        return await cb.message.edit_text(f"❌ Ошибка: Файл {tpl_data['img']} не найден.")
        
    photo = FSInputFile(img_path)
    
    await state.clear()
    status_msg = await cb.message.edit_text("⏳ Пытаюсь отредактировать сообщение...")

    try:
        # ПЫТАЕМСЯ ОТРЕДАКТИРОВАТЬ (Сработает, если сообщение было с фото)
        await cb.bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=InputMediaPhoto(media=photo, caption=final_text),
            parse_mode="HTML"
        )
        await status_msg.edit_text("✅ <b>Успешно! Сообщение отредактировано.</b>")
        
    except Exception as e:
        # ЕСЛИ ОШИБКА, ПОКАЗЫВАЕМ ЕЁ ТЕБЕ
        error_text = str(e)
        await status_msg.edit_text(
            f"⚠️ <b>Telegram запретил редактирование!</b>\n\n"
            f"Текст ошибки:\n<code>{error_text}</code>\n\n"
            f"<i>Пробую удалить старое и отправить новое...</i>"
        )
        
        try:
            await cb.bot.delete_message(chat_id=chat_id, message_id=message_id)
            await cb.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=final_text,
                parse_mode="HTML"
            )
            await status_msg.edit_text(
                f"✅ <b>Старое сообщение удалено, отправлено новое.</b>\n\n"
                f"(Причина, по которой не удалось отредактировать: <code>{error_text}</code>)"
            )
        except Exception as e2:
            await status_msg.edit_text(f"❌ Ошибка при удалении/отправке: {e2}")

@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await cb.message.edit_text("Отменено.", reply_markup=kb_channels())
    await cb.answer()

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    log = logging.getLogger("edit_bot")
    log.info("Бот-редактор запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
