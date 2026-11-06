import asyncio
import logging
import time

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
    LabeledPrice, PreCheckoutQuery, SuccessfulPayment,
)

from common import (
    BOT_TOKEN_CASHIER, LOG_CHAT_ID, PROXY_URL,
    PRICE_STARS, DONATE_STARS, log, log_event,
)
from db import (
    db_init, db_grant_access, db_save_donation, db_has_access,
)

router = Router()

def kb_pay() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Оплатить {PRICE_STARS} ⭐", callback_data="pay:access")],
        [InlineKeyboardButton(text=f"💖 Донат {DONATE_STARS} ⭐", callback_data="pay:donate")],
    ])

async def send_access_invoice(bot: Bot, chat_id: int, uid: int) -> None:
    prices = [LabeledPrice(label="Полный доступ к Почтальону", amount=PRICE_STARS)]
    await bot.send_invoice(
        chat_id=chat_id,
        title="Полный доступ к Почтальону",
        description=f"Разовая покупка. Открывает функцию «Почтальон» навсегда. {PRICE_STARS} ⭐",
        payload=f"access:{uid}:{int(time.time())}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )

async def send_donate_invoice(bot: Bot, chat_id: int, uid: int) -> None:
    prices = [LabeledPrice(label="Донат", amount=DONATE_STARS)]
    await bot.send_invoice(
        chat_id=chat_id,
        title="Поддержка проекта",
        description=f"Добровольный донат {DONATE_STARS} ⭐",
        payload=f"donate:{uid}:{int(time.time())}",
        provider_token="",
        currency="XTR",
        prices=prices,
    )

@router.message(CommandStart())
async def cmd_start(msg: Message, command: CommandObject):
    arg = (command.args or "").strip().lower()
    if arg == "donate":
        await send_donate_invoice(msg.bot, msg.chat.id, msg.from_user.id)
        await log_event(msg.bot, "cashier_donate_opened", msg.from_user)
        return

    if await db_has_access(msg.from_user.id):
        await msg.answer("✅ У вас уже есть доступ. Вернитесь в основной бот.")
        return
    await msg.answer(
        f"💳 <b>Оплата доступа</b>\n\n"
        f"Стоимость: <b>{PRICE_STARS} ⭐</b>\n\n"
        f"После оплаты доступ откроется автоматически — "
        f"вернитесь в основной бот и нажмите «📮 Почтальон».",
        reply_markup=kb_pay(),
    )
    await log_event(msg.bot, "cashier_opened", msg.from_user)

@router.callback_query(F.data == "pay:access")
async def cb_pay_access(cb: CallbackQuery):
    if await db_has_access(cb.from_user.id):
        await cb.answer("У вас уже есть доступ ✅", show_alert=True)
        return
    await send_access_invoice(cb.bot, cb.from_user.id, cb.from_user.id)
    await cb.answer()
    await log_event(cb.bot, "cashier_invoice_access", cb.from_user, f"Цена: {PRICE_STARS} ⭐")

@router.callback_query(F.data == "pay:donate")
async def cb_pay_donate(cb: CallbackQuery):
    await send_donate_invoice(cb.bot, cb.from_user.id, cb.from_user.id)
    await cb.answer()
    await log_event(cb.bot, "cashier_invoice_donate", cb.from_user, f"Сумма: {DONATE_STARS} ⭐")

@router.pre_checkout_query()
async def on_pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@router.message(F.successful_payment)
async def on_paid(msg: Message):
    sp: SuccessfulPayment = msg.successful_payment
    payload = sp.invoice_payload or ""

    if payload.startswith("access:"):
        await db_grant_access(msg.from_user.id, sp.telegram_payment_charge_id, sp.total_amount)
        await msg.answer("✅ <b>Оплата получена!</b>\n\nПолный доступ к Почтальону открыт. Перейдите в основной бот и нажмите «📮 Почтальон».")
        await log_event(msg.bot, "cashier_payment_access", msg.from_user, f"Сумма: {sp.total_amount} ⭐\nCharge: <code>{sp.telegram_payment_charge_id}</code>")
        return

    if payload.startswith("donate:"):
        await db_save_donation(msg.from_user.id, sp.total_amount, sp.telegram_payment_charge_id)
        await msg.answer(f"💖 Спасибо за поддержку! Донат {sp.total_amount} ⭐ получен.")
        await log_event(msg.bot, "cashier_donation_received", msg.from_user, f"Сумма: {sp.total_amount} ⭐")
        return

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    await db_init()
    
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else AiohttpSession()
    
    bot = Bot(token=BOT_TOKEN_CASHIER, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    me = await bot.get_me()
    log.info("Кассир подключен: @%s", me.username)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())