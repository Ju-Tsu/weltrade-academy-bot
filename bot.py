"""
Weltrade Academy Bot v3
────────────────────────────────────────────────────────
Новое в v3:
  - startapp параметр: t.me/bot?start=inf_bloger
    → кастомное приветствие + сохранение источника
  - Demo trigger: юзер нажал "Try demo" →
    через 3 дня бот пишет "готов к реальному счёту?"
  - Day 1 / Day 3 retention пуши (из v2)
  - CORS для TMA webhook (из v2)
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ─── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ["BOT_TOKEN"]
TMA_URL     = os.environ["TMA_URL"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT        = int(os.environ.get("PORT", 8080))

REGISTER_URL = (
    "https://track.gowt.me/visit/?bta=66558&brand=weltrade"
    "&utm_source=telegram_organic&utm_medium=bot"
    "&utm_campaign=bot_demo_trigger_cta"
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()

# ─── CORS Middleware ──────────────────────────────────────────────────────────
@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return web.Response(status=200, headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        })
    try:
        response = await handler(request)
    except web.HTTPException as ex:
        response = ex
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# ─── User Storage ─────────────────────────────────────────────────────────────
USERS_FILE = Path("users.json")

def load_users() -> dict:
    try:
        if USERS_FILE.exists():
            return json.loads(USERS_FILE.read_text())
    except Exception:
        pass
    return {}

def save_users(users: dict):
    try:
        USERS_FILE.write_text(json.dumps(users, indent=2))
    except Exception as e:
        log.error(f"Save failed: {e}")

def upsert_user(user_id: int, data: dict):
    users = load_users()
    uid = str(user_id)
    existing = users.get(uid, {})
    existing.update(data)
    users[uid] = existing
    save_users(users)

def get_user(user_id: int) -> dict:
    return load_users().get(str(user_id), {})

# ─── Keyboards ────────────────────────────────────────────────────────────────
def kb_open_academy() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎓 Open Academy", web_app=WebAppInfo(url=TMA_URL))
    return builder.as_markup()

def kb_continue() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶ Continue Learning", web_app=WebAppInfo(url=TMA_URL))
    return builder.as_markup()

def kb_demo_to_real() -> InlineKeyboardMarkup:
    """Кнопки после demo trigger — мост из демо в реальный счёт."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Open Real Account", url=REGISTER_URL)
    builder.button(text="📚 Continue Learning", web_app=WebAppInfo(url=TMA_URL))
    builder.adjust(1)
    return builder.as_markup()

def kb_open_and_register() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="▶ Continue Learning", web_app=WebAppInfo(url=TMA_URL))
    builder.button(text="🚀 Create Account", url=REGISTER_URL)
    builder.adjust(1)
    return builder.as_markup()

# ─── Module data ──────────────────────────────────────────────────────────────
MODULE_TITLES = {
    "mod_01": "Intro to Markets",
    "mod_02": "Reading Charts",
    "mod_03": "Risk Management",
    "mod_04": "Your First Trade",
    "mod_05": "Trading Psychology",
}

MODULE_MESSAGES = {
    "mod_01": "Markets are no longer a mystery 🌐",
    "mod_02": "You can now read a chart like a pro 📊",
    "mod_03": "Risk management unlocked — the #1 skill of profitable traders 🛡️",
    "mod_04": "You have a real trading process now 🚀",
    "mod_05": "Most traders never study psychology — you did 👑",
}

# ─── Influencer name resolver ─────────────────────────────────────────────────
# Маппинг UTM → человекочитаемое имя для кастомного приветствия
# Добавляй новых инфлюенсеров сюда
INFLUENCER_NAMES = {
    # "inf_bloger_name": "Имя блогера",
    # Примеры:
    # "inf_cryptoivan": "Crypto Ivan",
    # "inf_tradingpro": "Trading Pro",
}

def get_influencer_name(source: str) -> str | None:
    """Возвращает имя инфлюенсера по startapp параметру."""
    if source and source.startswith("inf_"):
        return INFLUENCER_NAMES.get(source, source.replace("inf_", "").replace("_", " ").title())
    return None

