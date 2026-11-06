import logging
import os

# ═══════════════════ НАСТРОЙКИ ═══════════════════
# Код берет токен из настроек хостинга (Bot Token), 
# а если его нет — берет из текста ниже
BOT_TOKEN_MAIN    = os.getenv("BOT_TOKEN", "ТОКЕН_ОСНОВНОГО_БОТА_СЮДА")
BOT_TOKEN_CASHIER = os.getenv("BOT_TOKEN", "ТОКЕН_КАССИРА_СЮДА")

CASHIER_USERNAME  = "VeperpCashierBot"  # без @, из @BotFather
CASHIER_URL       = f"https://t.me/VeperpCashierBot"

LOG_CHAT_ID       = -1003943716174     # ID общей лог-группы
ADMIN_IDS         = [421440916] # два админа

PROXY_URL         = None

CHANNEL_URL       = "https://t.me/+G25SaUOrcUUxMDMy"
PRICE_STARS       = 800
DONATE_STARS      = 1


log = logging.getLogger("postman")

async def log_event(bot, event: str, user, extra: str = "") -> None:
    if not LOG_CHAT_ID:
        return
    un = f"@{user.username}" if user.username else "—"
    txt = (f"<b>📮 Лог</b>\nСобытие: <b>{event}</b>\n"
           f"Пользователь: <a href='tg://user?id={user.id}'>{user.full_name}</a>\n"
           f"Username: {un}\nID: <code>{user.id}</code>\n")
    if extra:
        txt += f"\n{extra}"
    try:
        await bot.send_message(LOG_CHAT_ID, txt,
                               parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        log.debug("log fail: %s", e)
