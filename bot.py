import asyncio
import logging
import re
import time
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
    FSInputFile, InputMediaPhoto,
)
from aiogram.exceptions import TelegramBadRequest

import aiosqlite
from common import (
    BOT_TOKEN_MAIN, CASHIER_URL, LOG_CHAT_ID, ADMIN_IDS, PROXY_URL,
    CHANNEL_URL, PRICE_STARS, log, log_event,
)
from db import (
    db_init, db_has_access, db_grant_access,
    db_cooldown, db_mark_run, db_ticket, DB_PATH,
    db_add_user, db_get_all_users,
)

TOTAL_SESSIONS   = 50
SESSION_DURATION = 10.0
PHASE_PROXY_END  = 4.0
PHASE_GEN_END    = 8.0
COOLDOWN_SEC     = 120
MIN_LEN, MAX_LEN = 3, 128

LETTERS = {
    "child":     "📝 Детское письмо",
    "abusive":   "🚨 Оскорбительное письмо",
    "broadcast": "📢 Рассылка писем",
    "personal":  "💌 Личное письмо",
}

USERNAME_RE = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{3,31}$")
GROUP_RE    = re.compile(r"^(https?://)?t\.me/[A-Za-z0-9_+\-]{3,}$", re.I)
ID_RE       = re.compile(r"^-?\d{5,15}$")

router = Router()

# ─────────────── ПУТИ К КАРТИНКАМ ───────────────
DATA_DIR = "/app/data" if os.path.exists("/app/data") else "."
IMG_DIR = os.path.join(DATA_DIR, "images")
os.makedirs(IMG_DIR, exist_ok=True)

IMG_MAIN    = FSInputFile(os.path.join(IMG_DIR, "main.jpg"))
IMG_BUY     = FSInputFile(os.path.join(IMG_DIR, "buy.jpg"))
IMG_ABOUT   = FSInputFile(os.path.join(IMG_DIR, "about.jpg"))
IMG_POSTMAN = FSInputFile(os.path.join(IMG_DIR, "postman.jpg"))

# ─────────────── ТЕКСТЫ ───────────────
MAIN_TEXT = (
    "📬 <b>Добро пожаловать на Почту!</b>\n\n"
    "Здесь вы можете оформить и отправить официальное письмо.\n\n"
    "Что умеет бот — смотрите, нажимая по кнопкам ниже. 👇"
)
ABOUT_TEXT = (
    "📮 <b>Новая Почта</b>\n\n"
    "Наш почтальон уже доставил тысячи успешных писем.\n\n"
    f"💰 Цена за использование — <b>{PRICE_STARS} ⭐</b>\n\n"
    "По оплате переходите по кнопке <b>«💳 Купить бота»</b>."
)

# ─────────────── КЛАВИАТУРЫ ───────────────
async def kb_main(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    if user_id not in ADMIN_IDS and not await db_has_access(user_id):
        rows.append([InlineKeyboardButton(text=f"💳 Купить бота — {PRICE_STARS} ⭐", callback_data="main:buy")])
    rows.append([InlineKeyboardButton(text="ℹ️ О боте", callback_data="main:about")])
    rows.append([InlineKeyboardButton(text="📣 Наш канал", url=CHANNEL_URL)])
    rows.append([InlineKeyboardButton(text="📮 Почтальон", callback_data="main:postman")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main:menu")]])

def kb_tt() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 На группу / канал", callback_data="tt:group")],
        [InlineKeyboardButton(text="👤 На человека",       callback_data="tt:person")],
        [InlineKeyboardButton(text="⬅️ Назад",             callback_data="main:menu")],
    ])

def kb_letters() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=v, callback_data=f"lt:{k}")] for k, v in LETTERS.items()
    ] + [[InlineKeyboardButton(text="⬅️ Назад", callback_data="main:menu")]])

def kb_cancel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✖️ Отменить", callback_data="cancel")]])

def kb_paywall() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Купить доступ — {PRICE_STARS} ⭐", callback_data="main:buy")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main:menu")],
    ])

# ─────────────── ХЕЛПЕР ФОТО ───────────────
async def show_photo(msg: Message, photo: FSInputFile, caption: str, markup, edit: bool = True):
    if edit:
        try:
            await msg.edit_media(media=InputMediaPhoto(media=photo, caption=caption), reply_markup=markup)
            return
        except Exception:
            pass
    await msg.answer_photo(photo=photo, caption=caption, reply_markup=markup)

