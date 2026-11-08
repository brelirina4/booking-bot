import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ================== НАСТРОЙКИ ==================

USER_1_ID = 1977251069
USER_2_ID = 0

ALLOWED_USER_IDS = {USER_1_ID, USER_2_ID}

PARTNERS = {
    USER_1_ID: USER_2_ID,
    USER_2_ID: USER_1_ID,
}

TIMEZONE = ZoneInfo("Europe/Moscow")
DATA_FILE = Path(os.getenv("DATA_FILE_PATH", "data.json"))

# ================== ХРАНЕНИЕ ==================

DEFAULT_DATA = {
    "notes": [],
    "dates": [],
    "wishes": [],
    "plans": [],
    "moods": [],
    "playlist": [],
    "capsules": [],
}


def load_data() -> dict:
    if not DATA_FILE.exists():
        return {}

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(data, dict):
        return {}

    for key, value in DEFAULT_DATA.items():
        data.setdefault(key, value)

    return data


def save_data(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def generate_id() -> str:
    return str(int(datetime.now(TIMEZONE).timestamp() * 1000))


def now_moscow() -> datetime:
    return datetime.now(TIMEZONE)


def format_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return "дата не указана"


def get_partner(user_id: int) -> int:
    return PARTNERS.get(user_id, 0)


def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USER_IDS


# ================== ГЛАВНОЕ МЕНЮ ==================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💌 Записки", callback_data="menu:notes")],
            [InlineKeyboardButton("📅 Важные даты", callback_data="menu:dates")],
            [InlineKeyboardButton("🎁 Желания", callback_data="menu:wishes")],
            [InlineKeyboardButton("🧸 Наши планы", callback_data="menu:plans")],
            [InlineKeyboardButton("😊 Настроение дня", callback_data="menu:moods")],
            [InlineKeyboardButton("🎵 Наш плейлист", callback_data="menu:playlist")],
            [InlineKeyboardButton("🤍 Мне нужна поддержка", callback_data="menu:support")],
            [InlineKeyboardButton("⏳ Капсула времени", callback_data="menu:capsules")],
        ]
    )


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text(
            f"⛔ Этот бот только для двух людей.\n\n"
            f"Твой Telegram ID:\n<code>{user_id}</code>\n\n"
            "Отправь этот ID тому, кто создаёт бота.",
            parse_mode="HTML",
        )
        return

    await update.effective_message.reply_text(
        "🤍 <b>Наш личный бот</b>\n\nПривет! Это место только для нас двоих 💕\n\n"
        "Выбери раздел:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_main_menu(update, context)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_main_menu(update, context)


async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()

    await update.effective_message.reply_text(
        "❌ Действие отменено.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


# ================== ОБЩИЙ КАЛЕНДАРЬ ==================

def build_calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    keyboard = []

    month_name = datetime(year, month, 1, tzinfo=TIMEZONE).strftime("%B %Y")

    keyboard.append(
        [
            InlineKeyboardButton("⬅️", callback_data=f"pick:month:{year}:{month - 1}"),
            InlineKeyboardButton(month_name, callback_data="pick:ignore"),
            InlineKeyboardButton("➡️", callback_data=f"pick:month:{year}:{month + 1}"),
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton("Пн", callback_data="pick:ignore"),
            InlineKeyboardButton("Вт", callback_data="pick:ignore"),
            InlineKeyboardButton("Ср", callback_data="pick:ignore"),
            InlineKeyboardButton("Чт", callback_data="pick:ignore"),
            InlineKeyboardButton("Пт", callback_data="pick:ignore"),
            InlineKeyboardButton("Сб", callback_data="pick:ignore"),
            InlineKeyboardButton("Вс", callback_data="pick:ignore"),
        ]
    )

    first_day = datetime(year, month, 1, tzinfo=TIMEZONE)

    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=TIMEZONE)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=TIMEZONE)

    days_in_month = (next_month - first_day).days
    weekday = first_day.weekday()

    row = []

    for _ in range(weekday):
        row.append(InlineKeyboardButton(" ", callback_data="pick:ignore"))

    for day in range(1, days_in_month + 1):
        row.append(
            InlineKeyboardButton(
                str(day),
                callback_data=f"pick:day:{year}:{month}:{day}",
            )
        )

        if len(row) == 7:
            keyboard.append(row)
            row = []

    if row:
        while len(row) < 7:
            row.append(InlineKeyboardButton(" ", callback_data="pick:ignore"))

        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="pick:cancel")])

    return InlineKeyboardMarkup(keyboard)


def build_hour_keyboard() -> InlineKeyboardMarkup:
    keyboard = []

    for start in range(0, 24, 6):
        row = []

        for hour in range(start, start + 6):
            row.append(
                InlineKeyboardButton(
                    f"{hour:02d}:00",
                    callback_data=f"pick:hour:{hour}",
                )
            )

        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="pick:cancel")])

    return InlineKeyboardMarkup(keyboard)


def build_minute_keyboard(hour: int) -> InlineKeyboardMarkup:
    keyboard = []

    for start in range(0, 60, 10):
        row = []

        for minute in range(start, start + 10, 5):
            row.append(
                InlineKeyboardButton(
                    f"{hour:02d}:{minute:02d}",
                    callback_data=f"pick:minute:{hour}:{minute}",
                )
            )

        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="pick:cancel")])

    return InlineKeyboardMarkup(keyboard)


async def open_date_picker(
    update: Update, context: ContextTypes.DEFAULT_TYPE, purpose: str
) -> None:
    query = update.callback_query
    current_date = now_moscow()

    context.user_data["picker_purpose"] = purpose

    await query.edit_message_text(
        "📅 Выбери дату:",
        reply_markup=build_calendar_keyboard(
            current_date.year,
            current_date.month,
        ),
    )


