import asyncio
import os
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

DB_PATH = os.path.join(os.path.dirname(__file__), "tarot.db")
BOT_DRAW_LINK = "https://t.me/lesnaya_koloda_mudrosti_bot?start=draw"

MESSAGE_TEXT = (
    "🌿 Привет! Я обновился.\n\n"
    "Теперь я работаю 24/7 — даже ночью и в выходные. "
    "Можешь вытянуть карту в любой момент 🍃✨"
)

REMINDER_TIMES = [
    ("🌅 08:00", "08:00"),
    ("☀️ 10:00", "10:00"),
    ("🌞 12:00", "12:00"),
    ("🌆 18:00", "18:00"),
    ("🌙 20:00", "20:00"),
    ("🌛 22:00", "22:00"),
]


def build_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("✨ Вытянуть карту", callback_data="draw_card")]]
    return InlineKeyboardMarkup(rows)


def get_all_user_ids():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM draw_history")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


async def broadcast():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    user_ids = get_all_user_ids()
    print(f"Found {len(user_ids)} users to notify.")

    keyboard = build_keyboard()

    app = Application.builder().token(token).build()
    async with app:
        sent = 0
        failed = 0
        for user_id in user_ids:
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text=MESSAGE_TEXT,
                    reply_markup=keyboard,
                )
                print(f"✓ Sent to {user_id}")
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                print(f"✗ Failed for {user_id}: {e}")
                failed += 1

    print(f"\nDone. Sent: {sent}, Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(broadcast())