# ─────────────── АНИМАЦИЯ ───────────────
async def run_sessions(edit_fn, tick: float = 0.25) -> float:
    start_all = time.monotonic()
    total_duration = TOTAL_SESSIONS * SESSION_DURATION
    last = None
    for session_idx in range(TOTAL_SESSIONS):
        session_start = time.monotonic()
        while True:
            in_sess = time.monotonic() - session_start
            if in_sess >= SESSION_DURATION:
                break
            phase = "proxy" if in_sess < PHASE_PROXY_END else "generate" if in_sess < PHASE_GEN_END else "send"
            head = {"proxy": "🔄 Ротация прокси…", "generate": "🤖 Генерация текста…", "send": "📤 Отправка…"}[phase]
            done = session_idx + in_sess / SESSION_DURATION
            filled = int(20 * done / TOTAL_SESSIONS)
            bar = "▰" * filled + "▱" * (20 - filled)
            pct = int(done / TOTAL_SESSIONS * 100)
            elapsed_all = time.monotonic() - start_all
            txt = (f"{head}\n\n<code>[{bar}]</code> {pct}%\n"
                   f"Сессия: <b>{session_idx + 1}/{TOTAL_SESSIONS}</b>\n"
                   f"В сессии: <b>{in_sess:.1f}/10.0 сек</b>\n"
                   f"Общее время: <b>{elapsed_all:.0f}/{int(total_duration)} сек</b>")
            if txt != last:
                try: await edit_fn(txt)
                except Exception: pass
                last = txt
            await asyncio.sleep(tick)
        done = session_idx + 1
        filled = int(20 * done / TOTAL_SESSIONS)
        bar = "▰" * filled + "▱" * (20 - filled)
        txt = (f"✅ Сессия завершена\n\n<code>[{bar}]</code> {int(done/TOTAL_SESSIONS*100)}%\n"
               f"Сессия: <b>{done}/{TOTAL_SESSIONS}</b>\n"
               f"Общее время: <b>{time.monotonic()-start_all:.0f}/{int(total_duration)} сек</b>")
        if txt != last:
            try: await edit_fn(txt)
            except Exception: pass
            last = txt
    return time.monotonic() - start_all

class Flow(StatesGroup):
    target = State()
    letter = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

# ─────────────── СТАРТ ───────────────
@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await db_add_user(msg.from_user.id)
    markup = await kb_main(msg.from_user.id)
    await msg.answer_photo(photo=IMG_MAIN, caption=MAIN_TEXT, reply_markup=markup)
    await log_event(msg.bot, "main_start", msg.from_user)

@router.callback_query(F.data == "main:menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await db_add_user(cb.from_user.id)
    markup = await kb_main(cb.from_user.id)
    await show_photo(cb.message, IMG_MAIN, MAIN_TEXT, markup, edit=True)
    await cb.answer()

@router.callback_query(F.data == "main:about")
async def cb_about(cb: CallbackQuery):
    await show_photo(cb.message, IMG_ABOUT, ABOUT_TEXT, kb_back(), edit=True)
    await cb.answer()
    await log_event(cb.bot, "about_opened", cb.from_user)

@router.callback_query(F.data == "main:buy")
async def cb_buy(cb: CallbackQuery):
    if await db_has_access(cb.from_user.id) or cb.from_user.id in ADMIN_IDS:
        await cb.answer("У вас уже есть полный доступ ✅", show_alert=True)
        try: await cb.message.edit_reply_markup(reply_markup=await kb_main(cb.from_user.id))
        except Exception: pass
        return

    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Перейти к оплате ({PRICE_STARS} ⭐)", url=f"{CASHIER_URL}?start=pay")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="main:menu")],
    ])
    text = ("💳 <b>Оплата доступа</b>\n\n"
            f"Стоимость: <b>{PRICE_STARS} ⭐</b>\n\n"
            "Нажмите кнопку ниже — откроется бот-кассир. После оплаты вернитесь сюда.")
    await show_photo(cb.message, IMG_BUY, text, pay_kb, edit=True)
    await cb.answer()
    await log_event(cb.bot, "redirect_to_cashier", cb.from_user)

