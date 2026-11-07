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

ASK_NAME, ASK_PHONE, ADD_ADMIN = range(3)

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

        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT
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


def get_admin_ids():
    with sqlite3.connect(DATABASE) as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("admins",),
        ).fetchone()

    if not row or not row[0]:
        return []

    return [
        int(admin_id)
        for admin_id in row[0].split(",")
        if admin_id.strip().isdigit()
    ]


def add_admin_id(user_id):
    admins = get_admin_ids()

    if user_id not in admins:
        admins.append(user_id)

    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
            """,
            ("admins", ",".join(str(admin_id) for admin_id in admins)),
        )


def remove_admin_id(user_id):
    admins = get_admin_ids()

    if user_id in admins:
        admins.remove(user_id)

    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
            """,
            ("admins", ",".join(str(admin_id) for admin_id in admins)),
        )


def is_admin(user_id):
    owner_id = get_owner_id()
    return user_id == owner_id or user_id in get_admin_ids()


def save_user(update: Update):
    user = update.effective_user

    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO users (
                user_id, username, first_name
            )
            VALUES (?, ?, ?)
            """,
            (
                user.id,
                (user.username or "").lower(),
                user.first_name or "",
            ),
        )


def find_user_by_username(username):
    username = username.replace("@", "").strip().lower()

    with sqlite3.connect(DATABASE) as connection:
        row = connection.execute(
            "SELECT user_id FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    return int(row[0]) if row else None


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
    save_user(update)

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

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📋 Все записи",
            callback_data="all_bookings",
        )],
        [InlineKeyboardButton(
            "➕ Добавить админа",
            callback_data="add_admin",
        )],
        [InlineKeyboardButton(
            "👥 Список админов",
            callback_data="admins_list",
        )],
        [InlineKeyboardButton(
            "📅 Вернуться к календарю",
            callback_data="back_to_start",
        )],
    ])

    await query.edit_message_text(
        "Панель владельца.\n\n"
        "Выбери действие:",
        reply_markup=keyboard,
    )


async def panel_all_bookings(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
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
            "📋 Записей пока нет.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "← Назад",
                    callback_data="owner_panel",
                )]
            ]),
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

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "← Назад",
                callback_data="owner_panel",
            )]
        ]),
    )


async def panel_admins_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    owner_id = get_owner_id()

    if owner_id != update.effective_user.id:
        await query.edit_message_text(
            "Эта панель доступна только владельцу."
        )
        return

    admins = get_admin_ids()

    text = "👥 Админы:\n\n"

    if admins:
        for admin_id in admins:
            text += f"Telegram ID: {admin_id}\n"
    else:
        text += "Пока нет админов.\n"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "← Назад",
                callback_data="owner_panel",
            )]
        ]),
    )


async def start_add_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    owner_id = get_owner_id()

    if owner_id != update.effective_user.id:
        await query.edit_message_text(
            "Добавлять админов может только владелец."
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "Отправь @username человека, которого хочешь сделать админом.\n\n"
        "Например:\n"
        "@anna\n\n"
        "Важно: человек сначала должен открыть этого бота\n"
        "и нажать Start."
    )

    return ADD_ADMIN


async def save_new_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    username = update.message.text.strip()
    user_id = find_user_by_username(username)

    if not user_id:
        await update.message.reply_text(
            "Я не нашёл этого человека.\n\n"
            "Попроси его открыть бота и нажать Start,\n"
            "а потом отправь его @username ещё раз."
        )
        return ADD_ADMIN

    add_admin_id(user_id)

    await update.message.reply_text(
        "✅ Админ добавлен!\n\n"
        f"Telegram ID: {user_id}\n\n"
        "Теперь он будет получать уведомления о записях\n"
        "и сможет открывать /bookings."
    )

    return ConversationHandler.END


async def handle_button(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    action = parts[0]

    if action == "ignore":
        return

    if action == "back_to_start":
        await query.edit_message_text(
            "Выберите дату записи.\n"
            "× — свободного времени нет; · — дата недоступна.",
            reply_markup=start_keyboard(update.effective_user.id),
        )
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

    notification_text = (
        "🔔 Новая запись!\n\n"
        f"📅 Дата: {slot.strftime('%d.%m.%Y')}\n"
        f"🕒 Время: {slot.strftime('%H:%M')} — Минск\n"
        f"👤 Имя: {context.user_data['client_name']}\n"
        f"📞 Телефон: {phone}\n"
        f"Telegram ID: {update.effective_user.id}"
    )

    admins = get_admin_ids()
    owner_id = get_owner_id()

    if owner_id and owner_id not in admins:
        admins.append(owner_id)

    for admin_id in admins:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=notification_text,
            )
        except Exception:
            pass

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
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "Эта команда доступна только владельцу и админам."
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
        "Ты назначен владельцем бота.\n\n"
        "Открой /start и нажми «Панель владельца»,\n"
        "чтобы добавить админов."
    )


def main():
    init_database()

    admin_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_add_admin,
                pattern=r"^add_admin$",
            )
        ],
        states={
            ADD_ADMIN: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_new_admin,
                )
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

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
    app.add_handler(admin_handler)
    app.add_handler(conv_handler)
    app.add_handler(
        CallbackQueryHandler(
            owner_panel,
            pattern=r"^owner_panel$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            panel_all_bookings,
            pattern=r"^all_bookings$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            panel_admins_list,
            pattern=r"^admins_list$",
        )
    )
    app.add_handler(CallbackQueryHandler(handle_button))
    app.run_polling()


if __name__ == "__main__":
    main()