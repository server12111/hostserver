import io
import json
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from keyboards import (
    admin_menu_keyboard, admin_users_keyboard,
    admin_bots_keyboard, admin_resources_keyboard,
    workers_keyboard, worker_detail_keyboard, pe,
)
import worker_client as wc

WAITING_WORKER_URL = 30
WAITING_WORKER_SECRET = 31
WAITING_DB_FILE = 32


def _is_admin(user_id: int, context) -> bool:
    return user_id in context.bot_data.get("admin_ids", set())


async def admin_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_admin(user_id, context):
        if update.message:
            await update.message.reply_text("⛔ Нет доступа.")
        return
    text = f"{pe('settings', '🛠')} <b>Панель администратора</b>"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=admin_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=admin_menu_keyboard()
        )


async def admin_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    user_registry = context.bot_data["user_registry"]
    users = user_registry.list_users()
    if not users:
        await query.edit_message_text(
            f"{pe('users', '👥')} Пользователей пока нет.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")]
            ]),
        )
        return
    await query.edit_message_text(
        f"{pe('users', '👥')} <b>Пользователи ({len(users)}):</b>",
        parse_mode="HTML",
        reply_markup=admin_users_keyboard(users),
    )


async def admin_bots_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bots = registry.list_bots()
    if not bots:
        await query.edit_message_text(
            f"{pe('bot', '🤖')} Ботов пока нет.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")]
            ]),
        )
        return
    running = sum(1 for b in bots if manager.is_running(b["name"]))
    await query.edit_message_text(
        f"{pe('bot', '🤖')} <b>Все боты ({len(bots)}, запущено: {running}):</b>",
        parse_mode="HTML",
        reply_markup=admin_bots_keyboard(bots, manager),
    )


async def admin_resources_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    manager = context.bot_data["manager"]
    resources = manager.get_all_resources()
    if not resources:
        await query.edit_message_text(
            f"{pe('stats', '📊')} <b>Ресурсы</b>\n\n<i>Нет запущенных ботов.</i>",
            parse_mode="HTML",
            reply_markup=admin_resources_keyboard(),
        )
        return
    lines = [f"{pe('stats', '📊')} <b>Ресурсы запущенных ботов:</b>\n"]
    for r in resources:
        lines.append(
            f"• <b>{r['display']}</b>\n"
            f"  CPU: {r['cpu']}% | RAM: {r['ram_mb']} MB"
        )
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=admin_resources_keyboard(),
    )


async def admin_workers_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    wr = context.bot_data.get("worker_registry")
    workers = wr.list_workers() if wr else []
    statuses = {}
    for w in workers:
        h = await wc.health(w)
        statuses[w["id"]] = h.get("ok", False)
    online_count = sum(1 for v in statuses.values() if v)
    await query.edit_message_text(
        f"{pe('megaphone', '🖥')} <b>Воркеры ({len(workers)}, онлайн: {online_count})</b>\n\n"
        + (f"Добавьте воркеры для распределения ботов по серверам." if not workers else ""),
        parse_mode="HTML",
        reply_markup=workers_keyboard(workers, statuses),
    )


async def admin_worker_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        return
    worker_id = query.data.split(":", 1)[1]
    wr = context.bot_data.get("worker_registry")
    w = wr.get_worker(worker_id) if wr else None
    if not w:
        await query.answer("Воркер не найден.", show_alert=True)
        return
    h = await wc.health(w)
    status_icon = "🟢" if h.get("ok") else "🔴"
    status_text = "Онлайн" if h.get("ok") else "Недоступен"
    registry = context.bot_data["registry"]
    bots_count = len(registry.list_bots_by_worker(worker_id))
    await query.edit_message_text(
        f"{pe('megaphone', '🖥')} <b>{w['label']}</b>\n\n"
        f"URL: <code>{w['url']}</code>\n"
        f"Статус: {status_icon} <b>{status_text}</b>\n"
        f"Ботов: <b>{bots_count}</b>\n"
        f"Запущено: <b>{h.get('running', '—')}</b>\n"
        f"RAM свободно: <b>{h.get('ram_free_mb', '—')} МБ</b>",
        parse_mode="HTML",
        reply_markup=worker_detail_keyboard(worker_id),
    )


