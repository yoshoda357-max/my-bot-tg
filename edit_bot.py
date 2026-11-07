import asyncio
import logging
import json
import os
import re
import sys
import random

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
ADMIN_IDS = [421440916] # ТВОЙ ID

# НАСТРОЙКИ ДЛЯ ЮЗЕРОВ (ЗАГЛУШКА)
CHECK_CHANNEL_ID = "@duckduckcasino" # Юзернейм канала для проверки подписки (бот должен быть там!)
CHECK_CHANNEL_URL = "https://t.me/duckduckcasino" # Ссылка на этот же канал
CASINO_BOT_URL = "https://t.me/duckduckcasinobot"  # Куда вести после подписки

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = "/app/data" if os.path.exists("/app/data") else "."
IMG_DIR = os.path.join(DATA_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)
CHANNELS_FILE = os.path.join(DATA_DIR, "channels.json")

router = Router()

class EditStates(StatesGroup):
    m1_waiting_link = State()
    m1_waiting_template = State()
    m2_waiting_nick = State()
    m2_waiting_link = State()

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
        except Exception:
            pass
    return []

# ═══════════════ КЛАВИАТУРЫ ═══════════════
def kb_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Режим 1: Фото + Текст", callback_data="mode:1")],
        [InlineKeyboardButton(text="🎲 Режим 2: Мини-игра (Ставка)", callback_data="mode:2")]
    ])

def kb_channels(action_prefix):
    channels = get_channels()
    keyboard = []
    for i, ch in enumerate(channels):
        btn_text = ch if len(ch) < 30 else ch[:27] + "..."
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"{action_prefix}:{i}")])
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

def kb_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")]])

# Кнопки для обычных юзеров
def kb_user_start():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎰 Сделать ставку", callback_data="user_bet")]
    ])

def kb_user_subscribe():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHECK_CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="user_check_sub")]
    ])

# ═══════════════ СТАРТ ═══════════════
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    # Если это НЕ админ — показываем заглушку с бонусом
    if msg.from_user.id not in ADMIN_IDS:
        bonus_text = (
            "🎉 <b>Поздравляю!</b>\n\n"
            "Вы получили 3$ (187⭐️) бонусного баланса!"
        )
        try:
            # Пытаемся отправить картинку main.jpg (загрузи её в папку images)
            photo = FSInputFile(os.path.join(IMG_DIR, "main.jpg"))
            await msg.answer_photo(photo=photo, caption=bonus_text, reply_markup=kb_user_start())
        except Exception:
            # Если картинки нет, отправляем просто текст
            await msg.answer(bonus_text, reply_markup=kb_user_start())
        return

    # Если это АДМИН — показываем панель управления
    await state.clear()
    await msg.answer(
        "🛠 <b>Панель управления каналами</b>\n\n"
        "Выберите режим работы:",
        reply_markup=kb_main_menu()
    )

# ═══════════════ ЗАГЛУШКА ДЛЯ ЮЗЕРОВ ═══════════════
@router.callback_query(F.data == "user_bet")
async def cb_user_bet(cb: CallbackQuery):
    # Проверяем подписку на канал
    try:
        member = await cb.bot.get_chat_member(chat_id=CHECK_CHANNEL_ID, user_id=cb.from_user.id)
        if member.status in ["creator", "administrator", "member", "restricted"]:
            # Подписан — ведем в казино
            await cb.message.answer(
                "✅ <b>Подписка подтверждена!</b>\n\n"
                f"Переходите в наше казино, чтобы использовать бонус:\n👉 <a href='{CASINO_BOT_URL}'>Нажмите сюда</a>",
                disable_web_page_preview=True
            )
        else:
            raise Exception("Not a member")
    except Exception:
        # Не подписан или ошибка
        await cb.message.answer(
            "⚠️ <b>Чтобы сделать ставку, вам необходимо подписаться на наш канал!</b>",
            reply_markup=kb_user_subscribe()
        )
    await cb.answer()

@router.callback_query(F.data == "user_check_sub")
async def cb_user_check_sub(cb: CallbackQuery):
    # Проверяем подписку повторно
    try:
        member = await cb.bot.get_chat_member(chat_id=CHECK_CHANNEL_ID, user_id=cb.from_user.id)
        if member.status in ["creator", "administrator", "member", "restricted"]:
            await cb.message.edit_text(
                "✅ <b>Подписка подтверждена!</b>\n\n"
                f"Переходите в наше казино, чтобы использовать бонус:\n👉 <a href='{CASINO_BOT_URL}'>Нажмите сюда</a>",
                disable_web_page_preview=True
            )
        else:
            await cb.answer("❌ Вы всё еще не подписаны на канал!", show_alert=True)
    except Exception:
        await cb.answer("❌ Ошибка проверки. Подпишитесь и попробуйте снова.", show_alert=True)
    await cb.answer()

