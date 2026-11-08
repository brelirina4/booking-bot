import os
import json
import logging
import calendar
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Добавь переменную BOT_TOKEN в Railway -> Variables."
    )

DATA_FILE = "data.json"

OWNER_ID = None
ADMINS = set()
BOOKINGS = []
CLOSED_DAYS = set()


def load_data():
    global OWNER_ID, ADMINS, BOOKINGS, CLOSED_DAYS

    if not os.path.exists(DATA_FILE):
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        OWNER_ID = data.get("owner_id")
        ADMINS = set(data.get("admins", []))
        BOOKINGS = data.get("bookings", [])
        CLOSED_DAYS = set(data.get("closed_days", []))
    except Exception as error:
        logger.error(f"Ошибка загрузки данных: {error}")


def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "owner_id": OWNER_ID,
                    "admins": list(ADMINS),
                    "bookings": BOOKINGS,
                    "closed_days": list(CLOSED_DAYS),
                },
                file,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as error:
        logger.error(f"Ошибка сохранения данных: {error}")


def is_admin(user_id):
    return user_id == OWNER_ID or user_id in ADMINS


def get_month_title(year, month):
    months = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]

    return f"{months[month - 1]} {year}"


def build_calendar(year, month):
    keyboard = []

    keyboard.append(
        [
            InlineKeyboardButton("←", callback_data=f"calendar_{year}_{month - 1}"),
            InlineKeyboardButton(get_month_title(year, month), callback_data="ignore"),
            InlineKeyboardButton("→", callback_data=f"calendar_{year}_{month + 1}"),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton("Пн", callback_data="ignore"),
            InlineKeyboardButton("Вт", callback_data="ignore"),
            InlineKeyboardButton("Ср", callback_data="ignore"),
            InlineKeyboardButton("Чт", callback_data="ignore"),
            InlineKeyboardButton("Пт", callback_data="ignore"),
            InlineKeyboardButton("Сб", callback_data="ignore"),
            InlineKeyboardButton("Вс", callback_data="ignore"),
        ]
    )

    month_calendar = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)

    for week in month_calendar:
        row = []

        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
                continue

            date = datetime(year, month, day).date()

            if date < datetime.now().date():
                row.append(InlineKeyboardButton(" ", callback_data="ignore"))
                continue

            row.append(
                InlineKeyboardButton(
                    str(day),
                    callback_data=f"date_{date.isoformat()}",
                )
            )

        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global OWNER_ID

    user = update.effective_user

    if OWNER_ID is None:
        OWNER_ID = user.id
        save_data()

        await update.message.reply_text(
            f"Привет, {user.first_name}!\n\n"
            "Ты назначен владельцем бота."
        )

    keyboard = []

    if is_admin(user.id):
        keyboard.append(
            [InlineKeyboardButton("Панель владельца", callback_data="owner_panel")]
        )

    keyboard.append(
        [InlineKeyboardButton("Записаться", callback_data="book")]
    )

    await update.message.reply_text(
        "Привет! Выбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    now = datetime.now()

    await query.message.reply_text(
        "Выбери дату:",
        reply_markup=build_calendar(now.year, now.month),
    )


async def change_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.replace("calendar_", "")
    year, month = map(int, data.split("_"))

    if month < 1:
        month = 12
        year -= 1

    elif month > 12:
        month = 1
        year += 1

    await query.edit_message_reply_markup(
        reply_markup=build_calendar(year, month)
    )


async def choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_string = query.data.replace("date_", "")
    date = datetime.strptime(date_string, "%Y-%m-%d").date()

    if date.isoformat() in CLOSED_DAYS:
        await query.message.reply_text("Этот день закрыт для записи.")
        return

    booked_times = [
        booking["time"]
        for booking in BOOKINGS
        if booking["date"] == date.isoformat()
    ]

    keyboard = []

    for hour in range(10, 20):
        row = []

        for minutes in [0, 30]:
            time = f"{hour:02d}:{minutes:02d}"

            if time in booked_times:
                continue

            row.append(
                InlineKeyboardButton(
                    time,
                    callback_data=f"time_{date_string}_{time}",
                )
            )

        if row:
            keyboard.append(row)

    if not keyboard:
        await query.message.reply_text("На этот день нет свободного времени.")
        return

    await query.message.reply_text(
        f"Выбери время на {date.strftime('%d.%m.%Y')}:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.replace("time_", "")
    date_string, time = data.rsplit("_", 1)

    context.user_data["booking_date"] = date_string
    context.user_data["booking_time"] = time
    context.user_data["booking_step"] = "name"

    await query.message.reply_text("Напиши своё имя:")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    step = context.user_data.get("booking_step")

    if step == "name":
        context.user_data["booking_name"] = text
        context.user_data["booking_step"] = "phone"

        await update.message.reply_text("Теперь отправь свой номер телефона:")
        return

    if step == "phone":
        booking = {
            "user_id": user.id,
            "username": user.username,
            "name": context.user_data["booking_name"],
            "phone": text,
            "date": context.user_data["booking_date"],
            "time": context.user_data["booking_time"],
        }

        BOOKINGS.append(booking)
        save_data()

        context.user_data["booking_step"] = None

        date = datetime.strptime(booking["date"], "%Y-%m-%d").date()

        await update.message.reply_text(
            f"✅ Запись создана!\n\n"
            f"Имя: {booking['name']}\n"
            f"Телефон: {booking['phone']}\n"
            f"Дата: {date.strftime('%d.%m.%Y')}\n"
            f"Время: {booking['time']}"
        )

        username = f"@{user.username}" if user.username else "не указан"

        notification = (
            f"Новая запись!\n\n"
            f"Имя: {booking['name']}\n"
            f"Телефон: {booking['phone']}\n"
            f"Дата: {date.strftime('%d.%m.%Y')}\n"
            f"Время: {booking['time']}\n"
            f"Telegram: {username}"
        )

        if OWNER_ID:
            try:
                await context.bot.send_message(OWNER_ID, notification)
            except Exception as error:
                logger.error(f"Не удалось отправить уведомление владельцу: {error}")

        for admin_id in ADMINS:
            try:
                await context.bot.send_message(admin_id, notification)
            except Exception as error:
                logger.error(f"Не удалось отправить уведомление админу: {error}")

        return

    if context.user_data.get("admin_step") == "username":
        if not text.startswith("@"):
            await update.message.reply_text("Отправь username в формате @username.")
            return

        context.user_data["admin_step"] = None

        await update.message.reply_text(
            "Попроси этого человека открыть бота и нажать Start.\n\n"
            "После этого снова нажми «Добавить админа» и отправь его @username."
        )


async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.message.reply_text("У тебя нет доступа к панели владельца.")
        return

    keyboard = [
        [InlineKeyboardButton("Все записи", callback_data="all_bookings")],
        [InlineKeyboardButton("Добавить админа", callback_data="add_admin")],
        [InlineKeyboardButton("Список админов", callback_data="admin_list")],
        [InlineKeyboardButton("Вернуться к календарю", callback_data="book")],
    ]

    await query.message.reply_text(
        "Панель владельца:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def all_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not BOOKINGS:
        await query.message.reply_text("Записей пока нет.")
        return

    text = "Все записи:\n\n"

    for index, booking in enumerate(BOOKINGS, start=1):
        date = datetime.strptime(booking["date"], "%Y-%m-%d").date()

        text += (
            f"{index}. {booking['name']}\n"
            f"Телефон: {booking['phone']}\n"
            f"Дата: {date.strftime('%d.%m.%Y')}\n"
            f"Время: {booking['time']}\n\n"
        )

    await query.message.reply_text(text)


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["admin_step"] = "username"

    await query.message.reply_text(
        "Отправь @username человека, которого хочешь сделать админом."
    )


async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not ADMINS:
        await query.message.reply_text("Админов пока нет.")
        return

    text = "Админы:\n\n"

    for admin_id in ADMINS:
        text += f"ID: {admin_id}\n"

    await query.message.reply_text(text)


async def setadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global OWNER_ID

    user = update.effective_user

    if OWNER_ID is None:
        OWNER_ID = user.id
        save_data()

        await update.message.reply_text("Ты назначен владельцем бота.")
        return

    await update.message.reply_text("Владелец уже назначен.")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "book":
        await book(update, context)

    elif data.startswith("calendar_"):
        await change_month(update, context)

    elif data.startswith("date_"):
        await choose_date(update, context)

    elif data.startswith("time_"):
        await choose_time(update, context)

    elif data == "owner_panel":
        await owner_panel(update, context)

    elif data == "all_bookings":
        await all_bookings(update, context)

    elif data == "add_admin":
        await add_admin(update, context)

    elif data == "admin_list":
        await admin_list(update, context)

    elif data == "ignore":
        await query.answer()


def main():
    load_data()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setadmin", setadmin))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    application.run_polling()


if __name__ == "__main__":
    main()
