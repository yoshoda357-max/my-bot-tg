import logging
import os

# ═══════════════════ НАСТРОЙКИ ═══════════════════
BOT_TOKEN_MAIN     = os.getenv("BOT_TOKEN", "123456:ТОКЕН_ОСНОВНОГО")
BOT_TOKEN_CASHIER  = os.getenv("BOT_TOKEN", "654321:ТОКЕН_КАССИРА")
BOT_TOKEN_FEEDBACK = os.getenv("BOT_TOKEN", "111111:ТОКЕН_ФИДБЕКА") # <--- ДОБАВИЛИ

CASHIER_USERNAME  = "LunarCashierBot"
CASHIER_URL       = f"https://t.me/VeperpCashierBot"

LOG_CHAT_ID       = -1001234567890     # ID лог-группы
ADMIN_IDS         = [421440916]

PROXY_URL         = None 

CHANNEL_URL       = "https://t.me/+G25SaUOrcUUxMDMy"
PRICE_STARS       = 800
DONATE_STARS      = 1

log = logging.getLogger("postman")

async def log_event(bot, event: str, user, extra: str = "") -> None:
    # ... (код функции log_event оставляем без изменений)