@router.callback_query(F.data == "main:postman")
async def cb_postman(cb: CallbackQuery, state: FSMContext):
    if not await db_has_access(cb.from_user.id) and cb.from_user.id not in ADMIN_IDS:
        text = ("🔒 <b>Доступ закрыт</b>\n\n"
                f"Чтобы пользоваться Почтальоном, приобретите доступ за <b>{PRICE_STARS} ⭐</b>.")
        await show_photo(cb.message, IMG_BUY, text, kb_paywall(), edit=True)
        await cb.answer()
        await log_event(cb.bot, "access_denied", cb.from_user)
        return
    
    await state.clear()
    text = "📬 <b>Куда направляем?</b>"
    await show_photo(cb.message, IMG_POSTMAN, text, kb_tt(), edit=True)
    await cb.answer()
    await log_event(cb.bot, "postman_opened", cb.from_user)

@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    markup = await kb_main(cb.from_user.id)
    await show_photo(cb.message, IMG_MAIN, MAIN_TEXT, markup, edit=True)
    await cb.answer()

@router.callback_query(F.data.in_({"tt:group", "tt:person"}))
async def cb_tt(cb: CallbackQuery, state: FSMContext):
    if not await db_has_access(cb.from_user.id) and cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нужна покупка доступа", show_alert=True)
        return
    kind = cb.data.split(":")[1]
    await state.update_data(target_type=kind)
    await state.set_state(Flow.target)
    
    # Меняем текст подсказки: для человека просим ТОЛЬКО ID
    prompt = ("🔗 Ссылка на канал/группу (<code>https://t.me/name</code> или <code>@name</code>).") if kind == "group" else "👤 <b>Числовой ID получателя</b> (только цифры, указывайте точный айди человека иначе жалобы полетят внекуда)."
    
    try: await cb.message.delete()
    except Exception: pass
    await cb.message.answer(prompt, reply_markup=kb_cancel())
    await cb.answer()
    await log_event(cb.bot, "target_type_selected", cb.from_user, f"Тип: {kind}")

@router.message(Flow.target)
async def on_target(msg: Message, state: FSMContext):
    raw = (msg.text or "").strip()
    if not (MIN_LEN <= len(raw) <= MAX_LEN):
        return await msg.answer("❌ Не удалось распознать адрес.")
    
    data = await state.get_data()
    
    # ─────────────── НОРМАЛИЗАЦИЯ ───────────────
    if data.get("target_type") == "group":
        if not GROUP_RE.match(raw):
            return await msg.answer("❌ Не удалось распознать адрес. Отправьте ссылку на канал или группу.")
        target = raw if raw.startswith("http") else f"https://{raw}"
    else:
        # Разрешаем вводить ТОЛЬКО числовой ID
        if not ID_RE.match(raw):
            return await msg.answer("❌ Не удалось распознать адрес. Отправьте <b>только числовой ID</b> (без @ и букв).")
        target = raw

    # ─────────────── ПРОВЕРКА (ТОЛЬКО ДЛЯ ГРУПП/КАНАЛОВ) ───────────────
    if data.get("target_type") == "group":
        if "t.me/+" not in target:
            check_target = "@" + target.split("t.me/")[-1].strip("/") if "t.me/" in target else target
            try:
                await msg.bot.get_chat(check_target)
            except TelegramBadRequest as e:
                if "chat not found" in str(e).lower():
                    return await msg.answer("❌ Такого канала или группы не существует.")
                else:
                    log.warning(f"get_chat error: {e}")
    # Для людей (по ID) проверка пропускается
    # ────────────────────────────────────────────────────────────────────

    left = await db_cooldown(msg.from_user.id, COOLDOWN_SEC)
    if left:
        return await msg.answer(f"⏳ Предыдущее письмо ещё в пути. Повтор через {left} сек.")

    await state.update_data(target=target)
    await state.set_state(Flow.letter)
    await msg.answer("✉️ <b>Выберите тип письма:</b>", reply_markup=kb_letters())
    await log_event(msg.bot, "target_accepted", msg.from_user, f"Цель: <code>{target}</code>")