# ═══════════════ АДМИН: ВЫБОР РЕЖИМА ═══════════════
@router.callback_query(F.data.startswith("mode:"))
async def cb_choose_mode(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    mode = cb.data.split(":")[1]
    await state.update_data(mode=mode)
    action_prefix = "chan1" if mode == "1" else "chan2"
    await cb.message.edit_text(
        f"📌 <b>Режим {mode}</b>\n\nВыберите канал:",
        reply_markup=kb_channels(action_prefix)
    )
    await cb.answer()

@router.callback_query(F.data.startswith("chan1:") | F.data.startswith("chan2:"))
async def cb_channel(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    action, idx = cb.data.split(":")
    idx = int(idx)
    channels = get_channels()
    if idx >= len(channels): return await cb.answer("Ошибка", show_alert=True)
    
    channel = channels[idx]
    await state.update_data(channel_name=channel)
    
    if action == "chan1":
        await state.set_state(EditStates.m1_waiting_link)
        await cb.message.edit_text(f"📌 Канал: <b>{channel}</b>\n\nОтправьте ссылку на сообщение:", reply_markup=kb_cancel())
    else:
        await state.set_state(EditStates.m2_waiting_nick)
        await cb.message.edit_text(f"📌 Канал: <b>{channel}</b>\n\n🎰 Введите любой никнейм игрока:", reply_markup=kb_cancel())
    await cb.answer()

# ═══════════════ РЕЖИМ 1 (ФОТО) ═══════════════
@router.message(EditStates.m1_waiting_link)
async def m1_process_link(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    match = re.search(r't\.me/(?:c/)?([a-zA-Z0-9_]+)/(\d+)', msg.text)
    if not match: return await msg.answer("❌ Неверный формат ссылки.")
    
    channel_from_link = match.group(1)
    message_id = int(match.group(2))
    chat_id = int(f"-100{channel_from_link}") if "t.me/c/" in msg.text else f"@{channel_from_link}"

    await state.update_data(chat_id=chat_id, message_id=message_id)
    await state.set_state(EditStates.m1_waiting_template)
    await msg.answer("📝 Выберите шаблон:", reply_markup=kb_templates())

@router.callback_query(EditStates.m1_waiting_template, F.data.startswith("tpl:"))
async def m1_process_template(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    template_id = cb.data.split(":")[1]
    tpl_data = TEMPLATES.get(template_id)
    data = await state.get_data()
    chat_id, message_id = data.get("chat_id"), data.get("message_id")
    
    channel_link = f"https://t.me/{chat_id.replace('@', '')}" if isinstance(chat_id, str) else f"https://t.me/c/{str(chat_id).replace('-100', '')}"
    final_text = f"{tpl_data['text']}\n\n👉 {channel_link}"
    
    img_path = os.path.join(IMG_DIR, tpl_data['img'])
    photo = FSInputFile(img_path)
    
    await state.clear()
    status_msg = await cb.message.edit_text("⏳ Обрабатываю...")

    try:
        await cb.bot.edit_message_media(
            chat_id=chat_id, message_id=message_id,
            media=InputMediaPhoto(media=photo, caption=final_text, parse_mode="HTML")
        )
        await status_msg.edit_text("✅ <b>Сообщение отредактировано.</b>")
    except Exception:
        try:
            await cb.bot.delete_message(chat_id=chat_id, message_id=message_id)
            await cb.bot.send_photo(chat_id=chat_id, photo=photo, caption=final_text, parse_mode="HTML")
            await status_msg.edit_text("✅ <b>Старое удалено, отправлено новое.</b>")
        except Exception as e2:
            await status_msg.edit_text(f"❌ Ошибка: {e2}")

# ═══════════════ РЕЖИМ 2 (КУБИК) ═══════════════
@router.message(EditStates.m2_waiting_nick)
async def m2_process_nick(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    await state.update_data(nickname=msg.text)
    await state.set_state(EditStates.m2_waiting_link)
    await msg.answer("📝 Теперь отправьте ссылку на сообщение для замены:", reply_markup=kb_cancel())

@router.message(EditStates.m2_waiting_link)
async def m2_process_link(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    match = re.search(r't\.me/(?:c/)?([a-zA-Z0-9_]+)/(\d+)', msg.text)
    if not match: return await msg.answer("❌ Неверный формат ссылки.")

    channel_from_link = match.group(1)
    message_id = int(match.group(2))
    chat_id = int(f"-100{channel_from_link}") if "t.me/c/" in msg.text else f"@{channel_from_link}"

    data = await state.get_data()
    nickname = data.get("nickname")
    await state.clear()
    
    status_msg = await msg.answer("⏳ Генерирую игру...")

    game_mode = random.choice(["Чётное", "Нечётное"])
    dollars = random.randint(1, 5)
    cents = random.randint(10, 99)
    bet_amount = f"${dollars}.{cents}"
    
    game_text = (
        f"🎉 <b>Ваша ставка принята</b>\n"
        f"🔑 Игрок: {nickname} (https://t.me/LudoCasino_bot?start=dXNlcl9pbmZvOjUyOTQz)\n"
        f"🚀 Режим: {game_mode}\n"
        f"💸 Ставка: {bet_amount}"
    )

    try:
        await msg.bot.delete_message(chat_id=chat_id, message_id=message_id)
        await msg.bot.send_message(chat_id=chat_id, text=game_text, parse_mode="HTML", disable_web_page_preview=True)
        await msg.bot.send_dice(chat_id=chat_id, emoji="🎲")
        await status_msg.edit_text("✅ <b>Мини-игра отправлена!</b>")
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка: {e}")

# ═══════════════ ОТМЕНА ═══════════════
@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS: return
    await state.clear()
    await cb.message.edit_text("Отменено.", reply_markup=kb_main_menu())
    await cb.answer()

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    log = logging.getLogger("edit_bot")
    log.info("Бот-редактор (2 режима + заглушка) запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
