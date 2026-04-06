import asyncio
import os
import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application

DB_PATH = os.path.join(os.path.dirname(__file__), "tarot.db")
BOT_LINK = "https://t.me/lesnaya_koloda_mudrosti_bot"

MESSAGE_TEXT = (
    "🌿 Лесной Маг скучает по тебе...\n\n"
    "Давно не заглядывал в лес? Новая карта дня уже ждёт тебя! "
    "Загляни и узнай послание леса 🍃✨"
)


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

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✨ Вытянуть карту", url=BOT_LINK)]]
    )

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
