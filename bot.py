"""
Weltrade Academy Bot
─────────────────────────────────────────────────────
Деплой: Railway
Фреймворк: aiogram 3.x
Python: 3.11+

Что умеет сейчас (MVP):
  /start  — приветствие + кнопка открытия TMA
  /help   — краткая справка
  Webhook от TMA — поздравление при завершении модуля

Следующая итерация:
  - Day-1 / Day-3 retention push
  - Напоминание вернуться если юзер не заходил 48ч
  - Финальный CTA после 5-го модуля
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ─── Config ───────────────────────────────────────────────────────────────────
# Все секреты — через переменные окружения Railway (не хардкодим!)
BOT_TOKEN   = os.environ["BOT_TOKEN"]        # токен от @BotFather
TMA_URL     = os.environ["TMA_URL"]          # https://weltrade-academy.vercel.app
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # https://твой-домен.railway.app
PORT        = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

# ─── Keyboards ────────────────────────────────────────────────────────────────
def kb_open_academy() -> InlineKeyboardMarkup:
    """Кнопка открытия TMA — главная точка входа."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎓 Open Academy",
        web_app=WebAppInfo(url=TMA_URL)
    )
    return builder.as_markup()

def kb_open_and_register() -> InlineKeyboardMarkup:
    """Две кнопки: открыть академию + зарегистрироваться."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎓 Continue Learning",
        web_app=WebAppInfo(url=TMA_URL)
    )
    builder.button(
        text="🚀 Create Account",
        url="https://track.gowt.me/visit/?bta=66558&brand=weltrade&utm_source=telegram_organic&utm_medium=bot&utm_campaign=bot_graduation_cta"
    )
    builder.adjust(1)  # кнопки в столбик
    return builder.as_markup()

# ─── /start ───────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def handle_start(message: types.Message):
    """
    Первое сообщение — знакомство с академией.
    Короткий текст + кнопка TMA. Никакого лишнего текста.
    """
    first_name = message.from_user.first_name or "Trader"

    await message.answer(
        f"Hey {first_name} 👋\n\n"
        f"Welcome to <b>Weltrade Academy</b> — learn trading in short modules, "
        f"earn XP, and get ready for your first real trade.\n\n"
        f"📚 5 modules · ~36 min total · completely free\n\n"
        f"Tap below to start 👇",
        parse_mode="HTML",
        reply_markup=kb_open_academy()
    )

    log.info(f"New user: {message.from_user.id} (@{message.from_user.username})")

# ─── /help ────────────────────────────────────────────────────────────────────
@dp.message(Command("help"))
async def handle_help(message: types.Message):
    await message.answer(
        "🎓 <b>Weltrade Academy</b>\n\n"
        "Learn the basics of Forex trading through bite-sized modules:\n\n"
        "1️⃣ Intro to Markets\n"
        "2️⃣ Reading Charts\n"
        "3️⃣ Risk Management\n"
        "4️⃣ Your First Trade\n"
        "5️⃣ Trading Psychology\n\n"
        "Each module takes 6–8 minutes. Complete all 5 to earn the "
        "<b>Academy Graduate 👑</b> badge.",
        parse_mode="HTML",
        reply_markup=kb_open_academy()
    )

# ─── Webhook от TMA (module_completed) ───────────────────────────────────────
"""
TMA отправляет POST на /tma-webhook когда юзер завершает модуль.
Бот получает сигнал и пишет юзеру поздравление в чат.

Как подключить со стороны TMA:
В engine.js → trackModuleCompleted добавь:

  fetch("/tma-webhook", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id:      tg?.initDataUnsafe?.user?.id,
      module_id:    mod.id,
      module_title: mod.title,
      xp_earned:    mod.totalXP,
      total_xp:     totalXP,
      badge_icon:   mod.badge.icon,
      badge_name:   mod.badge.name,
      is_last:      modIdx === MODULES.length - 1,
    })
  });
"""

MODULE_MESSAGES = {
    "mod_01": "Great start! Markets are no longer a mystery 🌐",
    "mod_02": "You can now read a chart like a pro 📊",
    "mod_03": "Risk management unlocked — the #1 skill of profitable traders 🛡️",
    "mod_04": "You have a real trading process now 🚀",
    "mod_05": "You made it. Most traders never study psychology — you did 👑",
}

async def handle_tma_webhook(request: web.Request) -> web.Response:
    """
    Получаем событие от TMA и отправляем сообщение юзеру в Telegram.
    """
    try:
        data = await request.json()
        user_id      = data.get("user_id")
        module_id    = data.get("module_id")
        module_title = data.get("module_title", "")
        xp_earned    = data.get("xp_earned", 0)
        total_xp     = data.get("total_xp", 0)
        badge_icon   = data.get("badge_icon", "🏅")
        badge_name   = data.get("badge_name", "")
        is_last      = data.get("is_last", False)

        if not user_id:
            return web.json_response({"ok": False, "error": "no user_id"})

        # Кастомный текст для каждого модуля
        flavor = MODULE_MESSAGES.get(module_id, "Module complete!")

        if is_last:
            # Финальное сообщение — максимальный CTA
            text = (
                f"{badge_icon} <b>Academy Graduate!</b>\n\n"
                f"{flavor}\n\n"
                f"You've completed all 5 modules and earned <b>{total_xp} XP</b>.\n\n"
                f"You now have everything you need to start trading. "
                f"Open a real account and make your first trade 👇"
            )
            keyboard = kb_open_and_register()
        else:
            # Промежуточное поздравление
            text = (
                f"{badge_icon} <b>{module_title} complete!</b>\n\n"
                f"{flavor}\n\n"
                f"<b>+{xp_earned} XP</b> earned · Total: <b>{total_xp} XP</b>\n\n"
                f"Ready for the next module? 👇"
            )
            keyboard = kb_open_academy()

        await bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

        log.info(f"Module complete message sent: user={user_id} module={module_id}")
        return web.json_response({"ok": True})

    except Exception as e:
        log.error(f"TMA webhook error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)

# ─── Health check ─────────────────────────────────────────────────────────────
async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "weltrade-academy-bot"})

# ─── App Setup ────────────────────────────────────────────────────────────────
async def on_startup(app: web.Application):
    if WEBHOOK_URL:
        webhook_path = "/webhook"
        await bot.set_webhook(f"{WEBHOOK_URL}{webhook_path}")
        log.info(f"Webhook set: {WEBHOOK_URL}{webhook_path}")
    else:
        log.warning("WEBHOOK_URL not set — running in polling mode")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application()

    # Telegram webhook
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")

    # TMA events webhook
    app.router.add_post("/tma-webhook", handle_tma_webhook)

    # Health check для Railway
    app.router.add_get("/health", handle_health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    setup_application(app, dp, bot=bot)
    return app

# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = create_app()
    log.info(f"Starting bot on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
