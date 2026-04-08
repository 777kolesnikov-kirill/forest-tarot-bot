import io
import os
import random
import sqlite3
import logging
from datetime import date, timedelta, datetime, time as dt_time, timezone
from urllib.parse import quote

from PIL import Image

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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

BOT_USERNAME = "lesnaya_koloda_mudrosti_bot"
BOT_LINK = f"https://t.me/{BOT_USERNAME}"

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

REMINDER_TIMES = [
    ("🌅 08:00", "08:00"),
    ("☀️ 10:00", "10:00"),
    ("🌞 12:00", "12:00"),
    ("🌆 18:00", "18:00"),
    ("🌙 20:00", "20:00"),
    ("🌛 22:00", "22:00"),
]

REMINDER_PROMPT_TEXT = "🔔 Хочешь получать напоминание каждый день?"

REMINDER_TEXT = (
    "🌿 Лесной Маг зовёт тебя...\n"
    "Новая карта дня уже ждёт.\n"
    "Загляни в лес 🍃"
)

# Moscow time slots → UTC (MSK = UTC+3)
REMINDER_SLOTS = [
    ("08:00",  5, 0, False),
    ("10:00",  7, 0, False),
    ("12:00",  9, 0, True),
    ("18:00", 15, 0, False),
    ("20:00", 17, 0, False),
    ("22:00", 19, 0, False),
]


def build_reminder_time_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for label, t in REMINDER_TIMES:
        row.append(InlineKeyboardButton(label, callback_data=f"rtime_{t}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🚫 Нет, спасибо", callback_data="reminder_no")])
    return InlineKeyboardMarkup(rows)


# ── Database ──────────────────────────────────────────────────────────────────

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
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            user_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            reminder_time TEXT,
            last_reminded TEXT
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