# ─── /start ───────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def handle_start(message: types.Message):
    user = message.from_user
    first_name = user.first_name or "Trader"
    now = time.time()

    # Извлекаем startapp параметр: /start inf_bloger_name
    args = message.text.split(maxsplit=1)
    start_param = args[1].strip() if len(args) > 1 else ""
    influencer_name = get_influencer_name(start_param)

    upsert_user(user.id, {
        "id":                user.id,
        "first_name":        first_name,
        "username":          user.username or "",
        "started_at":        now,
        "last_seen":         now,
        "current_module":    "mod_01",
        "completed_modules": [],
        "source":            start_param or "organic",
        "day1_push_sent":    False,
        "day3_push_sent":    False,
        "demo_clicked_at":   None,
        "demo_trigger_sent": False,
    })

    # Кастомное приветствие если пришёл от инфлюенсера
    if influencer_name:
        text = (
            f"Hey {first_name} 👋\n\n"
            f"You're here from <b>{influencer_name}</b> — great choice.\n\n"
            f"<b>Weltrade Academy</b> will teach you the basics of trading "
            f"in 5 short modules. Completely free.\n\n"
            f"📚 5 modules · ~36 min · earn XP and badges\n\n"
            f"Tap below to start 👇"
        )
    else:
        text = (
            f"Hey {first_name} 👋\n\n"
            f"Welcome to <b>Weltrade Academy</b> — learn trading in short modules, "
            f"earn XP, and get ready for your first real trade.\n\n"
            f"📚 5 modules · ~36 min total · completely free\n\n"
            f"Tap below to start 👇"
        )

    await message.answer(text, parse_mode="HTML", reply_markup=kb_open_academy())
    log.info(f"New user: {user.id} (@{user.username}) source={start_param or 'organic'}")

# ─── /help ────────────────────────────────────────────────────────────────────
@dp.message(Command("help"))
async def handle_help(message: types.Message):
    await message.answer(
        "🎓 <b>Weltrade Academy</b>\n\n"
        "5 modules · ~36 min total:\n\n"
        "1️⃣ Intro to Markets\n"
        "2️⃣ Reading Charts\n"
        "3️⃣ Risk Management\n"
        "4️⃣ Your First Trade\n"
        "5️⃣ Trading Psychology\n\n"
        "Complete all 5 to earn the <b>Academy Graduate 👑</b> badge.",
        parse_mode="HTML",
        reply_markup=kb_open_academy()
    )