async def admin_worker_resources_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        return
    worker_id = query.data.split(":", 1)[1]
    wr = context.bot_data.get("worker_registry")
    w = wr.get_worker(worker_id) if wr else None
    if not w:
        await query.answer("Воркер не найден.", show_alert=True)
        return
    res = await wc.resources(w)
    if not res:
        text = f"{pe('stats', '📊')} <b>{w['label']}</b>\n\n<i>Нет запущенных ботов.</i>"
    else:
        lines = [f"{pe('stats', '📊')} <b>{w['label']} — ресурсы:</b>\n"]
        for r in res:
            lines.append(f"• <b>{r['display']}</b>\n  CPU: {r['cpu']}% | RAM: {r['ram_mb']} МБ")
        text = "\n".join(lines)
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data=f"admin_worker_res:{worker_id}")],
            [InlineKeyboardButton("◀️ Назад", callback_data=f"admin_worker:{worker_id}")],
        ]),
    )


async def admin_worker_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        return
    worker_id = query.data.split(":", 1)[1]
    wr = context.bot_data.get("worker_registry")
    if wr:
        wr.remove_worker(worker_id)
    await query.edit_message_text(
        f"{pe('check', '✅')} Воркер <b>{worker_id}</b> удалён.\n\n"
        f"Боты на этом воркере сохранены в реестре, но недоступны.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🖥 Воркеры", callback_data="admin_workers")]
        ]),
    )


async def admin_add_worker_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        return
    await query.edit_message_text(
        f"{pe('megaphone', '🖥')} <b>Добавить воркер</b>\n\n"
        "Отправьте URL воркера:\n"
        "<code>http://1.2.3.4:8000</code>\n\n"
        "<i>Для bothost.ru используйте URL из Cloudflare Quick Tunnel\n"
        "(смотрите /start на воркере)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✖️ Отмена", callback_data="admin_workers")]
        ]),
    )
    return WAITING_WORKER_URL


async def admin_receive_worker_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("❌ Неверный URL. Пример: http://1.2.3.4:8000")
        return WAITING_WORKER_URL
    context.user_data["new_worker_url"] = url
    await update.message.reply_text(
        f"{pe('check', '✅')} URL: <code>{url}</code>\n\n"
        f"Теперь отправьте <b>секретный ключ</b> воркера\n"
        "(значение WORKER_SECRET на том сервере):",
        parse_mode="HTML",
    )
    return WAITING_WORKER_SECRET


async def admin_receive_worker_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secret = update.message.text.strip()
    url = context.user_data.pop("new_worker_url", "")
    if not url:
        await update.message.reply_text("❌ Ошибка сессии. Начните заново.")
        return ConversationHandler.END

    test_worker = {"url": url, "secret": secret}
    await update.message.reply_text(
        f"{pe('loading', '⏳')} Проверяю подключение...",
        parse_mode="HTML",
    )
    h = await wc.health(test_worker)
    if not h.get("ok"):
        error_detail = h.get("error", "неизвестная ошибка")
        await update.message.reply_text(
            f"{pe('cross', '❌')} <b>Воркер недоступен</b>\n\n"
            f"Ошибка: <code>{error_detail}</code>\n\n"
            "Проверьте:\n"
            "• URL доступен из интернета\n"
            "• WORKER_SECRET совпадает\n"
            "• worker_api.py запущен",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥 Воркеры", callback_data="admin_workers")]
            ]),
        )
        return ConversationHandler.END

    wr = context.bot_data.get("worker_registry")
    worker_id = wr.next_id()
    label = f"Worker #{worker_id[1:]}"
    wr.add_worker(worker_id, url, secret, label)
    await update.message.reply_text(
        f"{pe('celebrate', '🎉')} <b>Воркер добавлен!</b>\n\n"
        f"ID: <code>{worker_id}</code>\n"
        f"URL: <code>{url}</code>\n"
        f"Ботов сейчас: <b>{h.get('bots', 0)}</b>\n"
        f"RAM свободно: <b>{h.get('ram_free_mb', '—')} МБ</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🖥 Воркеры", callback_data="admin_workers")]
        ]),
    )
    return ConversationHandler.END


