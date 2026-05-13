import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from payments import PLANS, CURRENCIES

# ─── Иконки ───────────────────────────────────────────────────────────────────
STATUS_ICON = {"running": "🟢", "stopped": "🔴"}


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
            InlineKeyboardButton("🤖 Мои боты", callback_data="my_bots"),
            InlineKeyboardButton("➕ Добавить бота", callback_data="add_bot"),
        ],
        [InlineKeyboardButton("🖥 Мой хостинг", callback_data="balance")],
    ])


# ─── Список ботов ─────────────────────────────────────────────────────────────
def bot_list_keyboard(bots: list[dict], manager) -> InlineKeyboardMarkup:
    rows = []
    for bot in bots:
        name = bot["name"]
        display = bot.get("display_name", name)
        icon = STATUS_ICON["running"] if manager.is_running(name) else STATUS_ICON["stopped"]
        rows.append([InlineKeyboardButton(f"{icon} {display}", callback_data=f"bot_info:{name}")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


# ─── Детали бота ──────────────────────────────────────────────────────────────
def bot_detail_keyboard(bot_name: str, is_running: bool) -> InlineKeyboardMarkup:
    action = (
        InlineKeyboardButton("⏹ Остановить", callback_data=f"stop_bot:{bot_name}")
        if is_running else
        InlineKeyboardButton("▶️ Запустить", callback_data=f"start_bot:{bot_name}")
    )
    return InlineKeyboardMarkup([
        [action],
        [
            InlineKeyboardButton("📋 Логи", callback_data=f"logs:{bot_name}"),
            InlineKeyboardButton("📝 Конфиг", callback_data=f"config:{bot_name}"),
        ],
        [
            InlineKeyboardButton("⚙️ Пакеты", callback_data=f"packages:{bot_name}"),
            InlineKeyboardButton("📁 Файлы", callback_data=f"files:{bot_name}"),
        ],
        [InlineKeyboardButton("🔄 Оновити код", callback_data=f"update_bot:{bot_name}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{bot_name}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="my_bots")],
    ])


def update_source_keyboard(bot_name: str, has_git: bool) -> InlineKeyboardMarkup:
    rows = []
    if has_git:
        rows.append([InlineKeyboardButton("🔗 Оновити з Git", callback_data=f"update_git:{bot_name}")])
    rows.append([InlineKeyboardButton("📦 Завантажити новий ZIP", callback_data=f"update_zip:{bot_name}")])
    rows.append([InlineKeyboardButton("❌ Скасувати", callback_data=f"bot_info:{bot_name}")])
    return InlineKeyboardMarkup(rows)


# ─── Подтверждение удаления ───────────────────────────────────────────────────
def delete_confirm_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del:{bot_name}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"bot_info:{bot_name}"),
        ]
    ])


# ─── Логи ─────────────────────────────────────────────────────────────────────
def logs_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Обновить", callback_data=f"logs:{bot_name}"),
            InlineKeyboardButton("🔙 Назад", callback_data=f"bot_info:{bot_name}"),
        ]
    ])


# ─── Конфиг ───────────────────────────────────────────────────────────────────
def config_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_config:{bot_name}")],
        [InlineKeyboardButton("🔙 Назад", callback_data=f"bot_info:{bot_name}")],
    ])


def config_edit_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data=f"config:{bot_name}")]
    ])


# ─── Пакеты ───────────────────────────────────────────────────────────────────
def packages_keyboard(bot_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data=f"bot_info:{bot_name}")]
    ])


# ─── Файлы ────────────────────────────────────────────────────────────────────
def files_keyboard(bot_name: str, files: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, fname in enumerate(files[:20]):
        rows.append([InlineKeyboardButton(
            f"📄 {fname}", callback_data=f"dl_file:{bot_name}:{i}"
        )])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data=f"bot_info:{bot_name}")])
    return InlineKeyboardMarkup(rows)


