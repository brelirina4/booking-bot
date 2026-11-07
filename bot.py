import calendar
import logging
import sqlite3
from datetime import datetime, date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

TOKEN = "9244559671:AAHIrntd4NqgsQ2noNfkpEZdmMt097J2XpY"

TIMEZONE = ZoneInfo("Europe/Minsk")
DATABASE = Path(__file__).with_name("bookings.sqlite3")

ASK_NAME, ASK_PHONE = range(2)

OPEN_HOUR = 10
CLOSE_HOUR = 18

MONTHS = [
    "", "Январь", "Февраль", "Март", "Апрель",
    "Май", "Июнь", "Июль", "Август",
    "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

logging.basicConfig(level=logging.WARNING)


def now():
    return datetime.now(TIMEZONE)


def init_database():
    with sqlite3.connect(DATABASE) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                slot TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        try:
            connection.execute(
                "ALTER TABLE bookings ADD COLUMN name TEXT"
            )
        except sqlite3.OperationalError:
            pass

        try:
            connection.execute(
                "ALTER TABLE bookings ADD COLUMN phone TEXT"
            )
        except sqlite3.OperationalError:
            pass


def get_owner_id():
    with sqlite3.connect(DATABASE) as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("owner_id",),
        ).fetchone()

    return int(row[0]) if row else None


def set_owner_id(user_id):
    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
            """,
            ("owner_id", str(user_id)),
        )


def booked_slots():
    with sqlite3.connect(DATABASE) as connection:
        rows = connection.execute(
            "SELECT slot FROM bookings"
        ).fetchall()
    return {row[0] for row in rows}


def available_slots(day):
    occupied = booked_slots()
    current = now()
    result = []

    for hour in range(OPEN_HOUR, CLOSE_HOUR):
        slot = datetime.combine(
            day, time(hour=hour), tzinfo=TIMEZONE
        )
        if slot > current and slot.isoformat() not in occupied:
            result.append(slot)

    return result


def month_keyboard(year, month):
    current = now().date()
    last_day = current + timedelta(days=90)

    rows = [
        [InlineKeyboardButton(
            f"{MONTHS[month]} {year}",
            callback_data="ignore",
        )],
        [
            InlineKeyboardButton(label, callback_data="ignore")
            for label in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        ],
    ]

    for week in calendar.monthcalendar(year, month):
        buttons = []

        for number in week:
            label = " "
            callback = "ignore"

            if number:
                day = date(year, month, number)

                if current <= day <= last_day:
                    if available_slots(day):
                        label = str(number)
                        callback = f"day|{day.isoformat()}"
                    else:
                        label = "×"
                else:
                    label = "·"

            buttons.append(InlineKeyboardButton(
                label, callback_data=callback
            ))

        rows.append(buttons)

    navigation = []

    if (year, month) > (current.year, current.month):
        previous = (
            (year - 1, 12) if month == 1 else (year, month - 1)
        )
        navigation.append(InlineKeyboardButton(
            "←",
            callback_data=f"month|{previous[0]}|{previous[1]}",
        ))

    if (year, month) < (last_day.year, last_day.month):
        following = (
            (year + 1, 1) if month == 12 else (year, month + 1)
        )
        navigation.append(InlineKeyboardButton(
            "→",
            callback_data=f"month|{following[0]}|{following[1]}",
        ))

    if navigation:
        rows.append(navigation)

    return InlineKeyboardMarkup(rows)


def hours_keyboard(day):
    slots = available_slots(day)
    buttons = [
        InlineKeyboardButton(
            slot.strftime("%H:%M"),
            callback_data=f"slot|{slot.isoformat()}",
        )
        for slot in slots
    ]

    rows = [
        buttons[index:index + 3]
        for index in range(0, len(buttons), 3)
    ]

    rows.append([InlineKeyboardButton(
        "Назад к календарю",
        callback_data=f"month|{day.year}|{day.month}",
    )])

    return InlineKeyboardMarkup(rows)


def start_keyboard(user_id):
    current = now().date()
    owner_id = get_owner_id()

    month_menu = month_keyboard(current.year, current.month)
    rows = [list(row) for row in month_menu.inline_keyboard]

    if owner_id == user_id:
        rows.append([
            InlineKeyboardButton(
                "Панель владельца",
                callback_data="owner_panel",
            )
        ])

    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите дату записи.\n"
        "Время — Минск. Длительность — 1 час.\n"
        "× — свободного времени нет; · — дата недоступна.",
        reply_markup=start_keyboard(update.effective_user.id),
    )


async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    owner_id = get_owner_id()

    if owner_id != update.effective_user.id:
        await query.edit_message_text(
            "Эта панель доступна только владельцу."
        )
        return

    with sqlite3.connect(DATABASE) as connection:
        rows = connection.execute(
            """
            SELECT slot, name, phone, user_id
            FROM bookings
            ORDER BY slot
            """
        ).fetchall()

    if not rows:
        await query.edit_message_text(
            "📋 Записей пока нет.\n\n"
            "Нажмите /start, чтобы вернуться к календарю."
        )
        return

    text = "📋 Все записи:\n\n"

    for slot, name, phone, user_id in rows:
        booking_time = datetime.fromisoformat(slot)
        text += (
            f"📅 {booking_time.strftime('%d.%m.%Y')}\n"
            f"🕒 {booking_time.strftime('%H:%M')} — Минск\n"
            f"👤 Имя: {name or 'не указано'}\n"
            f"📞 Телефон: {phone or 'не указан'}\n"
            f"Telegram ID: {user_id}\n\n"
        )

    await query.edit_message_text(text)


async def handle_button(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    action = parts[0]

    if action == "ignore":
        return

    if action == "month":
        year, month = int(parts[1]), int(parts[2])

        await query.edit_message_text(
            "Выберите дату записи.\n"
            "× — свободного времени нет; · — дата недоступна.",
            reply_markup=month_keyboard(year, month),
        )

    elif action == "day":
        day = date.fromisoformat(parts[1])

        await query.edit_message_text(
            f"Свободное время на {day.strftime('%d.%m.%Y')}.\n"
            "Часовой пояс — Минск.",
            reply_markup=hours_keyboard(day),
        )

    elif action == "slot":
        slot = datetime.fromisoformat(parts[1])

        if slot not in available_slots(slot.date()):
            await query.edit_message_text(
                "Это время уже недоступно. Выберите другое.",
                reply_markup=hours_keyboard(slot.date()),
            )
            return

        await query.edit_message_text(
            f"Подтвердить запись на "
            f"{slot.strftime('%d.%m.%Y в %H:%M')}?\n"
            "Длительность — 1 час. Время — Минск.\n"
            "До подтверждения место не забронировано.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "Подтвердить запись",
                    callback_data=f"book|{slot.isoformat()}",
                )],
                [InlineKeyboardButton(
                    "Выбрать другое время",
                    callback_data=f"day|{slot.date().isoformat()}",
                )],
            ]),
        )


async def start_booking(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    slot = datetime.fromisoformat(parts[1])

    context.user_data["pending_slot"] = slot.isoformat()

    await query.edit_message_text(
        f"Запись на {slot.strftime('%d.%m.%Y в %H:%M')}.\n\n"
        "Как тебя зовут?\n"
        "Напиши имя одним сообщением."
    )

    return ASK_NAME


async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["client_name"] = update.message.text.strip()

    await update.message.reply_text(
        "Спасибо! Теперь отправь номер телефона.\n\n"
        "Например: +7 900 123-45-67"
    )

    return ASK_PHONE


async def save_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    slot_iso = context.user_data.get("pending_slot")

    if not slot_iso:
        await update.message.reply_text("Начните запись заново: /start")
        return ConversationHandler.END

    slot = datetime.fromisoformat(slot_iso)
    current = now()

    valid = (
        current.date() <= slot.date()
        <= current.date() + timedelta(days=90)
        and slot > current
        and OPEN_HOUR <= slot.hour < CLOSE_HOUR
        and slot.minute == 0
        and slot.second == 0
    )

    if not valid:
        await update.message.reply_text(
            "Это время уже недоступно. Начните заново: /start"
        )
        return ConversationHandler.END

    try:
        with sqlite3.connect(DATABASE) as connection:
            connection.execute(
                """
                INSERT INTO bookings (
                    slot, user_id, created_at, name, phone
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    slot_iso,
                    update.effective_user.id,
                    current.isoformat(),
                    context.user_data["client_name"],
                    phone,
                ),
            )
    except sqlite3.IntegrityError:
        await update.message.reply_text(
            "Это время уже заняли. Выберите другое: /start"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ Запись сохранена!\n\n"
        "Дата: " + slot.strftime("%d.%m.%Y") + "\n"
        "Время: " + slot.strftime("%H:%M") + " — Минск\n"
        "Имя: " + context.user_data["client_name"] + "\n"
        "Телефон: " + phone + "\n\n"
        "Это учебная запись, не запись в настоящий салон."
    )

    return ConversationHandler.END