async def admin_cancel_worker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await admin_workers_handler(update, context)
    return ConversationHandler.END


# ─── База данных: скачать ─────────────────────────────────────────────────────
async def admin_download_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        return
    await query.edit_message_text(
        f"{pe('download', '📥')} Отправляю файлы базы данных...",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")]
        ]),
    )
    for fname in ("bots_registry.json", "users_registry.json"):
        if os.path.exists(fname):
            with open(fname, "rb") as f:
                data = f.read()
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=io.BytesIO(data),
                filename=fname,
                caption=f"📄 {fname}",
            )


# ─── База данных: загрузить ───────────────────────────────────────────────────
async def admin_upload_db_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        return
    await query.edit_message_text(
        f"{pe('upload', '📤')} <b>Загрузить базу данных</b>\n\n"
        "Отправьте файл <code>bots_registry.json</code> или <code>users_registry.json</code>.\n\n"
        "⚠️ Файл полностью заменит текущую базу данных.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✖️ Отмена", callback_data="admin_menu")]
        ]),
    )
    return WAITING_DB_FILE


async def admin_receive_db_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id, context):
        return ConversationHandler.END
    doc = update.message.document
    allowed = ("bots_registry.json", "users_registry.json")
    if not doc or not doc.file_name.endswith(".json"):
        await update.message.reply_text("❌ Отправьте файл в формате .json")
        return WAITING_DB_FILE
    if doc.file_name not in allowed:
        await update.message.reply_text(
            f"❌ Неверное имя файла.\n"
            f"Допустимые: <code>bots_registry.json</code>, <code>users_registry.json</code>",
            parse_mode="HTML",
        )
        return WAITING_DB_FILE
    tg_file = await doc.get_file()
    data_bytes = bytes(await tg_file.download_as_bytearray())
    try:
        data = json.loads(data_bytes)
    except Exception:
        await update.message.reply_text("❌ Файл повреждён — не удалось разобрать JSON.")
        return WAITING_DB_FILE
    with open(doc.file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if doc.file_name == "bots_registry.json":
        context.bot_data["registry"]._load()
    else:
        context.bot_data["user_registry"]._load()
    await update.message.reply_text(
        f"{pe('check', '✅')} База данных <code>{doc.file_name}</code> успешно загружена и применена.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ В меню", callback_data="admin_menu")]
        ]),
    )
    return ConversationHandler.END


async def admin_cancel_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await admin_command_handler(update, context)
    return ConversationHandler.END


async def admin_user_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    user_id = int(query.data.split(":", 1)[1])
    user_registry = context.bot_data["user_registry"]
    u = user_registry.get_user(user_id)
    if not u:
        await query.answer("Пользователь не найден.", show_alert=True)
        return
    from payments import PLANS
    plan_name = PLANS.get(u.get("plan", ""), {}).get("name", "—") if u.get("plan") else "—"
    sub_status = user_registry.subscription_status(user_id)
    bots = u.get("bots", [])
    text = (
        f"{pe('profile', '👤')} <b>Пользователь @{u.get('username') or user_id}</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Тариф: <b>{plan_name}</b>\n"
        f"Подписка: <b>{sub_status}</b>\n"
        f"Ботов: <b>{len(bots)} / {u.get('max_bots', 0)}</b>\n"
        f"Регистрация: {u.get('registered_at', '—')}"
    )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_users")]
        ]),
    )