# ─── Источник бота ────────────────────────────────────────────────────────────
def add_source_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 ZIP-архив", callback_data="add_zip"),
            InlineKeyboardButton("🔗 Git репозиторий", callback_data="add_git"),
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")],
    ])


# ─── Хостинг ──────────────────────────────────────────────────────────────────
def balance_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖥 Купить хостинг-слот", callback_data="plans")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")],
    ])


def plans_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, plan in PLANS.items():
        label = f"💾 {plan['ram']} RAM — {plan['price']} USDT/мес"
        rows.append([InlineKeyboardButton(label, callback_data=f"buy_plan:{key}")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="balance")])
    return InlineKeyboardMarkup(rows)


def currency_keyboard(plan_key: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(c, callback_data=f"pay_currency:{plan_key}:{c}")]
            for c in CURRENCIES]
    rows.append([InlineKeyboardButton("💎 Оплатить TON", callback_data=f"pay_ton:{plan_key}")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="plans")])
    return InlineKeyboardMarkup(rows)


def payment_keyboard(pay_url: str, plan_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton("🔙 Назад", callback_data="plans")],
    ])


def ton_payment_keyboard(plan_key: str, wallet: str = "", amount_ton: float = 0, comment: str = "") -> InlineKeyboardMarkup:
    rows = []
    if wallet and amount_ton:
        amount_nano = int(amount_ton * 1_000_000_000)
        tonkeeper_url = f"https://app.tonkeeper.com/transfer/{wallet}?amount={amount_nano}&text={comment}"
        rows.append([InlineKeyboardButton("💎 Открыть TonKeeper", url=tonkeeper_url)])
    rows.append([InlineKeyboardButton("✅ Я оплатил", callback_data=f"ton_check:{plan_key}")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data=f"buy_plan:{plan_key}")])
    return InlineKeyboardMarkup(rows)


# ─── Админ-панель ─────────────────────────────────────────────────────────────
def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
            InlineKeyboardButton("🤖 Все боты", callback_data="admin_bots"),
        ],
        [
            InlineKeyboardButton("📊 Ресурсы", callback_data="admin_resources"),
            InlineKeyboardButton("🖥 Воркеры", callback_data="admin_workers"),
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")],
    ])


def workers_keyboard(workers: list[dict], statuses: dict) -> InlineKeyboardMarkup:
    rows = []
    for w in workers:
        icon = "🟢" if statuses.get(w["id"]) else "🔴"
        rows.append([InlineKeyboardButton(
            f"{icon} {w['label']} ({w['url']})",
            callback_data=f"admin_worker:{w['id']}",
        )])
    rows.append([InlineKeyboardButton("➕ Добавить воркер", callback_data="admin_add_worker")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(rows)


def worker_detail_keyboard(worker_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Ресурсы", callback_data=f"admin_worker_res:{worker_id}"),
            InlineKeyboardButton("❌ Удалить", callback_data=f"admin_worker_del:{worker_id}"),
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_workers")],
    ])


def admin_users_keyboard(users: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for u in users[:30]:
        uid = u["user_id"]
        uname = u.get("username") or str(uid)
        bots_count = len(u.get("bots", []))
        plan = u.get("plan") or "—"
        rows.append([InlineKeyboardButton(
            f"👤 @{uname} | {plan} | {bots_count} бот(ов)",
            callback_data=f"admin_user:{uid}",
        )])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(rows)


def admin_bots_keyboard(bots: list[dict], manager) -> InlineKeyboardMarkup:
    rows = []
    for bot in bots[:30]:
        name = bot["name"]
        display = bot.get("display_name", name)
        owner = bot.get("owner_id", "?")
        icon = STATUS_ICON["running"] if manager.is_running(name) else STATUS_ICON["stopped"]
        rows.append([InlineKeyboardButton(
            f"{icon} {display} (uid:{owner})",
            callback_data=f"bot_info:{name}",
        )])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")])
    return InlineKeyboardMarkup(rows)


def admin_resources_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_resources")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")],
    ])
