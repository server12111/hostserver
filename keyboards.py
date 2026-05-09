import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

TEXT_MY_BOTS = "📦 Мої боти"
TEXT_ADD_BOT = "➕ Додати бота"
TEXT_START_BOT = "▶️ Запустити"
TEXT_STOP_BOT = "⏹ Зупинити"
TEXT_DELETE = "🗑 Видалити"
TEXT_LOGS = "📋 Логи"
TEXT_BACK = "🔙 Назад"
TEXT_REFRESH = "🔄 Оновити"
TEXT_YES_DELETE = "✅ Так, видалити"
TEXT_CANCEL = "❌ Скасувати"
TEXT_PACKAGES = "⚙️ Пакети"
TEXT_CONFIG = "📝 Конфіг"

STATUS_ICON = {"running": "🟢", "stopped": "🔴"}


def sanitize_bot_name(raw: str, max_len: int = 49) -> str:
    name = re.sub(r"[^a-z0-9_]", "_", raw.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:max_len] or "bot"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(TEXT_MY_BOTS, callback_data="my_bots"),
            InlineKeyboardButton(TEXT_ADD_BOT, callback_data="add_bot"),
        ]
    ])


def bot_list_keyboard(bots: list[dict], manager) -> InlineKeyboardMarkup:
    rows = []
    for bot in bots:
        name = bot["name"]
        is_running = manager.is_running(name)
        icon = STATUS_ICON["running"] if is_running else STATUS_ICON["stopped"]
        label = f"{icon} {name}"
        rows.append([InlineKeyboardButton(label, callback_data=f"bot_info:{name}")])
    rows.append([InlineKeyboardButton(TEXT_BACK, callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def bot_detail_keyboard(bot_name: str, is_running: bool) -> InlineKeyboardMarkup:
    if is_running:
        action_btn = InlineKeyboardButton(TEXT_STOP_BOT, callback_data=f"stop_bot:{bot_name}")
    else:
        action_btn = InlineKeyboardButton(TEXT_START_BOT, callback_data=f"start_bot:{bot_name}")
    return InlineKeyboardMarkup([
        [action_btn],
        [
            InlineKeyboardButton(TEXT_LOGS, callback_data=f"logs:{bot_name}"),
            InlineKeyboardButton(TEXT_CONFIG, callback_data=f"config:{bot_name}"),
        ],
        [InlineKeyboardButton(TEXT_PACKAGES, callback_data=f"packages:{bot_name}")],
        [InlineKeyboardButton(TEXT_DELETE, callback_data=f"delete:{bot_name}")],
        [InlineKeyboardButton(TEXT_BACK, callback_data="my_bots")],
    ])


def delete_confirm_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(TEXT_YES_DELETE, callback_data=f"confirm_del:{bot_name}"),
            InlineKeyboardButton(TEXT_CANCEL, callback_data=f"bot_info:{bot_name}"),
        ]
    ])


def config_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Редагувати", callback_data=f"edit_config:{bot_name}")],
        [InlineKeyboardButton(TEXT_BACK, callback_data=f"bot_info:{bot_name}")],
    ])


def config_edit_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXT_CANCEL, callback_data=f"config:{bot_name}")]
    ])


def packages_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TEXT_BACK, callback_data=f"bot_info:{bot_name}")]
    ])


def logs_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(TEXT_REFRESH, callback_data=f"logs:{bot_name}"),
            InlineKeyboardButton(TEXT_BACK, callback_data=f"bot_info:{bot_name}"),
        ]
    ])
