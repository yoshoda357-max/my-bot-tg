import logging
import os

# ═══════════════════ НАСТРОЙКИ ═══════════════════
# На хостинге Bothost токен автоматически подставляется в переменную BOT_TOKEN.
# Если ты запускаешь код на компьютере, он возьмет запасной токен из кавычек.

BOT_TOKEN_MAIN     = os.getenv("BOT_TOKEN", "ТОКЕН_ОСНОВНОГО_БОТА")
BOT_TOKEN_CASHIER  = os.getenv("BOT_TOKEN", "ТОКЕН_КАССИРА")
BOT_TOKEN_FEEDBACK = os.getenv("BOT_TOKEN", "ТОКЕН_БОТА_ФИДБЕКА")

# Ссылка на бота-кассира (без @)
CASHIER_USERNAME   = "LunarCashierBot"
CASHIER_URL        = f"https://t.me/VeperpCashierBot"

# ═══════════════════ ГЛАВНЫЕ ID ═══════════════════
# ID твоей группы-лога, куда падают все события и фидбеки
LOG_CHAT_ID        = -1001234567890  

# Твои ID (впиши свои цифры)
ADMIN_IDS          = [421440916]

# Прокси (для Bothost оставляем None, для домашнего ПК вставь строку)
PROXY_URL          = None 
# PROXY_URL        = "socks5://user:pass@host:port"

# ═══════════════════ ТЕКСТЫ И ЦЕНЫ ═══════════════════
CHANNEL_URL        = "https://t.me/+G25SaUOrcUUxMDMy"
PRICE_STARS        = 800
DONATE_STARS       = 1

# ═══════════════════ ЛОГГЕР ═══════════════════
log = logging.getLogger("postman")

async def log_event(bot, event: str, user, extra: str = "") -> None:
    """Отправляет красивое сообщение в группу-лог (LOG_CHAT_ID)"""
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
