import os
import random
import sqlite3
import logging
from datetime import date

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


def save_user_card(user_id: int, card_index: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO daily_cards (user_id, last_date, card_index)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_date = excluded.last_date, card_index = excluded.card_index
        """,
        (user_id, get_today_str(), card_index),
    )
    conn.commit()
    conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(BUTTON_TEXT, callback_data="draw_card")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(WELCOME_TEXT, reply_markup=reply_markup)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Твой Telegram ID: `{user_id}`", parse_mode="Markdown")


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
    save_user_card(user_id, card_index)

    card_text = f"*{card['name']}*\n\n{card['description']}"

    image_path = os.path.join(os.path.dirname(__file__), card["image"])
    if os.path.exists(image_path):
        with open(image_path, "rb") as photo:
            await query.message.reply_photo(
                photo=photo,
                caption=card_text,
                parse_mode="Markdown",
            )
    else:
        await query.message.reply_text(card_text, parse_mode="Markdown")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    init_db()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CallbackQueryHandler(draw_card_callback, pattern="^draw_card$"))

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
