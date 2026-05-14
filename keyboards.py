import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from payments import PLANS, CURRENCIES

# ─── Status icons ─────────────────────────────────────────────────────────────
STATUS_ICON = {"running": "🟢", "stopped": "🔴"}

# ─── Premium emoji IDs ────────────────────────────────────────────────────────
_E = {
    "settings":  "5870982283724328568",
    "profile":   "5870994129244131212",
    "users":     "5870772616305839506",
    "check":     "5870633910337015697",
    "cross":     "5870657884844462243",
    "bot":       "6030400221232501136",
    "home":      "5873147866364514353",
    "stats":     "5870921681735781843",
    "lock":      "6037249452824072506",
    "megaphone": "6039422865189638057",
    "pencil":    "5870676941614354370",
    "trash":     "5870875489362513438",
    "file":      "5870528606328852614",
    "info":      "6028435952299413210",
    "download":  "6039802767931871481",
    "wallet":    "5769126056262898415",
    "gift":      "6032644646587338669",
    "money":     "5904462880941545555",
    "loading":   "5345906554510012647",
    "celebrate": "6041731551845159060",
    "notify":    "6039486778597970865",
    "package":   "5884479287171485878",
    "eye":       "6037397706505195857",
    "upload":    "5963103826075456248",
}


def pe(key: str, fallback: str = "•") -> str:
    """Premium emoji HTML tag for use in HTML-formatted messages."""
    return f'<tg-emoji emoji-id="{_E[key]}">{fallback}</tg-emoji>'


def _btn(text: str, ekey: str = None, callback_data: str = None, url: str = None) -> InlineKeyboardButton:
    """InlineKeyboardButton with premium emoji icon (no plain emoji in text)."""
    kwargs = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url
    if ekey:
        kwargs["api_kwargs"] = {"icon_custom_emoji_id": _E[ekey]}
    return InlineKeyboardButton(**kwargs)


# ─── Утилиты ──────────────────────────────────────────────────────────────────
def sanitize_bot_name(raw: str, max_len: int = 35) -> str:
    name = re.sub(r"[^a-z0-9_]", "_", raw.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:max_len] or "bot"


def make_bot_key(display_name: str, user_id: int) -> str:
    return f"{sanitize_bot_name(display_name)}_{user_id}"


# ─── Главное меню ─────────────────────────────────────────────────────────────
def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("Мои боты",      "bot",    callback_data="my_bots"),
            _btn("Добавить бота", "upload", callback_data="add_bot"),
        ],
        [_btn("Мой хостинг", "wallet", callback_data="balance")],
    ])


# ─── Список ботов ─────────────────────────────────────────────────────────────
def bot_list_keyboard(bots: list[dict], manager) -> InlineKeyboardMarkup:
    rows = []
    for bot in bots:
        name = bot["name"]
        display = bot.get("display_name", name)
        if bot.get("worker_id"):
            is_running = bot.get("status") == "running"
        else:
            is_running = manager.is_running(name)
        icon = STATUS_ICON["running"] if is_running else STATUS_ICON["stopped"]
        rows.append([_btn(f"{icon} {display}", "bot", callback_data=f"bot_info:{name}")])
    rows.append([_btn("Главное меню", "home", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ─── Детали бота ──────────────────────────────────────────────────────────────
def bot_detail_keyboard(bot_name: str, is_running: bool) -> InlineKeyboardMarkup:
    action = (
        _btn("Остановить", "cross", callback_data=f"stop_bot:{bot_name}")
        if is_running else
        _btn("Запустить",  "check", callback_data=f"start_bot:{bot_name}")
    )
    return InlineKeyboardMarkup([
        [action, _btn("Перезапуск", "loading", callback_data=f"restart_bot:{bot_name}")],
        [
            _btn("Логи",   "eye",    callback_data=f"logs:{bot_name}"),
            _btn("Конфиг", "pencil", callback_data=f"config:{bot_name}"),
        ],
        [
            _btn("Пакеты", "package", callback_data=f"packages:{bot_name}"),
            _btn("Файлы",  "file",    callback_data=f"files:{bot_name}"),
        ],
        [_btn("Обновити код",   "upload", callback_data=f"update_bot:{bot_name}")],
        [_btn("Видалити бота",  "trash",  callback_data=f"delete:{bot_name}")],
        [_btn("До списку ботів","bot",    callback_data="my_bots")],
    ])


def update_source_keyboard(bot_name: str, has_git: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_git:
        rows.append([_btn("Обновить из Git",    "info",    callback_data=f"update_git:{bot_name}")])
    rows.append([    _btn("Загрузить новый ZIP", "package", callback_data=f"update_zip:{bot_name}")])
    rows.append([    _btn("Отмена",              "cross",   callback_data=f"bot_info:{bot_name}")])
    return InlineKeyboardMarkup(rows)


# ─── Подтверждение удаления ───────────────────────────────────────────────────
def delete_confirm_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("Да, удалить", "trash", callback_data=f"confirm_del:{bot_name}"),
            _btn("Отмена",      "cross", callback_data=f"bot_info:{bot_name}"),
        ]
    ])


# ─── Логи ─────────────────────────────────────────────────────────────────────
def logs_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("Обновить логи", "loading", callback_data=f"logs:{bot_name}"),
            _btn("Назад",         "bot",     callback_data=f"bot_info:{bot_name}"),
        ]
    ])


# ─── Конфиг ───────────────────────────────────────────────────────────────────
def config_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("Редактировать", "pencil", callback_data=f"edit_config:{bot_name}")],
        [_btn("Назад",         "bot",    callback_data=f"bot_info:{bot_name}")],
    ])


def config_edit_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("Отмена", "cross", callback_data=f"config:{bot_name}")]
    ])