def set_reminder(user_id: int, reminder_time: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO reminders (user_id, enabled, reminder_time)
        VALUES (?, 1, ?)
        ON CONFLICT(user_id) DO UPDATE SET enabled = 1, reminder_time = excluded.reminder_time
        """,
        (user_id, reminder_time),
    )
    conn.commit()
    conn.close()


def disable_reminder(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reminders SET enabled = 0 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def get_user_reminder(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT enabled, reminder_time FROM reminders WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def get_users_for_slot(slot_time: str, include_no_preference: bool, today_str: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if include_no_preference:
        cursor.execute(
            """
            SELECT DISTINCT dh.user_id
            FROM draw_history dh
            LEFT JOIN reminders r ON dh.user_id = r.user_id
            WHERE (
                (r.enabled = 1 AND r.reminder_time = ?)
                OR (r.user_id IS NULL)
                OR (r.enabled = 0)
            )
            AND COALESCE(r.last_reminded, '') != ?
            """,
            (slot_time, today_str),
        )
    else:
        cursor.execute(
            """
            SELECT user_id FROM reminders
            WHERE enabled = 1
              AND reminder_time = ?
              AND (last_reminded IS NULL OR last_reminded != ?)
            """,
            (slot_time, today_str),
        )
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def mark_reminder_sent(user_id: int, today_str: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO reminders (user_id, enabled, last_reminded)
        VALUES (?, 0, ?)
        ON CONFLICT(user_id) DO UPDATE SET last_reminded = excluded.last_reminded
        """,
        (user_id, today_str),
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

    cursor.execute("SELECT COUNT(*) FROM draw_history WHERE draw_date = ?", (today_str,))
    today_count = cursor.fetchone()[0]

    week_counts = {}
    for d in week_days:
        cursor.execute("SELECT COUNT(*) FROM draw_history WHERE draw_date = ?", (d.isoformat(),))
        week_counts[d] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM draw_history WHERE draw_date >= ?", (month_start,))
    month_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM draw_history")
    unique_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reminders WHERE enabled = 1")
    reminders_enabled = cursor.fetchone()[0]

    reminder_by_time = {}
    for _, t in REMINDER_TIMES:
        cursor.execute(
            "SELECT COUNT(*) FROM reminders WHERE enabled = 1 AND reminder_time = ?", (t,)
        )
        reminder_by_time[t] = cursor.fetchone()[0]

    conn.close()

    return {
        "today": today_count,
        "week": week_counts,
        "month": month_count,
        "unique_users": unique_users,
        "today_date": today,
        "reminders_enabled": reminders_enabled,
        "reminder_by_time": reminder_by_time,
    }


# ── Image helper ──────────────────────────────────────────────────────────────

def compress_image(path: str) -> io.BytesIO:
    img = Image.open(path).convert("RGB")
    img.thumbnail((1280, 1280), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf


# ── Shared draw logic ─────────────────────────────────────────────────────────

async def do_draw_card(message, user_id: int):
    existing_card = get_user_card_today(user_id)
    if existing_card is not None:
        await message.reply_text(ALREADY_GOT_TEXT)
        return

    card_index = random.randint(0, len(CARDS) - 1)
    card = CARDS[card_index]

    card_text = f"*{card['name']}*\n\n{card['description']}"

    share_text = (
        f"Сегодня Лесной Маг дал мне карту «{card['name']}» 🌿 "
        f"Получи своё послание от леса: t.me/{BOT_USERNAME}"
    )
    share_url = (
        "https://t.me/share/url"
        f"?url=https%3A%2F%2Ft.me%2F{BOT_USERNAME}"
        f"&text={quote(share_text)}"
    )
    share_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🌿 Поделиться с другом", url=share_url)]]
    )

    image_path = os.path.join(os.path.dirname(__file__), card["image"])
    if os.path.exists(image_path):
        buf = compress_image(image_path)
        await message.reply_photo(
            photo=buf,
            caption=card_text,
            parse_mode="Markdown",
            reply_markup=share_keyboard,
        )
    else:
        await message.reply_text(
            card_text,
            parse_mode="Markdown",
            reply_markup=share_keyboard,
        )

    save_user_card(user_id, card_index)

    row = get_user_reminder(user_id)
    has_reminder = row and row[0] == 1
    if not has_reminder:
        await message.reply_text(
            REMINDER_PROMPT_TEXT,
            reply_markup=build_reminder_time_keyboard(),
        )


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(BUTTON_TEXT, callback_data="draw_card")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    mage_image = os.path.join(os.path.dirname(__file__), "images", "the Forest Wizard.png")
    if os.path.exists(mage_image):
        buf = compress_image(mage_image)
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

    reminder_lines = "\n".join(
        f"  • {t} — {s['reminder_by_time'][t]} чел." for _, t in REMINDER_TIMES
    )

    text = (
        f"📊 *Статистика Лесного Мага*\n\n"
        f"📅 *Сегодня* ({today.strftime('%d.%m.%Y')}): {s['today']} карт\n\n"
        f"📆 *Эта неделя:*\n{week_text}\n\n"
        f"🗓 *Этот месяц:* {s['month']} карт\n\n"
        f"👥 *Всего уникальных пользователей:* {s['unique_users']}\n\n"
        f"🔔 *Напоминания:*\n"
        f"  • Включено: {s['reminders_enabled']} пользователей\n"
        f"{reminder_lines}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("У тебя нет доступа к этой команде.")
        return
    delete_user_record(ADMIN_ID)
    await update.message.reply_text("✅ Готово. Лимит сброшен — ты можешь вытянуть карту снова.")


async def reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    row = get_user_reminder(update.effective_user.id)
    enabled = row and row[0] == 1
    reminder_time = row[1] if row else None

    if enabled and reminder_time:
        status = f"🔔 Напоминание включено — каждый день в *{reminder_time}*"
    else:
        status = "🔕 Напоминание выключено"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔔 Включить напоминание", callback_data="reminder_enable"),
            InlineKeyboardButton("🔕 Выключить напоминание", callback_data="reminder_disable"),
        ]
    ])

    await update.message.reply_text(
        f"{status}\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "reminder_enable":
        time_buttons = [
            [InlineKeyboardButton(label, callback_data=f"rtime_{t}")]
            for label, t in REMINDER_TIMES
        ]
        await query.message.edit_text(
            "В какое время напоминать?",
            reply_markup=InlineKeyboardMarkup(time_buttons),
        )

    elif data == "reminder_disable":
        disable_reminder(user_id)
        await query.message.edit_text("🔕 Напоминание отключено. Лес будет молчать.")

    elif data == "reminder_no":
        await query.message.edit_reply_markup(reply_markup=None)

    elif data.startswith("rtime_"):
        chosen_time = data[len("rtime_"):]
        set_reminder(user_id, chosen_time)
        label = next((lbl for lbl, t in REMINDER_TIMES if t == chosen_time), chosen_time)
        await query.message.edit_text(
            f"✅ Напоминание установлено на *{chosen_time}* {label.split()[0]}\n\n"
            f"Каждый день в это время Лесной Маг напомнит тебе о карте дня. 🌿",
            parse_mode="Markdown",
        )


async def draw_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await do_draw_card(query.message, query.from_user.id)


# ── Scheduler jobs ────────────────────────────────────────────────────────────

async def send_reminders_for_slot(context: ContextTypes.DEFAULT_TYPE):
    slot_time, include_no_preference = context.job.data
    today = get_today_str()

    user_ids = get_users_for_slot(slot_time, include_no_preference, today)
    if not user_ids:
        logger.info(f"Reminder job {slot_time}: no users to notify")
        return

    draw_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(BUTTON_TEXT, callback_data="draw_card")]]
    )

    sent = 0
    for user_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=REMINDER_TEXT,
                reply_markup=draw_keyboard,
            )
            mark_reminder_sent(user_id, today)
            sent += 1
        except Exception:
            pass

    logger.info(f"Sent reminder to {sent} users at {slot_time}")


# ── Bot commands menu ─────────────────────────────────────────────────────────

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Начать — получить карту дня"),
        BotCommand("reminder", "Настроить ежедневное напоминание"),
        BotCommand("stats", "Статистика (только для админа)"),
    ])


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    init_db()

    app = Application.builder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("reminder", reminder_command))
    app.add_handler(CallbackQueryHandler(draw_card_callback, pattern="^draw_card$"))
    app.add_handler(CallbackQueryHandler(reminder_callback, pattern="^reminder_"))
    app.add_handler(CallbackQueryHandler(reminder_callback, pattern="^rtime_"))

    # Automatic reminder jobs disabled. Uncomment to re-enable:
    # utc = timezone.utc
    # for slot_time, utc_hour, utc_minute, include_no_pref in REMINDER_SLOTS:
    #     app.job_queue.run_daily(
    #         send_reminders_for_slot,
    #         time=dt_time(utc_hour, utc_minute, tzinfo=utc),
    #         data=(slot_time, include_no_pref),
    #         name=f"reminder_{slot_time}",
    #     )

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