async def all_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = get_owner_id()

    if owner_id is None:
        await update.message.reply_text(
            "Владелец ещё не назначен. Отправьте /setadmin."
        )
        return

    if update.effective_user.id != owner_id:
        await update.message.reply_text(
            "Эта команда доступна только владельцу."
        )
        return

    with sqlite3.connect(DATABASE) as connection:
        rows = connection.execute(
            """
            SELECT slot, name, phone, user_id
            FROM bookings
            ORDER BY slot
            """
        ).fetchall()

    if not rows:
        await update.message.reply_text("Записей пока нет.")
        return

    text = "📋 Все записи:\n\n"

    for slot, name, phone, user_id in rows:
        booking_time = datetime.fromisoformat(slot)
        text += (
            f"📅 {booking_time.strftime('%d.%m.%Y')}\n"
            f"🕒 {booking_time.strftime('%H:%M')} — Минск\n"
            f"👤 Имя: {name or 'не указано'}\n"
            f"📞 Телефон: {phone or 'не указан'}\n"
            f"Telegram ID: {user_id}\n\n"
        )

    await update.message.reply_text(text)


async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = get_owner_id()

    if owner_id is not None:
        await update.message.reply_text(
            "Владелец уже назначен."
        )
        return

    set_owner_id(update.effective_user.id)

    await update.message.reply_text(
        "Ты назначен владельцем бота.\n"
        "Теперь панель владельца доступна только тебе."
    )


def main():
    init_database()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_booking,
                pattern=r"^book\|",
            )
        ],
        states={
            ASK_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_name,
                )
            ],
            ASK_PHONE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_phone,
                )
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bookings", all_bookings))
    app.add_handler(CommandHandler("setadmin", set_admin))
    app.add_handler(conv_handler)
    app.add_handler(
        CallbackQueryHandler(
            owner_panel,
            pattern=r"^owner_panel$",
        )
    )
    app.add_handler(CallbackQueryHandler(handle_button))
    app.run_polling()


if __name__ == "__main__":
    main()