async def date_picker_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    parts = query.data.split(":")
    action = parts[1]

    if action == "cancel":
        context.user_data.clear()

        await query.edit_message_text(
            "❌ Действие отменено.",
            reply_markup=main_menu_keyboard(),
        )

        return ConversationHandler.END

    if action == "ignore":
        return context.user_data.get("picker_state", "WAITING_PICK_DATE")

    if action == "month":
        year = int(parts[2])
        month = int(parts[3])

        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1

        await query.edit_message_reply_markup(
            reply_markup=build_calendar_keyboard(year, month)
        )

        return "WAITING_PICK_DATE"

    if action == "day":
        year = int(parts[2])
        month = int(parts[3])
        day = int(parts[4])

        context.user_data["pick_year"] = year
        context.user_data["pick_month"] = month
        context.user_data["pick_day"] = day

        await query.edit_message_text(
            "⏰ Выбери час:",
            reply_markup=build_hour_keyboard(),
        )

        return "WAITING_PICK_HOUR"

    if action == "hour":
        hour = int(parts[2])
        context.user_data["pick_hour"] = hour

        await query.edit_message_text(
            "⏰ Выбери минуты:",
            reply_markup=build_minute_keyboard(hour),
        )

        return "WAITING_PICK_MINUTE"

    if action == "minute":
        hour = int(parts[2])
        minute = int(parts[3])

        year = context.user_data.get("pick_year")
        month = context.user_data.get("pick_month")
        day = context.user_data.get("pick_day")

        if not year or not month or not day:
            await query.edit_message_text(
                "⚠️ Не удалось выбрать дату. Попробуй снова.",
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END

        selected = datetime(year, month, day, hour, minute, tzinfo=TIMEZONE)
        context.user_data["picked_datetime"] = selected.isoformat()

        purpose = context.user_data.get("picker_purpose")

        if purpose == "note":
            return await finish_note_date(update, context, selected)

        if purpose == "date":
            return await finish_date_picker(update, context, selected)

        if purpose == "plan":
            return await finish_plan_date(update, context, selected)

        if purpose == "capsule":
            return await finish_capsule_date(update, context, selected)

    return ConversationHandler.END


# ================== ЗАПИСКИ ==================

async def show_notes_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Оставить записку", callback_data="note:create")],
        [InlineKeyboardButton("🗂 Все записки", callback_data="note:list")],
        [InlineKeyboardButton("🗑 Удалить записку", callback_data="note:delete")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "💌 <b>Записки</b>\n\nЗдесь можно оставить записку партнёру.\n"
        "Можно отправить сразу или выбрать дату и время.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_create_note(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    await query.edit_message_text(
        "💌 Напиши записку для партнёра.\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_NOTE_TEXT"


async def save_note_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    note_text = update.message.text.strip()

    if not note_text:
        await update.message.reply_text("⚠️ Текст записки не может быть пустым.")
        return "WAITING_NOTE_TEXT"

    context.user_data["new_note_text"] = note_text

    keyboard = [
        [
            InlineKeyboardButton("🚀 Отправить сразу", callback_data="note:when:now"),
            InlineKeyboardButton("📅 Выбрать дату", callback_data="note:when:date"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="pick:cancel")],
    ]

    await update.message.reply_text(
        "⏰ Когда отправить записку?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return "WAITING_NOTE_TIME"


async def note_time_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    choice = query.data.split(":")[2]

    if choice == "now":
        return await finish_note_now(update, context)

    await open_date_picker(update, context, "note")

    return "WAITING_PICK_DATE"


async def finish_note_now(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    note_text = context.user_data.get("new_note_text")

    if not note_text:
        await query.edit_message_text(
            "⚠️ Не удалось найти текст записки. Попробуй создать её заново.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()
    note_id = generate_id()

    data["notes"].append(
        {
            "id": note_id,
            "from_id": user_id,
            "to_id": get_partner(user_id),
            "text": note_text,
            "send_at": now_moscow().isoformat(),
            "status": "sent",
            "reply": None,
        }
    )

    save_data(data)

    context.user_data.clear()

    partner_id = get_partner(user_id)

    try:
        await context.bot.send_message(
            chat_id=partner_id,
            text=f"💌 <b>Тебе пришла записка</b>\n\n{note_text}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "💬 Ответить",
                            callback_data=f"note:reply:{note_id}",
                        )
                    ]
                ]
            ),
        )
    except Exception:
        pass

    try:
        await query.edit_message_text(
            "✅ Записка отправлена.",
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Записка отправлена.",
            reply_markup=main_menu_keyboard(),
        )

    return ConversationHandler.END


async def finish_note_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, selected: datetime
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    note_text = context.user_data.get("new_note_text")

    if not note_text:
        await query.edit_message_text(
            "⚠️ Не удалось найти текст записки. Попробуй создать её заново.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()
    note_id = generate_id()

    data["notes"].append(
        {
            "id": note_id,
            "from_id": user_id,
            "to_id": get_partner(user_id),
            "text": note_text,
            "send_at": selected.isoformat(),
            "status": "scheduled",
            "reply": None,
        }
    )

    save_data(data)

    context.user_data.clear()

    success_text = (
        f"✅ Записка сохранена.\n\n"
        f"Она будет отправлена:\n"
        f"<b>{format_datetime(selected.isoformat())}</b>"
    )

    try:
        await query.edit_message_text(
            success_text,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=success_text,
                parse_mode="HTML",
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            pass

    return ConversationHandler.END


async def show_notes_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    notes = data["notes"]

    keyboard = []

    for note in notes:
        if note["from_id"] == user_id:
            title = f"💌 Твоя записка — {format_datetime(note['send_at'])}"
        else:
            title = f"💌 Записка партнёра — {format_datetime(note['send_at'])}"

        keyboard.append(
            [
                InlineKeyboardButton(
                    title,
                    callback_data=f"note:view:{note['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:notes")])

    await query.edit_message_text(
        "🗂 <b>Все записки</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def open_note(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    note_id = query.data.split(":")[2]

    data = load_data()
    note = next(
        (item for item in data["notes"] if item["id"] == note_id),
        None,
    )

    if not note:
        await query.edit_message_text("⚠️ Записка не найдена.")
        return

    if note["from_id"] == user_id:
        title = "💌 Твоя записка"
    else:
        title = "💌 Записка партнёра"

    keyboard = []

    if note["to_id"] == user_id and not note["reply"]:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "💬 Ответить",
                    callback_data=f"note:reply:{note_id}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="note:list")])

    reply_text = (
        f"\n\n💬 <b>Ответ:</b>\n{note['reply']}"
        if note["reply"]
        else ""
    )

    await query.edit_message_text(
        f"{title}\n\n{note['text']}\n\n"
        f"Отправлена: {format_datetime(note['send_at'])}"
        f"{reply_text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_note_reply(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    note_id = query.data.split(":")[2]
    context.user_data["reply_note_id"] = note_id

    await query.edit_message_text(
        "💬 Напиши ответ на записку.\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_NOTE_REPLY"


async def save_note_reply(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    reply_text = update.message.text.strip()
    note_id = context.user_data.get("reply_note_id")

    if not note_id:
        await update.message.reply_text(
            "⚠️ Не удалось найти записку.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()
    note = next(
        (item for item in data["notes"] if item["id"] == note_id),
        None,
    )

    if not note:
        await update.message.reply_text(
            "⚠️ Записка не найдена.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    note["reply"] = reply_text
    save_data(data)

    try:
        await context.bot.send_message(
            chat_id=note["from_id"],
            text=f"💌 <b>Ответ на твою записку</b>\n\n{reply_text}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await update.message.reply_text(
        "✅ Ответ отправлен.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def delete_note_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    notes = data["notes"]

    keyboard = []

    for note in notes:
        title = (
            f"💌 Твоя записка — {format_datetime(note['send_at'])}"
            if note["from_id"] == user_id
            else f"💌 Записка партнёра — {format_datetime(note['send_at'])}"
        )

        keyboard.append(
            [
                InlineKeyboardButton(
                    title,
                    callback_data=f"note:delete_confirm:{note['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:notes")])

    await query.edit_message_text(
        "🗑 <b>Выбери записку, которую удалить:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_note_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    note_id = query.data.split(":")[2]

    data = load_data()
    data["notes"] = [
        note for note in data["notes"] if note["id"] != note_id
    ]

    save_data(data)

    await query.edit_message_text(
        "✅ Записка удалена.",
        reply_markup=main_menu_keyboard(),
    )


# ================== ВАЖНЫЕ ДАТЫ ==================

async def show_dates_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Добавить дату", callback_data="date:create")],
        [InlineKeyboardButton("🗓 Все даты", callback_data="date:list")],
        [InlineKeyboardButton("📅 Ближайшие даты", callback_data="date:nearest")],
        [InlineKeyboardButton("🗑 Удалить дату", callback_data="date:delete")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "📅 <b>Важные даты</b>\n\nЗдесь можно сохранить важные даты\n"
        "и получать напоминания.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_create_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    await query.edit_message_text(
        "📅 Напиши название даты.\n\n"
        "Например: Наш день знакомства\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_DATE_NAME"


async def save_date_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    date_name = update.message.text.strip()

    if not date_name:
        await update.message.reply_text("⚠️ Название не может быть пустым.")
        return "WAITING_DATE_NAME"

    context.user_data["new_date_name"] = date_name

    await open_date_picker(update, context, "date")

    return "WAITING_PICK_DATE"


async def finish_date_picker(
    update: Update, context: ContextTypes.DEFAULT_TYPE, selected: datetime
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    context.user_data["new_date_when"] = selected.isoformat()

    keyboard = [
        [
            InlineKeyboardButton("🚀 Один раз", callback_data="date:repeat:once"),
            InlineKeyboardButton("📅 Каждый год", callback_data="date:repeat:yearly"),
        ],
        [
            InlineKeyboardButton("🗓 Каждый месяц", callback_data="date:repeat:monthly"),
            InlineKeyboardButton("❌ Отмена", callback_data="pick:cancel"),
        ],
    ]

    await query.edit_message_text(
        f"📅 Дата: <b>{format_datetime(selected.isoformat())}</b>\n\n"
        "🔁 Как часто напоминать?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return "WAITING_DATE_REPEAT"


async def save_date_repeat(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    repeat = query.data.split(":")[2]
    name = context.user_data.get("new_date_name")
    when = context.user_data.get("new_date_when")

    if not name or not when:
        await query.edit_message_text(
            "⚠️ Не удалось сохранить дату.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()

    data["dates"].append(
        {
            "id": generate_id(),
            "name": name,
            "when": when,
            "repeat": repeat,
        }
    )

    save_data(data)

    context.user_data.clear()

    repeat_text = {
        "once": "один раз",
        "yearly": "каждый год",
        "monthly": "каждый месяц",
    }[repeat]

    await query.edit_message_text(
        f"✅ Дата сохранена.\n\nПовтор: {repeat_text}.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def show_dates_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    dates = data["dates"]

    dates.sort(key=lambda item: item["when"])

    keyboard = []

    for date_item in dates:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 {date_item['name']} — {format_datetime(date_item['when'])}",
                    callback_data=f"date:view:{date_item['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:dates")])

    await query.edit_message_text(
        "🗓 <b>Все даты</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_nearest_dates(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    current_time = now_moscow()

    dates = [
        date_item
        for date_item in data["dates"]
        if datetime.fromisoformat(date_item["when"]) >= current_time
    ]

    dates.sort(key=lambda item: item["when"])

    keyboard = []

    for date_item in dates[:10]:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📅 {date_item['name']} — {format_datetime(date_item['when'])}",
                    callback_data=f"date:view:{date_item['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:dates")])

    await query.edit_message_text(
        "📅 <b>Ближайшие даты</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def open_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    date_id = query.data.split(":")[2]

    data = load_data()
    date_item = next(
        (item for item in data["dates"] if item["id"] == date_id),
        None,
    )

    if not date_item:
        await query.edit_message_text("⚠️ Дата не найдена.")
        return

    repeat_text = {
        "once": "один раз",
        "yearly": "каждый год",
        "monthly": "каждый месяц",
    }.get(date_item["repeat"], "один раз")

    keyboard = [
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"date:delete:{date_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="date:list")],
    ]

    await query.edit_message_text(
        f"📅 <b>{date_item['name']}</b>\n\n"
        f"Дата: {format_datetime(date_item['when'])}\n"
        f"Повтор: {repeat_text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_date_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    dates = data["dates"]

    keyboard = []

    for date_item in dates:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🗑 {date_item['name']}",
                    callback_data=f"date:delete_confirm:{date_item['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:dates")])

    await query.edit_message_text(
        "🗑 <b>Выбери дату, которую удалить:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_date_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    date_id = query.data.split(":")[2]

    data = load_data()
    data["dates"] = [
        item for item in data["dates"] if item["id"] != date_id
    ]

    save_data(data)

    await query.edit_message_text(
        "✅ Дата удалена.",
        reply_markup=main_menu_keyboard(),
    )


# ================== ЖЕЛАНИЯ ==================

async def show_wishes_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Добавить желание", callback_data="wish:create")],
        [InlineKeyboardButton("🎁 Мои желания", callback_data="wish:mine")],
        [InlineKeyboardButton("🎁 Желания партнёра", callback_data="wish:partner")],
        [InlineKeyboardButton("✅ Желание исполнено", callback_data="wish:done")],
        [InlineKeyboardButton("🗑 Удалить желание", callback_data="wish:delete")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "🎁 <b>Желания</b>\n\nЗдесь можно сохранять желания\n"
        "и отмечать исполненные.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_create_wish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    await query.edit_message_text(
        "🎁 Напиши желание.\n\n"
        "Например: Новые наушники\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_WISH_TEXT"


async def save_wish_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    wish_text = update.message.text.strip()

    if not wish_text:
        await update.message.reply_text("⚠️ Текст желания не может быть пустым.")
        return "WAITING_WISH_TEXT"

    context.user_data["new_wish_text"] = wish_text

    keyboard = [
        [
            InlineKeyboardButton("🤍 Для меня", callback_data="wish:owner:me"),
            InlineKeyboardButton("🤍 Для партнёра", callback_data="wish:owner:partner"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="pick:cancel")],
    ]

    await update.message.reply_text(
        "🏷 Это желание для:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return "WAITING_WISH_OWNER"


async def save_wish_owner(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    choice = query.data.split(":")[2]
    wish_text = context.user_data.get("new_wish_text")

    if not wish_text:
        await query.edit_message_text(
            "⚠️ Не удалось сохранить желание.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    owner_id = user_id if choice == "me" else get_partner(user_id)

    data = load_data()

    data["wishes"].append(
        {
            "id": generate_id(),
            "owner_id": owner_id,
            "text": wish_text,
            "done": False,
        }
    )

    save_data(data)

    context.user_data.clear()

    await query.edit_message_text(
        "✅ Желание сохранено.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def show_wishes(
    update: Update, context: ContextTypes.DEFAULT_TYPE, owner_type: str
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()

    if owner_type == "mine":
        owner_id = user_id
        title = "🎁 <b>Мои желания</b>"
    else:
        owner_id = get_partner(user_id)
        title = "🎁 <b>Желания партнёра</b>"

    wishes = [
        wish for wish in data["wishes"] if wish["owner_id"] == owner_id
    ]

    keyboard = []

    for wish in wishes:
        status = "✅" if wish["done"] else "⬜️"

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{status} {wish['text']}",
                    callback_data=f"wish:view:{wish['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:wishes")])

    await query.edit_message_text(
        title,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def open_wish(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    wish_id = query.data.split(":")[2]

    data = load_data()
    wish = next(
        (item for item in data["wishes"] if item["id"] == wish_id),
        None,
    )

    if not wish:
        await query.edit_message_text("⚠️ Желание не найдено.")
        return

    status = "✅ Исполнено" if wish["done"] else "⬜️ Не исполнено"

    keyboard = [
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"wish:delete:{wish_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:wishes")],
    ]

    await query.edit_message_text(
        f"🎁 <b>Желание</b>\n\n{wish['text']}\n\nСтатус: {status}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def mark_wish_done_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    wishes = [
        wish for wish in data["wishes"] if not wish["done"]
    ]

    keyboard = []

    for wish in wishes:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"✅ {wish['text']}",
                    callback_data=f"wish:done_confirm:{wish['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:wishes")])

    await query.edit_message_text(
        "✅ <b>Выбери желание, которое исполнилось:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def mark_wish_done_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    wish_id = query.data.split(":")[2]

    data = load_data()
    wish = next(
        (item for item in data["wishes"] if item["id"] == wish_id),
        None,
    )

    if not wish:
        await query.edit_message_text("⚠️ Желание не найдено.")
        return

    wish["done"] = True
    save_data(data)

    await query.edit_message_text(
        f"✅ Желание «{wish['text']}» исполнено!",
        reply_markup=main_menu_keyboard(),
    )


async def delete_wish_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    wishes = data["wishes"]

    keyboard = []

    for wish in wishes:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🗑 {wish['text']}",
                    callback_data=f"wish:delete_confirm:{wish['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:wishes")])

    await query.edit_message_text(
        "🗑 <b>Выбери желание, которое удалить:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_wish_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    wish_id = query.data.split(":")[2]

    data = load_data()
    data["wishes"] = [
        item for item in data["wishes"] if item["id"] != wish_id
    ]

    save_data(data)

    await query.edit_message_text(
        "✅ Желание удалено.",
        reply_markup=main_menu_keyboard(),
    )


# ================== НАШИ ПЛАНЫ ==================

async def show_plans_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Добавить план", callback_data="plan:create")],
        [InlineKeyboardButton("🗓 Все планы", callback_data="plan:list")],
        [InlineKeyboardButton("✅ Отметить выполненным", callback_data="plan:done")],
        [InlineKeyboardButton("🗑 Удалить план", callback_data="plan:delete")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "🧸 <b>Наши планы</b>\n\nЗдесь можно сохранять идеи,\n"
        "фильмы, поездки и свидания.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_create_plan(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    await query.edit_message_text(
        "🧸 Напиши план.\n\n"
        "Например: Сходить в кино\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_PLAN_TEXT"


async def save_plan_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    plan_text = update.message.text.strip()

    if not plan_text:
        await update.message.reply_text("⚠️ Текст плана не может быть пустым.")
        return "WAITING_PLAN_TEXT"

    context.user_data["new_plan_text"] = plan_text

    keyboard = [
        [
            InlineKeyboardButton("📅 Добавить дату", callback_data="plan:when:date"),
            InlineKeyboardButton("🚫 Без даты", callback_data="plan:when:none"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="pick:cancel")],
    ]

    await update.message.reply_text(
        "📅 Добавить дату к плану?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return "WAITING_PLAN_TIME"


async def plan_time_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    choice = query.data.split(":")[2]

    if choice == "none":
        return await finish_plan_no_date(update, context)

    await open_date_picker(update, context, "plan")

    return "WAITING_PICK_DATE"


async def finish_plan_no_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    plan_text = context.user_data.get("new_plan_text")

    if not plan_text:
        await query.edit_message_text(
            "⚠️ Не удалось найти план. Попробуй создать его заново.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()

    data["plans"].append(
        {
            "id": generate_id(),
            "text": plan_text,
            "when": None,
            "done": False,
        }
    )

    save_data(data)

    context.user_data.clear()

    await query.edit_message_text(
        "✅ План сохранён.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def finish_plan_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, selected: datetime
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    plan_text = context.user_data.get("new_plan_text")

    if not plan_text:
        await query.edit_message_text(
            "⚠️ Не удалось найти план. Попробуй создать его заново.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()

    data["plans"].append(
        {
            "id": generate_id(),
            "text": plan_text,
            "when": selected.isoformat(),
            "done": False,
        }
    )

    save_data(data)

    context.user_data.clear()

    await query.edit_message_text(
        f"✅ План сохранён.\n\nДата: <b>{format_datetime(selected.isoformat())}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def show_plans_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    plans = data["plans"]

    plans.sort(
        key=lambda item: item["when"] or "9999-12-31T23:59:59"
    )

    keyboard = []

    for plan in plans:
        status = "✅" if plan["done"] else "⬜️"
        date_text = (
            f" — {format_datetime(plan['when'])}"
            if plan["when"]
            else ""
        )

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{status} {plan['text']}{date_text}",
                    callback_data=f"plan:view:{plan['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:plans")])

    await query.edit_message_text(
        "🗓 <b>Все планы</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def open_plan(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    plan_id = query.data.split(":")[2]

    data = load_data()
    plan = next(
        (item for item in data["plans"] if item["id"] == plan_id),
        None,
    )

    if not plan:
        await query.edit_message_text("⚠️ План не найден.")
        return

    status = "✅ Выполнен" if plan["done"] else "⬜️ Не выполнен"

    keyboard = [
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"plan:delete:{plan_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="plan:list")],
    ]

    await query.edit_message_text(
        f"🧸 <b>План</b>\n\n{plan['text']}\n\n"
        f"Дата: {format_datetime(plan['when'])}\n"
        f"Статус: {status}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def mark_plan_done_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    plans = [
        plan for plan in data["plans"] if not plan["done"]
    ]

    keyboard = []

    for plan in plans:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"✅ {plan['text']}",
                    callback_data=f"plan:done_confirm:{plan['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:plans")])

    await query.edit_message_text(
        "✅ <b>Выбери план, который выполнили:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def mark_plan_done_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    plan_id = query.data.split(":")[2]

    data = load_data()
    plan = next(
        (item for item in data["plans"] if item["id"] == plan_id),
        None,
    )

    if not plan:
        await query.edit_message_text("⚠️ План не найден.")
        return

    plan["done"] = True
    save_data(data)

    await query.edit_message_text(
        f"✅ План «{plan['text']}» выполнен!",
        reply_markup=main_menu_keyboard(),
    )


async def delete_plan_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    plans = data["plans"]

    keyboard = []

    for plan in plans:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🗑 {plan['text']}",
                    callback_data=f"plan:delete_confirm:{plan['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:plans")])

    await query.edit_message_text(
        "🗑 <b>Выбери план, который удалить:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_plan_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    plan_id = query.data.split(":")[2]

    data = load_data()
    data["plans"] = [
        item for item in data["plans"] if item["id"] != plan_id
    ]

    save_data(data)

    await query.edit_message_text(
        "✅ План удалён.",
        reply_markup=main_menu_keyboard(),
    )


# ================== НАСТРОЕНИЕ ==================

MOODS = {
    "great": "😍 Отлично",
    "good": "🙂 Хорошо",
    "normal": "😐 Нормально",
    "sad": "😔 Грустно",
    "tired": "😩 Устал(а)",
    "angry": "😡 Злюсь",
    "annoyed": "😡 Ты меня бесишь",
    "love": "🥰 Люблю",
}


async def show_moods_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("😊 Как моё настроение?", callback_data="mood:choose")],
        [InlineKeyboardButton("📊 История настроений", callback_data="mood:history")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "😊 <b>Настроение дня</b>\n\nЗдесь можно отмечать настроение\n"
        "и оставлять заметки. Всё видно вам обоим.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_mood_choices(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    keyboard = []

    row = []

    for mood_key, mood_name in MOODS.items():
        row.append(
            InlineKeyboardButton(
                mood_name,
                callback_data=f"mood:select:{mood_key}",
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:moods")])

    await query.edit_message_text(
        "😊 Как твоё настроение сегодня?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return "WAITING_MOOD_NOTE"


async def save_mood_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    mood_key = query.data.split(":")[2]
    context.user_data["new_mood"] = mood_key

    await query.edit_message_text(
        "📝 Хочешь добавить заметку к настроению?\n\n"
        "Напиши заметку или нажми «Без заметки».",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🚫 Без заметки", callback_data="mood:no_note")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu:moods")],
            ]
        ),
    )

    return "WAITING_MOOD_NOTE"


async def save_mood_note(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    mood_note = update.message.text.strip()
    mood_key = context.user_data.get("new_mood")

    if not mood_key:
        await update.message.reply_text(
            "⚠️ Не удалось сохранить настроение.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()

    data["moods"].append(
        {
            "id": generate_id(),
            "user_id": user_id,
            "mood": mood_key,
            "note": mood_note,
            "date": now_moscow().isoformat(),
        }
    )

    save_data(data)

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ Настроение сохранено: {MOODS[mood_key]}",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def save_mood_without_note(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    mood_key = context.user_data.get("new_mood")

    if not mood_key:
        await query.edit_message_text(
            "⚠️ Не удалось сохранить настроение.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()

    data["moods"].append(
        {
            "id": generate_id(),
            "user_id": user_id,
            "mood": mood_key,
            "note": None,
            "date": now_moscow().isoformat(),
        }
    )

    save_data(data)

    context.user_data.clear()

    await query.edit_message_text(
        f"✅ Настроение сохранено: {MOODS[mood_key]}",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def show_mood_history(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    moods = data["moods"]

    moods.sort(key=lambda item: item["date"], reverse=True)

    text = "📊 <b>История настроений</b>\n\n"

    if not moods:
        text += "Пока нет настроений."
    else:
        for mood in moods[:20]:
            mood_name = MOODS.get(mood["mood"], "Настроение")
            note_text = f"\n📝 {mood['note']}" if mood["note"] else ""

            text += (
                f"{format_datetime(mood['date'])} — {mood_name}"
                f"{note_text}\n\n"
            )

    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:moods")]
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ================== ПЛЕЙЛИСТ ==================

async def show_playlist_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Добавить песню", callback_data="song:create")],
        [InlineKeyboardButton("🎧 Открыть плейлист", callback_data="song:list")],
        [InlineKeyboardButton("🎲 Случайная песня", callback_data="song:random")],
        [InlineKeyboardButton("✏️ Добавить подпись", callback_data="song:caption")],
        [InlineKeyboardButton("🗑 Удалить песню", callback_data="song:delete")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "🎵 <b>Наш плейлист</b>\n\nЗдесь можно сохранять ваши песни,\n"
        "ссылки и подписи к ним.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_create_song(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    await query.edit_message_text(
        "🎵 Напиши название песни.\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_SONG_TITLE"


async def save_song_title(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    title = update.message.text.strip()

    if not title:
        await update.message.reply_text("⚠️ Название не может быть пустым.")
        return "WAITING_SONG_TITLE"

    context.user_data["new_song_title"] = title

    await update.message.reply_text(
        "🎤 Напиши исполнителя.\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_SONG_ARTIST"


async def save_song_artist(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    artist = update.message.text.strip()

    if not artist:
        await update.message.reply_text("⚠️ Исполнитель не может быть пустым.")
        return "WAITING_SONG_ARTIST"

    context.user_data["new_song_artist"] = artist

    await update.message.reply_text(
        "🔗 Отправь ссылку на песню.\n\n"
        "Например: https://youtube.com/...\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_SONG_URL"


async def save_song_url(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    url = update.message.text.strip()

    if not url.startswith(("http://", "https://")):
        await update.message.reply_text(
            "⚠️ Ссылка должна начинаться с http:// или https://\n"
            "Попробуй ещё раз или отправь /cancel"
        )
        return "WAITING_SONG_URL"

    context.user_data["new_song_url"] = url

    await update.message.reply_text(
        "✏️ Напиши подпись к песне или нажми «Без подписи».",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🚫 Без подписи", callback_data="song:no_caption")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu:playlist")],
            ]
        ),
    )

    return "WAITING_SONG_CAPTION"


async def save_song_caption(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    caption = update.message.text.strip()
    title = context.user_data.get("new_song_title")
    artist = context.user_data.get("new_song_artist")
    url = context.user_data.get("new_song_url")

    if not title or not artist or not url:
        await update.message.reply_text(
            "⚠️ Не удалось сохранить песню.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()

    data["playlist"].append(
        {
            "id": generate_id(),
            "title": title,
            "artist": artist,
            "url": url,
            "caption": caption,
            "added_by": user_id,
        }
    )

    save_data(data)

    context.user_data.clear()

    await update.message.reply_text(
        "✅ Песня добавлена в плейлист.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def save_song_without_caption(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    title = context.user_data.get("new_song_title")
    artist = context.user_data.get("new_song_artist")
    url = context.user_data.get("new_song_url")

    if not title or not artist or not url:
        await query.edit_message_text(
            "⚠️ Не удалось сохранить песню.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()

    data["playlist"].append(
        {
            "id": generate_id(),
            "title": title,
            "artist": artist,
            "url": url,
            "caption": None,
            "added_by": user_id,
        }
    )

    save_data(data)

    context.user_data.clear()

    await query.edit_message_text(
        "✅ Песня добавлена в плейлист.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def show_playlist(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    songs = data["playlist"]

    keyboard = []

    for song in songs:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🎧 {song['title']} — {song['artist']}",
                    url=song["url"],
                )
            ]
        )

        if song["caption"]:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"✏️ {song['caption']}",
                        callback_data=f"song:view:{song['id']}",
                    )
                ]
            )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:playlist")])

    await query.edit_message_text(
        "🎧 <b>Наш плейлист</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_random_song(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    songs = data["playlist"]

    if not songs:
        await query.edit_message_text(
            "🎲 В плейлисте пока нет песен.",
            reply_markup=main_menu_keyboard(),
        )
        return

    song = random.choice(songs)

    caption = f"\n\n✏️ {song['caption']}" if song["caption"] else ""

    keyboard = [
        [InlineKeyboardButton("🔗 Открыть", url=song["url"])],
        [InlineKeyboardButton("🎲 Ещё раз", callback_data="song:random")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:playlist")],
    ]

    await query.edit_message_text(
        f"🎲 <b>Случайная песня</b>\n\n"
        f"🎧 {song['title']}\n"
        f"🎤 {song['artist']}"
        f"{caption}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def choose_song_for_caption(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    data = load_data()
    songs = data["playlist"]

    keyboard = []

    for song in songs:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🎧 {song['title']} — {song['artist']}",
                    callback_data=f"song:caption_select:{song['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:playlist")])

    await query.edit_message_text(
        "✏️ <b>Выбери песню для подписи:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return "WAITING_SONG_CAPTION_EDIT"


async def ask_song_caption(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    song_id = query.data.split(":")[2]
    context.user_data["caption_song_id"] = song_id

    await query.edit_message_text(
        "✏️ Напиши подпись к песне.\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_NEW_SONG_CAPTION"


async def save_song_caption_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    caption = update.message.text.strip()
    song_id = context.user_data.get("caption_song_id")

    if not song_id:
        await update.message.reply_text(
            "⚠️ Не удалось найти песню.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    data = load_data()
    song = next(
        (item for item in data["playlist"] if item["id"] == song_id),
        None,
    )

    if not song:
        await update.message.reply_text(
            "⚠️ Песня не найдена.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    song["caption"] = caption
    save_data(data)

    await update.message.reply_text(
        "✅ Подпись сохранена.",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def delete_song_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    songs = data["playlist"]

    keyboard = []

    for song in songs:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🗑 {song['title']} — {song['artist']}",
                    callback_data=f"song:delete_confirm:{song['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:playlist")])

    await query.edit_message_text(
        "🗑 <b>Выбери песню, которую удалить:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_song_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    song_id = query.data.split(":")[2]

    data = load_data()
    data["playlist"] = [
        item for item in data["playlist"] if item["id"] != song_id
    ]

    save_data(data)

    await query.edit_message_text(
        "✅ Песня удалена.",
        reply_markup=main_menu_keyboard(),
    )


# ================== ПОДДЕРЖКА ==================

async def show_support_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🆘 Мне нужна поддержка", callback_data="support:need")],
        [InlineKeyboardButton("💬 Давай поговорим", callback_data="support:talk")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "🤍 <b>Мне нужна поддержка</b>\n\n"
        "Если нажмёшь «Мне нужна поддержка»,\n"
        "партнёр сразу получит уведомление.\n\n"
        "Если нажмёшь «Давай поговорим»,\n"
        "партнёр тоже сразу получит уведомление.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def send_support_need(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    partner_id = get_partner(user_id)

    try:
        await context.bot.send_message(
            chat_id=partner_id,
            text=(
                "🤍 <b>Тебе нужна поддержка</b>\n\n"
                "Партнёр написал, что ему сейчас нужна поддержка."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "💬 Давай поговорим",
                            callback_data=f"support:talk_back:{user_id}",
                        )
                    ]
                ]
            ),
        )
    except Exception:
        pass

    await query.edit_message_text(
        "✅ Партнёр получил уведомление.",
        reply_markup=main_menu_keyboard(),
    )


async def send_support_talk(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    partner_id = get_partner(user_id)

    try:
        await context.bot.send_message(
            chat_id=partner_id,
            text="💬 Партнёр хочет поговорить.",
        )
    except Exception:
        pass

    await query.edit_message_text(
        "✅ Партнёр получил уведомление.",
        reply_markup=main_menu_keyboard(),
    )


async def send_support_talk_back(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    requester_id = int(query.data.split(":")[2])

    try:
        await context.bot.send_message(
            chat_id=requester_id,
            text="💬 Партнёр готов поговорить.",
        )
    except Exception:
        pass

    await query.edit_message_text(
        "✅ Партнёр получил уведомление.",
        reply_markup=main_menu_keyboard(),
    )


# ================== КАПСУЛЫ ==================

async def show_capsules_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Создать капсулу", callback_data="capsule:create")],
        [InlineKeyboardButton("📦 Мои капсулы", callback_data="capsule:mine")],
        [InlineKeyboardButton("📦 Капсулы партнёра", callback_data="capsule:partner")],
        [InlineKeyboardButton("🗑 Удалить капсулу", callback_data="capsule:delete")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:main")],
    ]

    await query.edit_message_text(
        "⏳ <b>Капсула времени</b>\n\nЗдесь можно создать сообщение,\n"
        "которое откроется в выбранную дату и время.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start_create_capsule(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    await query.edit_message_text(
        "⏳ Напиши сообщение для капсулы.\n\n"
        "Чтобы отменить, отправь /cancel",
        parse_mode="HTML",
    )

    return "WAITING_CAPSULE_TEXT"


async def save_capsule_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> str:
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        await update.effective_message.reply_text("⛔ Нет доступа.")
        return ConversationHandler.END

    capsule_text = update.message.text.strip()

    if not capsule_text:
        await update.message.reply_text("⚠️ Текст капсулы не может быть пустым.")
        return "WAITING_CAPSULE_TEXT"

    context.user_data["new_capsule_text"] = capsule_text

    await open_date_picker(update, context, "capsule")

    return "WAITING_PICK_DATE"


async def finish_capsule_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE, selected: datetime
) -> str:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    capsule_text = context.user_data.get("new_capsule_text")

    if not capsule_text:
        await query.edit_message_text(
            "⚠️ Не удалось найти текст капсулы. Попробуй создать её заново.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    context.user_data["new_capsule_when"] = selected.isoformat()

    keyboard = [
        [
            InlineKeyboardButton("🤍 Для меня", callback_data="capsule:to:me"),
            InlineKeyboardButton("🤍 Для партнёра", callback_data="capsule:to:partner"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="pick:cancel")],
    ]

    await query.edit_message_text(
        f"📅 Капсула откроется:\n<b>{format_datetime(selected.isoformat())}</b>\n\n"
        "Для кого эта капсула?",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return "WAITING_CAPSULE_OWNER"


async def save_capsule_owner(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return ConversationHandler.END

    await query.answer()

    choice = query.data.split(":")[2]
    capsule_text = context.user_data.get("new_capsule_text")
    capsule_when = context.user_data.get("new_capsule_when")

    if not capsule_text or not capsule_when:
        await query.edit_message_text(
            "⚠️ Не удалось создать капсулу.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    to_id = user_id if choice == "me" else get_partner(user_id)

    data = load_data()

    data["capsules"].append(
        {
            "id": generate_id(),
            "from_id": user_id,
            "to_id": to_id,
            "text": capsule_text,
            "open_at": capsule_when,
            "opened": False,
        }
    )

    save_data(data)

    context.user_data.clear()

    await query.edit_message_text(
        f"✅ Капсула создана.\n\n"
        f"Она откроется:\n<b>{format_datetime(capsule_when)}</b>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    return ConversationHandler.END


async def show_capsules(
    update: Update, context: ContextTypes.DEFAULT_TYPE, owner_type: str
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()

    if owner_type == "mine":
        from_id = user_id
        title = "📦 <b>Мои капсулы</b>"
    else:
        from_id = get_partner(user_id)
        title = "📦 <b>Капсулы партнёра</b>"

    capsules = [
        capsule for capsule in data["capsules"] if capsule["from_id"] == from_id
    ]

    capsules.sort(key=lambda item: item["open_at"])

    keyboard = []

    for capsule in capsules:
        status = "🔓" if capsule["opened"] else "🔒"

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{status} Капсула — {format_datetime(capsule['open_at'])}",
                    callback_data=f"capsule:view:{capsule['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:capsules")])

    await query.edit_message_text(
        title,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def open_capsule(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    capsule_id = query.data.split(":")[2]

    data = load_data()
    capsule = next(
        (item for item in data["capsules"] if item["id"] == capsule_id),
        None,
    )

    if not capsule:
        await query.edit_message_text("⚠️ Капсула не найдена.")
        return

    if not capsule["opened"]:
        text = "🔒 Капсула ещё закрыта."
    else:
        text = f"⏳ <b>Капсула открыта</b>\n\n{capsule['text']}"

    keyboard = [
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"capsule:delete:{capsule_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="menu:capsules")],
    ]

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_capsule_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    data = load_data()
    capsules = data["capsules"]

    keyboard = []

    for capsule in capsules:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🗑 Капсула — {format_datetime(capsule['open_at'])}",
                    callback_data=f"capsule:delete_confirm:{capsule['id']}",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu:capsules")])

    await query.edit_message_text(
        "🗑 <b>Выбери капсулу, которую удалить:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_capsule_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    capsule_id = query.data.split(":")[2]

    data = load_data()
    data["capsules"] = [
        item for item in data["capsules"] if item["id"] != capsule_id
    ]

    save_data(data)

    await query.edit_message_text(
        "✅ Капсула удалена.",
        reply_markup=main_menu_keyboard(),
    )


# ================== АВТООТПРАВКА ==================

async def check_scheduled(
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    data = load_data()
    current_time = now_moscow()
    changed = False

    for note in data["notes"]:
        if note["status"] != "scheduled":
            continue

        try:
            send_time = datetime.fromisoformat(note["send_at"])
        except (ValueError, TypeError):
            continue

        if send_time > current_time:
            continue

        try:
            await context.bot.send_message(
                chat_id=note["to_id"],
                text=f"💌 <b>Тебе пришла записка</b>\n\n{note['text']}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "💬 Ответить",
                                callback_data=f"note:reply:{note['id']}",
                            )
                        ]
                    ]
                ),
            )

            note["status"] = "sent"
            changed = True
        except Exception:
            continue

    for date_item in data["dates"]:
        try:
            date_time = datetime.fromisoformat(date_item["when"])
        except (ValueError, TypeError):
            continue

        if date_time > current_time:
            continue

        for user_id in ALLOWED_USER_IDS:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"📅 <b>Сегодня важная дата</b>\n\n"
                        f"{date_item['name']}"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                continue

        if date_item["repeat"] == "yearly":
            date_item["when"] = (
                date_time + timedelta(days=365)
            ).isoformat()
            changed = True

        elif date_item["repeat"] == "monthly":
            month = date_time.month + 1
            year = date_time.year

            if month > 12:
                month = 1
                year += 1

            date_item["when"] = date_time.replace(
                year=year,
                month=month,
            ).isoformat()
            changed = True

        else:
            data["dates"] = [
                item for item in data["dates"] if item["id"] != date_item["id"]
            ]

        changed = True

    for capsule in data["capsules"]:
        if capsule["opened"]:
            continue

        try:
            open_time = datetime.fromisoformat(capsule["open_at"])
        except (ValueError, TypeError):
            continue

        if open_time > current_time:
            continue

        try:
            await context.bot.send_message(
                chat_id=capsule["to_id"],
                text=(
                    f"⏳ <b>Капсула времени открылась</b>\n\n"
                    f"{capsule['text']}"
                ),
                parse_mode="HTML",
            )

            capsule["opened"] = True
            changed = True
        except Exception:
            continue

    for plan in data["plans"]:
        if not plan["when"] or plan["done"]:
            continue

        try:
            plan_time = datetime.fromisoformat(plan["when"])
        except (ValueError, TypeError):
            continue

        if plan_time > current_time:
            continue

        for user_id in ALLOWED_USER_IDS:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🧸 <b>Время плана</b>\n\n"
                        f"{plan['text']}"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                continue

        plan["done"] = True
        changed = True

    if changed:
        save_data(data)


# ================== НАЖАТИЯ КНОПОК ==================

async def button_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    if not is_allowed(user_id):
        await query.answer("⛔ Нет доступа.")
        return

    await query.answer()

    action = query.data

    if action == "menu:main":
        await query.edit_message_text(
            "🤍 <b>Наш личный бот</b>\n\nВыбери раздел:",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )

    elif action == "menu:notes":
        await show_notes_menu(update, context)

    elif action == "menu:dates":
        await show_dates_menu(update, context)

    elif action == "menu:wishes":
        await show_wishes_menu(update, context)

    elif action == "menu:plans":
        await show_plans_menu(update, context)

    elif action == "menu:moods":
        await show_moods_menu(update, context)

    elif action == "menu:playlist":
        await show_playlist_menu(update, context)

    elif action == "menu:support":
        await show_support_menu(update, context)

    elif action == "menu:capsules":
        await show_capsules_menu(update, context)

    elif action == "note:create":
        await start_create_note(update, context)

    elif action == "note:list":
        await show_notes_list(update, context)

    elif action == "note:delete":
        await delete_note_menu(update, context)

    elif action.startswith("note:view:"):
        await open_note(update, context)

    elif action.startswith("note:reply:"):
        await start_note_reply(update, context)

    elif action.startswith("note:delete_confirm:"):
        await delete_note_confirm(update, context)

    elif action == "date:create":
        await start_create_date(update, context)

    elif action == "date:list":
        await show_dates_list(update, context)

    elif action == "date:nearest":
        await show_nearest_dates(update, context)

    elif action == "date:delete":
        await delete_date_menu(update, context)

    elif action.startswith("date:view:"):
        await open_date(update, context)

    elif action.startswith("date:repeat:"):
        await save_date_repeat(update, context)

    elif action.startswith("date:delete_confirm:"):
        await delete_date_confirm(update, context)

    elif action == "wish:create":
        await start_create_wish(update, context)

    elif action == "wish:mine":
        await show_wishes(update, context, "mine")

    elif action == "wish:partner":
        await show_wishes(update, context, "partner")

    elif action == "wish:done":
        await mark_wish_done_menu(update, context)

    elif action == "wish:delete":
        await delete_wish_menu(update, context)

    elif action.startswith("wish:view:"):
        await open_wish(update, context)

    elif action.startswith("wish:owner:"):
        await save_wish_owner(update, context)

    elif action.startswith("wish:done_confirm:"):
        await mark_wish_done_confirm(update, context)

    elif action.startswith("wish:delete_confirm:"):
        await delete_wish_confirm(update, context)

    elif action == "plan:create":
        await start_create_plan(update, context)

    elif action == "plan:list":
        await show_plans_list(update, context)

    elif action == "plan:done":
        await mark_plan_done_menu(update, context)

    elif action == "plan:delete":
        await delete_plan_menu(update, context)

    elif action.startswith("plan:view:"):
        await open_plan(update, context)

    elif action.startswith("plan:when:"):
        await plan_time_handler(update, context)

    elif action.startswith("plan:done_confirm:"):
        await mark_plan_done_confirm(update, context)

    elif action.startswith("plan:delete_confirm:"):
        await delete_plan_confirm(update, context)

    elif action == "mood:choose":
        await show_mood_choices(update, context)

    elif action == "mood:history":
        await show_mood_history(update, context)

    elif action.startswith("mood:select:"):
        await save_mood_choice(update, context)

    elif action == "mood:no_note":
        await save_mood_without_note(update, context)

    elif action == "song:create":
        await start_create_song(update, context)

    elif action == "song:list":
        await show_playlist(update, context)

    elif action == "song:random":
        await show_random_song(update, context)

    elif action == "song:caption":
        await choose_song_for_caption(update, context)

    elif action == "song:delete":
        await delete_song_menu(update, context)

    elif action == "song:no_caption":
        await save_song_without_caption(update, context)

    elif action.startswith("song:caption_select:"):
        await ask_song_caption(update, context)

    elif action.startswith("song:delete_confirm:"):
        await delete_song_confirm(update, context)

    elif action == "support:need":
        await send_support_need(update, context)

    elif action == "support:talk":
        await send_support_talk(update, context)

    elif action.startswith("support:talk_back:"):
        await send_support_talk_back(update, context)

    elif action == "capsule:create":
        await start_create_capsule(update, context)

    elif action == "capsule:mine":
        await show_capsules(update, context, "mine")

    elif action == "capsule:partner":
        await show_capsules(update, context, "partner")

    elif action == "capsule:delete":
        await delete_capsule_menu(update, context)

    elif action.startswith("capsule:view:"):
        await open_capsule(update, context)

    elif action.startswith("capsule:to:"):
        await save_capsule_owner(update, context)

    elif action.startswith("capsule:delete_confirm:"):
        await delete_capsule_confirm(update, context)

    elif action.startswith("pick:"):
        await date_picker_handler(update, context)


# ================== ЗАПУСК ==================

def main() -> None:
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не найдена. "
            "Добавь её в Railway в разделе Variables."
        )

    application = Application.builder().token(token).build()

    note_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_create_note, pattern="^note:create$")
        ],
        states={
            "WAITING_NOTE_TEXT": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_note_text)
            ],
            "WAITING_NOTE_TIME": [
                CallbackQueryHandler(note_time_handler, pattern="^note:when:")
            ],
            "WAITING_PICK_DATE": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
            "WAITING_PICK_HOUR": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
            "WAITING_PICK_MINUTE": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
            "WAITING_NOTE_REPLY": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_note_reply)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_action)],
        allow_reentry=True,
    )

    date_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_create_date, pattern="^date:create$")
        ],
        states={
            "WAITING_DATE_NAME": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_date_name)
            ],
            "WAITING_PICK_DATE": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
            "WAITING_PICK_HOUR": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
            "WAITING_PICK_MINUTE": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
            "WAITING_DATE_REPEAT": [
                CallbackQueryHandler(save_date_repeat, pattern="^date:repeat:")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_action)],
        allow_reentry=True,
    )

    wish_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_create_wish, pattern="^wish:create$")
        ],
        states={
            "WAITING_WISH_TEXT": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_wish_text)
            ],
            "WAITING_WISH_OWNER": [
                CallbackQueryHandler(save_wish_owner, pattern="^wish:owner:")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_action)],
        allow_reentry=True,
    )

    plan_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_create_plan, pattern="^plan:create$")
        ],
        states={
            "WAITING_PLAN_TEXT": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_plan_text)
            ],
            "WAITING_PLAN_TIME": [
                CallbackQueryHandler(plan_time_handler, pattern="^plan:when:")
            ],
            "WAITING_PICK_DATE": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
            "WAITING_PICK_HOUR": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
            "WAITING_PICK_MINUTE": [
                CallbackQueryHandler(date_picker_handler, pattern="^pick:")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_action)],
        allow_reentry=True,
    )

    mood_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(show_mood_choices, pattern="^mood:choose$")
        ],
        states={
            "WAITING_MOOD_NOTE": [
                CallbackQueryHandler(save_mood_choice, pattern="^mood:select:"),
                CallbackQueryHandler(
                    save_mood_without_note,
                    pattern="^mood:no_note$",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_mood_note),
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_action)],
        allow_reentry=True,
    )

    song_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_create_song, pattern="^song:create$")
        ],
        states={
            "WAITING_SONG_TITLE": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_song_title)
            ],
            "WAITING_SONG_ARTIST": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_song_artist)
            ],
            "WAITING_SONG_URL": [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_song_url)
            ],
            "WAITING_SONG_CAPTION": [
                CallbackQueryHandler(
                    save_song_without_caption,
                    pattern="^song:no_caption$",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_song_caption),
            ],
            "WAITING_SONG_CAPTION_EDIT": [
                CallbackQueryHandler(
                    ask_song_caption,
                    pattern="^song:caption_select:",
                )
            ],
            "WAITING_NEW_SONG_CAPTION": [