# ─── Пакеты ───────────────────────────────────────────────────────────────────
def packages_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("Назад", "bot", callback_data=f"bot_info:{bot_name}")]
    ])


# ─── Файлы ────────────────────────────────────────────────────────────────────
def files_keyboard(bot_name: str, files: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, fname in enumerate(files[:20]):
        rows.append([_btn(fname, "file", callback_data=f"dl_file:{bot_name}:{i}")])
    rows.append([_btn("Назад", "bot", callback_data=f"bot_info:{bot_name}")])
    return InlineKeyboardMarkup(rows)


# ─── Источник бота ────────────────────────────────────────────────────────────
def add_source_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("ZIP-архив",       "package", callback_data="add_zip"),
            _btn("Git репозиторий", "info",    callback_data="add_git"),
        ],
        [_btn("Главное меню", "home", callback_data="menu")],
    ])


# ─── Хостинг ──────────────────────────────────────────────────────────────────
def balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("Купить хостинг-слот", "money", callback_data="plans")],
        [_btn("Главное меню",        "home",  callback_data="menu")],
    ])


def plans_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PLANS.items():
        label = f"{plan['ram']} RAM — {plan['price']} USDT/мес"
        rows.append([_btn(label, "money", callback_data=f"buy_plan:{key}")])
    rows.append([_btn("Назад", "wallet", callback_data="balance")])
    return InlineKeyboardMarkup(rows)


def currency_keyboard(plan_key: str) -> InlineKeyboardMarkup:
    rows = [[_btn(c, "money", callback_data=f"pay_currency:{plan_key}:{c}")]
            for c in CURRENCIES]
    rows.append([_btn("Оплатить TON", "gift",  callback_data=f"pay_ton:{plan_key}")])
    rows.append([_btn("Назад",        "money", callback_data="plans")])
    return InlineKeyboardMarkup(rows)


def payment_keyboard(pay_url: str, plan_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("Оплатить сейчас", "check", url=pay_url)],
        [_btn("Назад",           "money", callback_data="plans")],
    ])


def ton_payment_keyboard(plan_key: str, wallet: str = "", amount_ton: float = 0, comment: str = "") -> InlineKeyboardMarkup:
    rows = []
    if wallet and amount_ton:
        amount_nano = int(amount_ton * 1_000_000_000)
        tonkeeper_url = f"https://app.tonkeeper.com/transfer/{wallet}?amount={amount_nano}&text={comment}"
        rows.append([_btn("Открыть TonKeeper", "gift", url=tonkeeper_url)])
    rows.append([_btn("Я оплатил", "check", callback_data=f"ton_check:{plan_key}")])
    rows.append([_btn("Назад",     "money", callback_data=f"buy_plan:{plan_key}")])
    return InlineKeyboardMarkup(rows)


# ─── Админ-панель ─────────────────────────────────────────────────────────────
def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("Пользователи", "users",     callback_data="admin_users"),
            _btn("Все боты",     "bot",       callback_data="admin_bots"),
        ],
        [
            _btn("Ресурсы", "stats",     callback_data="admin_resources"),
            _btn("Воркеры", "megaphone", callback_data="admin_workers"),
        ],
        [
            _btn("Скачать БД",  "download", callback_data="admin_download_db"),
            _btn("Загрузить БД","upload",   callback_data="admin_upload_db"),
        ],
        [_btn("Главное меню", "home", callback_data="menu")],
    ])


def workers_keyboard(workers: list[dict], statuses: dict) -> InlineKeyboardMarkup:
    rows = []
    for w in workers:
        icon = "🟢" if statuses.get(w["id"]) else "🔴"
        rows.append([_btn(
            f"{icon} {w['label']} ({w['url']})",
            "megaphone",
            callback_data=f"admin_worker:{w['id']}",
        )])
    rows.append([_btn("Добавить воркер", "notify",   callback_data="admin_add_worker")])
    rows.append([_btn("Назад",           "settings", callback_data="admin_menu")])
    return InlineKeyboardMarkup(rows)


def worker_detail_keyboard(worker_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _btn("Ресурсы", "stats", callback_data=f"admin_worker_res:{worker_id}"),
            _btn("Удалить", "trash", callback_data=f"admin_worker_del:{worker_id}"),
        ],
        [_btn("Назад", "megaphone", callback_data="admin_workers")],
    ])


def admin_users_keyboard(users: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for u in users[:30]:
        uid = u["user_id"]
        uname = u.get("username") or str(uid)
        bots_count = len(u.get("bots", []))
        plan = u.get("plan") or "—"
        rows.append([_btn(
            f"@{uname} | {plan} | {bots_count} бот(ов)",
            "profile",
            callback_data=f"admin_user:{uid}",
        )])
    rows.append([_btn("Назад", "settings", callback_data="admin_menu")])
    return InlineKeyboardMarkup(rows)


def admin_bots_keyboard(bots: list[dict], manager) -> InlineKeyboardMarkup:
    rows = []
    for bot in bots[:30]:
        name = bot["name"]
        display = bot.get("display_name", name)
        owner = bot.get("owner_id", "?")
        if bot.get("worker_id"):
            is_running = bot.get("status") == "running"
        else:
            is_running = manager.is_running(name)
        icon = STATUS_ICON["running"] if is_running else STATUS_ICON["stopped"]
        rows.append([_btn(
            f"{icon} {display} (uid:{owner})",
            "bot",
            callback_data=f"bot_info:{name}",
        )])
    rows.append([_btn("Назад", "settings", callback_data="admin_menu")])
    return InlineKeyboardMarkup(rows)


def admin_resources_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_btn("Обновить", "loading",  callback_data="admin_resources")],
        [_btn("Назад",    "settings", callback_data="admin_menu")],
    ])