# ─── TMA Webhook ──────────────────────────────────────────────────────────────
async def handle_tma_webhook(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        log.info(f"TMA webhook: {data}")

        user_id   = data.get("user_id")
        event     = data.get("event", "module_completed")
        module_id = data.get("module_id")

        if not user_id:
            return web.json_response({"ok": False, "error": "no user_id"})

        update = {"last_seen": time.time()}

        # ── Юзер открыл модуль ───────────────────────────────────────────────
        if event == "module_opened":
            update["current_module"] = module_id
            update["day1_push_sent"] = True
            upsert_user(int(user_id), update)
            return web.json_response({"ok": True})

        # ── Юзер нажал Demo CTA ───────────────────────────────────────────────
        # Сохраняем время клика — через 3 дня отправим demo trigger
        if event == "demo_cta_clicked":
            update["demo_clicked_at"]   = time.time()
            update["demo_trigger_sent"] = False
            upsert_user(int(user_id), update)
            log.info(f"Demo clicked: user={user_id}")
            return web.json_response({"ok": True})

        # ── Модуль завершён ───────────────────────────────────────────────────
        if event == "module_completed":
            module_title = data.get("module_title", "")
            xp_earned    = data.get("xp_earned", 0)
            total_xp     = data.get("total_xp", 0)
            badge_icon   = data.get("badge_icon", "🏅")
            is_last      = data.get("is_last", False)

            user = get_user(int(user_id))
            completed = user.get("completed_modules", [])
            if module_id not in completed:
                completed.append(module_id)

            module_ids = list(MODULE_TITLES.keys())
            idx = module_ids.index(module_id) if module_id in module_ids else 0
            next_mod = module_ids[idx + 1] if idx + 1 < len(module_ids) else module_id

            update.update({
                "current_module":    next_mod,
                "completed_modules": completed,
                "day1_push_sent":    True,
                "day3_push_sent":    False,
            })
            upsert_user(int(user_id), update)

            flavor = MODULE_MESSAGES.get(module_id, "Module complete!")

            if is_last:
                text = (
                    f"{badge_icon} <b>Academy Graduate!</b>\n\n"
                    f"{flavor}\n\n"
                    f"You've completed all 5 modules and earned <b>{total_xp} XP</b>.\n\n"
                    f"You now have everything you need. Open a real account and make your first trade 👇"
                )
                keyboard = kb_open_and_register()
            else:
                text = (
                    f"{badge_icon} <b>{module_title} complete!</b>\n\n"
                    f"{flavor}\n\n"
                    f"<b>+{xp_earned} XP</b> · Total: <b>{total_xp} XP</b>\n\n"
                    f"Ready for the next module? 👇"
                )
                keyboard = kb_continue()

            await bot.send_message(
                chat_id=user_id, text=text,
                parse_mode="HTML", reply_markup=keyboard
            )
            log.info(f"Module complete sent: user={user_id} module={module_id}")

        return web.json_response({"ok": True})

    except Exception as e:
        log.error(f"TMA webhook error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)

# ─── Demo Trigger ─────────────────────────────────────────────────────────────
async def send_demo_trigger(user: dict):
    """
    Юзер нажал 'Try demo' → через 3 дня спрашиваем готов ли к реальному счёту.
    Это главный мост из демо в FTD.
    """
    uid = user.get("id") or user.get("user_id")
    if not uid:
        log.warning(f"send_demo_trigger: no id in user record")
        return
    first_name = user.get("first_name", "Trader")
    completed_count = len(user.get("completed_modules", []))

    if completed_count >= 3:
        # Прошёл 3+ модуля — уверенный месседж
        text = (
            f"Hey {first_name} 📈\n\n"
            f"You've been on the demo account for a few days — "
            f"and you've completed {completed_count} modules.\n\n"
            f"That means you already know: how markets work, "
            f"how to read charts, and how to manage risk.\n\n"
            f"<b>Most traders who reach this point are ready for a real account.</b>\n\n"
            f"The minimum deposit is small. The knowledge you have is real. 👇"
        )
    else:
        # Прошёл мало модулей — мягче
        text = (
            f"Hey {first_name} 👋\n\n"
            f"How's the demo going?\n\n"
            f"When you feel ready to trade with real money — "
            f"the process takes 2 minutes.\n\n"
            f"Finish the remaining modules first if you want to feel more confident 👇"
        )

    try:
        await bot.send_message(
            chat_id=uid, text=text,
            parse_mode="HTML", reply_markup=kb_demo_to_real()
        )
        upsert_user(uid, {"demo_trigger_sent": True})
        log.info(f"Demo trigger sent: user={uid}")
    except Exception as e:
        log.warning(f"Demo trigger failed {uid}: {e}")

# ─── Retention Pushes ─────────────────────────────────────────────────────────
async def send_day1_push(user: dict):
    uid = user.get("id") or user.get("user_id")
    if not uid:
        log.warning(f"send_day1_push: no id in user record {user}")
        return
    first_name = user.get("first_name", "Trader")
    current_mod = user.get("current_module", "mod_01")
    mod_title = MODULE_TITLES.get(current_mod, "your next module")
    completed_count = len(user.get("completed_modules", []))

    if completed_count == 0:
        text = (
            f"Hey {first_name} 👋\n\n"
            f"You haven't started yet — and that's okay.\n\n"
            f"<b>Intro to Markets</b> takes just 7 minutes. "
            f"Less time than your morning coffee ☕\n\n"
            f"Ready when you are 👇"
        )
    else:
        text = (
            f"Hey {first_name} 👋\n\n"
            f"You left off on <b>{mod_title}</b>.\n\n"
            f"You're {completed_count}/5 modules in — "
            f"keep going and earn your <b>Academy Graduate 👑</b> badge.\n\n"
            f"Takes less than 8 minutes 👇"
        )
    try:
        await bot.send_message(chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb_continue())
        upsert_user(uid, {"day1_push_sent": True})
        log.info(f"Day1 push sent: {uid}")
    except Exception as e:
        log.warning(f"Day1 push failed {uid}: {e}")

async def send_day3_push(user: dict):
    uid = user.get("id") or user.get("user_id")
    if not uid:
        log.warning(f"send_day3_push: no id in user record {user}")
        return
    first_name = user.get("first_name", "Trader")
    current_mod = user.get("current_module", "mod_01")
    mod_title = MODULE_TITLES.get(current_mod, "your next module")

    text = (
        f"Hey {first_name} — still thinking about trading? 📈\n\n"
        f"<b>{mod_title}</b> is waiting for you.\n\n"
        f"Most people who finish all 5 modules make their first trade within a week.\n\n"
        f"You're closer than you think 👇"
    )
    try:
        await bot.send_message(chat_id=uid, text=text, parse_mode="HTML", reply_markup=kb_open_and_register())
        upsert_user(uid, {"day3_push_sent": True})
        log.info(f"Day3 push sent: {uid}")
    except Exception as e:
        log.warning(f"Day3 push failed {uid}: {e}")

# ─── Scheduler ────────────────────────────────────────────────────────────────
async def retention_scheduler():
    """Каждый час проверяем всех юзеров на retention и demo trigger.
    Обёрнут в try/except — краш внутри не убивает планировщик."""
    while True:
        try:
            await asyncio.sleep(3600)
        now = time.time()
        users = load_users()
        log.info(f"Scheduler check: {len(users)} users")

        for uid, user in users.items():
            completed = user.get("completed_modules", [])
            last_seen = user.get("last_seen", now)
            hours_inactive = (now - last_seen) / 3600

            # ── Demo trigger: 3 дня после клика на демо ───────────────────────
            demo_clicked_at = user.get("demo_clicked_at")
            demo_trigger_sent = user.get("demo_trigger_sent", False)

            if (demo_clicked_at
                    and not demo_trigger_sent
                    and (now - demo_clicked_at) >= 72 * 3600):
                await send_demo_trigger(user)
                await asyncio.sleep(0.1)
                continue  # не спамим retention push если уже отправили demo trigger

            # ── Retention пуши (только если не прошёл все модули) ─────────────
            if len(completed) >= 5:
                continue

            if 24 <= hours_inactive < 48 and not user.get("day1_push_sent", False):
                await send_day1_push(user)
                await asyncio.sleep(0.1)
            elif hours_inactive >= 72 and not user.get("day3_push_sent", False):
                await send_day3_push(user)
                await asyncio.sleep(0.1)

# ─── Health ───────────────────────────────────────────────────────────────────
async def handle_health(request: web.Request) -> web.Response:
    users = load_users()
    return web.json_response({
        "status":      "ok",
        "users_total": len(users),
        "service":     "weltrade-academy-bot-v3",
    })

# ─── App ──────────────────────────────────────────────────────────────────────
async def on_startup(app: web.Application):
    if WEBHOOK_URL:
        await bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        log.info(f"Webhook: {WEBHOOK_URL}/webhook")

    # Миграция: фикс старых записей без поля "id"
    users = load_users()
    fixed = 0
    for uid_str, user in users.items():
        if "id" not in user:
            user["id"] = int(uid_str)
            fixed += 1
    if fixed:
        save_users(users)
        log.info(f"Migration: fixed {fixed} user records without 'id' field")

    asyncio.create_task(retention_scheduler())
    log.info("Scheduler started")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()

def create_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    app.router.add_post("/tma-webhook", handle_tma_webhook)
    app.router.add_route("OPTIONS", "/tma-webhook", lambda r: web.Response(
        headers={
            "Access-Control-Allow-Origin":  "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    ))
    app.router.add_get("/health", handle_health)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    setup_application(app, dp, bot=bot)
    return app

if __name__ == "__main__":
    app = create_app()
    log.info(f"Starting on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
