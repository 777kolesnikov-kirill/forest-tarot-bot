import io
import os
import random
import sqlite3
import logging
from datetime import date, timedelta
from urllib.parse import quote

from PIL import Image

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from cards import CARDS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "tarot.db")

WELCOME_TEXT = (
    "Из глубины леса доносится шелест листьев...\n"
    "А, вот и ты. Я ждал.\n"
    "Меня называют Лесным Магом. Карты не лгут — и я пришёл, чтобы ты это понял.\n"
    "Каждый день лес готовит для тебя одно послание. Одна карта. Одна правда. Этого достаточно.\n"
    "Твоя карта уже ждёт. Ты готов?"
)

ALREADY_GOT_TEXT = "Ты уже получил своё послание сегодня. Лес заговорит снова завтра. 🌿"

BUTTON_TEXT = "✨ Вытянуть карту"

ADMIN_ID = 186890590


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_cards (
            user_id INTEGER NOT NULL,
            last_date TEXT NOT NULL,
            card_index INTEGER NOT NULL,
            PRIMARY KEY (user_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS draw_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            draw_date TEXT NOT NULL,
            card_index INTEGER NOT NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_draw_date ON draw_history (draw_date)"
    )
    conn.commit()
    conn.close()


def get_today_str() -> str:
    return date.today().isoformat()


def get_user_card_today(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_date, card_index FROM daily_cards WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    last_date, card_index = row
    if last_date == get_today_str():
        return CARDS[card_index]
    return None


def delete_user_record(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM daily_cards WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def save_user_card(user_id: int, card_index: int):
    today = get_today_str()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO daily_cards (user_id, last_date, card_index)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_date = excluded.last_date, card_index = excluded.card_index
        """,
        (user_id, today, card_index),
    )
    cursor.execute(
        "INSERT INTO draw_history (user_id, draw_date, card_index) VALUES (?, ?, ?)",
        (user_id, today, card_index),
    )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    today = date.today()
    today_str = today.isoformat()

    week_start = today - timedelta(days=today.weekday())
    week_days = [(week_start + timedelta(days=i)) for i in range(7)]

    month_start = today.replace(day=1).isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM draw_history WHERE draw_date = ?", (today_str,)
    )
    today_count = cursor.fetchone()[0]

    week_counts = {}
    for d in week_days:
        cursor.execute(
            "SELECT COUNT(*) FROM draw_history WHERE draw_date = ?", (d.isoformat(),)
        )
        week_counts[d] = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM draw_history WHERE draw_date >= ?", (month_start,)
    )
    month_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM draw_history")
    unique_users = cursor.fetchone()[0]

    conn.close()

    return {
        "today": today_count,
        "week": week_counts,
        "month": month_count,
        "unique_users": unique_users,
        "today_date": today,
    }


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(BUTTON_TEXT, callback_data="draw_card")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    mage_image = os.path.join(os.path.dirname(__file__), "images", "the Forest Wizard.png")
    if os.path.exists(mage_image):
        img = Image.open(mage_image).convert("RGB")
        img.thumbnail((1280, 1280), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        await update.message.reply_photo(
            photo=buf,
            caption=WELCOME_TEXT,
            reply_markup=reply_markup,
        )
    else:
        await update.message.reply_text(WELCOME_TEXT, reply_markup=reply_markup)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Твой Telegram ID: `{user_id}`", parse_mode="Markdown")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return

    s = get_stats()

    day_names = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
    today = s["today_date"]

    week_lines = []
    for d, count in s["week"].items():
        marker = " ◀ сегодня" if d == today else ""
        week_lines.append(f"  {day_names[d.weekday()]} {d.strftime('%d.%m')}: {count}{marker}")
    week_text = "\n".join(week_lines)

    text = (
        f"📊 *Статистика Лесного Мага*\n\n"
        f"📅 *Сегодня* ({today.strftime('%d.%m.%Y')}): {s['today']} карт\n\n"
        f"📆 *Эта неделя:*\n{week_text}\n\n"
        f"🗓 *Этот месяц:* {s['month']} карт\n\n"
        f"👥 *Всего уникальных пользователей:* {s['unique_users']}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return
    delete_user_record(ADMIN_ID)
    await update.message.reply_text("✅ Готово. Лимит сброшен — ты можешь вытянуть карту снова.")


async def draw_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    existing_card = get_user_card_today(user_id)
    if existing_card is not None:
        await query.message.reply_text(ALREADY_GOT_TEXT)
        return

    card_index = random.randint(0, len(CARDS) - 1)
    card = CARDS[card_index]

    card_text = f"*{card['name']}*\n\n{card['description']}"

    share_text = (
        f"Сегодня Лесной Маг дал мне карту «{card['name']}» 🌿 "
        f"Получи своё послание от леса: t.me/lesnaya_koloda_mudrosti_bot"
    )
    share_url = (
        "https://t.me/share/url"
        f"?url=https%3A%2F%2Ft.me%2Flesnaya_koloda_mudrosti_bot"
        f"&text={quote(share_text)}"
    )
    share_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌿 Поделиться с другом", url=share_url)]]
    )

    image_path = os.path.join(os.path.dirname(__file__), card["image"])
    if os.path.exists(image_path):
        img = Image.open(image_path).convert("RGB")
        img.thumbnail((1280, 1280), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        await query.message.reply_photo(
            photo=buf,
            caption=card_text,
            parse_mode="Markdown",
            reply_markup=share_keyboard,
        )
    else:
        await query.message.reply_text(
            card_text,
            parse_mode="Markdown",
            reply_markup=share_keyboard,
        )

    save_user_card(user_id, card_index)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    init_db()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CallbackQueryHandler(draw_card_callback, pattern="^draw_card$"))

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