@router.callback_query(Flow.letter, F.data.startswith("lt:"))
async def cb_letter(cb: CallbackQuery, state: FSMContext):
    if not await db_has_access(cb.from_user.id) and cb.from_user.id not in ADMIN_IDS:
        await cb.answer("Нужна покупка доступа", show_alert=True)
        return
    lt = cb.data.split(":", 1)[1]
    if lt not in LETTERS:
        return await cb.answer("Неизвестный тип", show_alert=True)
    data = await state.get_data()
    await state.clear()
    await log_event(cb.bot, "letter_selected", cb.from_user, f"Цель: <code>{data['target']}</code>\nПисьмо: {LETTERS[lt]}")

    await cb.message.edit_text("📨 Принято в обработку…")
    await cb.answer()

    chat_id, msg_id = cb.message.chat.id, cb.message.message_id

    async def edit_fn(t: str):
        await cb.bot.edit_message_text(text=t, chat_id=chat_id, message_id=msg_id, parse_mode="HTML")

    elapsed = await run_sessions(edit_fn)
    ticket = await db_ticket(cb.from_user.id, data["target_type"], data["target"], lt)
    await db_mark_run(cb.from_user.id)

    final = (f"✅ <b>Отчет о доставке</b>\n\n"
             f"📬 Получатель: <code>{data['target']}</code>\n"
             f"✉️ Тип: {LETTERS[lt]}\n"
             f"📦 Отправлено жалоб: <b>{TOTAL_SESSIONS}</b>\n"
             f"📊 Статус: <b>Доставлено адресату</b>\n"
             f"⏱ Затрачено времени: <b>{elapsed:.0f} сек</b>\n\n"
             f"Квитанция № <code>{ticket}</code>")
    try:
        await cb.bot.edit_message_text(text=final, chat_id=chat_id, message_id=msg_id, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await cb.bot.send_message(chat_id, final, parse_mode="HTML")

    await log_event(cb.bot, "delivery_completed", cb.from_user,
                    f"Квитанция: <code>{ticket}</code>\nЦель: <code>{data['target']}</code>\nТип: {LETTERS[lt]}\nЖалоб: {TOTAL_SESSIONS}\nВремя: {elapsed:.1f} сек")

@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    await state.set_state(BroadcastState.waiting_for_message)
    await msg.answer("📢 <b>Режим рассылки</b>\n\nОтправьте мне сообщение (текст, фото, видео и т.д.), и я перешлю его всем пользователям.\n\nДля отмены напишите /cancel")

@router.message(BroadcastState.waiting_for_message)
async def process_broadcast(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    if msg.text == "/cancel":
        await state.clear()
        return await msg.answer("Рассылка отменена.")

    users = await db_get_all_users()
    if not users:
        await state.clear()
        return await msg.answer("⚠️ В базе пока нет пользователей.")

    status_msg = await msg.answer(f"⏳ Начинаю рассылку на {len(users)} чел...")
    success, blocked = 0, 0
    
    for uid in users:
        try:
            await msg.copy_to(chat_id=uid)
            success += 1
        except Exception as e:
            if "Forbidden" in str(e) or "blocked" in str(e): blocked += 1
            else: log.warning(f"Broadcast fail {uid}: {e}")
        await asyncio.sleep(0.05)

    await state.clear()
    await status_msg.edit_text(f"✅ <b>Рассылка завершена</b>\n\nУспешно доставлено: {success}\nЗаблокировали бота: {blocked}")

@router.message(Command("cancel"))
async def cmd_cancel_broadcast(msg: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None: return
    await state.clear()
    await msg.answer("Действие отменено.")

@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM tickets")
        total = (await cur.fetchone())[0]
        cur = await db.execute("SELECT letter_type, COUNT(*) FROM tickets GROUP BY letter_type")
        rows = await cur.fetchall()
        cur = await db.execute("SELECT COUNT(*), COALESCE(SUM(stars),0) FROM access")
        buyers, stars = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM donations")
        don_count, don_sum = await cur.fetchone()
    txt = (f"<b>Статистика</b>\nВсего писем: {total}\nПокупателей: {buyers}\nЗвёзд собрано: {stars} ⭐\nДонатов: {don_count} на {don_sum} ⭐\n\n<b>По типам:</b>\n")
    for k, v in rows: txt += f"• {LETTERS.get(k, k)}: {v}\n"
    await msg.answer(txt)

@router.message(Command("grant"))
async def cmd_grant(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip().lstrip("-").isdigit():
        return await msg.answer("Использование: /grant <user_id>")
    uid = int(parts[1].strip())
    await db_grant_access(uid, "admin_manual", 0)
    await msg.answer(f"✅ Доступ выдан пользователю <code>{uid}</code>")

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    await db_init()
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else AiohttpSession()
    
    bot = Bot(token=BOT_TOKEN_MAIN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    me = await bot.get_me()
    log.info("Основной бот подключен: @%s", me.username)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())