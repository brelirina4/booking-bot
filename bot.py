import os
import json
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "data.json"

OWNER_ID = None
ADMINS = set()
BOOKINGS = []
CLOSED_DAYS = set()

NAME, PHONE = range(2)


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


def get_dates():
    dates = []
    today = datetime.now().date()

    for day in range(14):
        date = today + timedelta(days=day)
        dates.append(date)

    return dates


def date_text(date):
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"
    ]

    weekdays = [
        "Понедельник", "Вторник", "Среда", "Четверг",
        "Пятница", "Суббота", "Воскресенье"
    ]

    return f"{weekdays[date.weekday()]}, {date.day} {months[date.month]}"


def get_free_times(date):
    if date.isoformat() in CLOSED_DAYS:
        return []

    booked_times = []

    for booking in BOOKINGS:
        if booking["date"] == date.isoformat():
            booked_times.append(booking["time"])

    free_times = []

    for hour in range(10, 20):
        for minutes in [0, 30]:
            time = f"{hour:02d}:{minutes:02d}"

            if time not in booked_times:
                free_times.append(time)

    return free_times


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    dates = get_dates()
    keyboard = []

    for date in dates[:7]:
        keyboard.append(
            [
                InlineKeyboardButton(
                    date_text(date),
                    callback_data=f"date_{date.isoformat()}",
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("Следующие дни", callback_data="more_dates")]
    )

    await query.message.reply_text(
        "Выбери день:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def more_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    dates = get_dates()
    keyboard = []

    for date in dates[7:]:
        keyboard.append(
            [
                InlineKeyboardButton(
                    date_text(date),
                    callback_data=f"date_{date.isoformat()}",
                )
            ]
        )

    await query.message.reply_text(
        "Выбери день:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def choose_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_string = query.data.replace("date_", "")
    date = datetime.strptime(date_string, "%Y-%m-%d").date()

    free_times = get_free_times(date)

    if not free_times:
        await query.message.reply_text(
            "На этот день нет свободного времени."
        )
        return

    keyboard = []

    for time in free_times:
        keyboard.append(
            [
                InlineKeyboardButton(
                    time,
                    callback_data=f"time_{date_string}_{time}",
                )
            ]
        )

    await query.message.reply_text(
        f"Выбери время на {date_text(date)}:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.replace("time_", "")
    date_string, time = data.split("_")

    context.user_data["date"] = date_string
    context.user_data["time"] = time

    await query.message.reply_text("Напиши своё имя:")

    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text

    await update.message.reply_text("Теперь отправь свой номер телефона:")

    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    booking = {
        "user_id": user.id,
        "username": user.username,
        "name": context.user_data["name"],
        "phone": update.message.text,
        "date": context.user_data["date"],
        "time": context.user_data["time"],
    }

    BOOKINGS.append(booking)
    save_data()

    date = datetime.strptime(booking["date"], "%Y-%m-%d").date()

    await update.message.reply_text(
        f"✅ Запись создана!\n\n"
        f"Имя: {booking['name']}\n"
        f"Телефон: {booking['phone']}\n"
        f"Дата: {date_text(date)}\n"
        f"Время: {booking['time']}"
    )

    notification = (
        f"Новая запись!\n\n"
        f"Имя: {booking['name']}\n"
        f"Телефон: {booking['phone']}\n"
        f"Дата: {date_text(date)}\n"
        f"Время: {booking['time']}\n"
        f"Telegram: @{user.username}" if user.username else ""
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

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END


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
            f"Дата: {date_text(date)}\n"
            f"Время: {booking['time']}\n\n"
        )

    await query.message.reply_text(text)


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "Отправь @username человека, которого хочешь сделать админом."
    )

    return "WAIT_USERNAME"


async def get_admin_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()

    if not username.startswith("@"):
        await update.message.reply_text(
            "Отправь username в формате @username."
        )
        return "WAIT_USERNAME"

    await update.message.reply_text(
        "Попроси этого человека открыть бота и нажать Start.\n\n"
        "После этого снова нажми «Добавить админа» и отправь его @username."
    )

    return ConversationHandler.END


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

    elif data == "more_dates":
        await more_dates(update, context)

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


def main():
    load_data()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setadmin", setadmin))
    application.add_handler(CallbackQueryHandler(button_handler))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(choose_time, pattern="^time_")],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            get_admin_username,
        )
    )

    application.run_polling()


if __name__ == "__main__":
    main()
