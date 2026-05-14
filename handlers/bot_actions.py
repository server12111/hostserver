import html
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from keyboards import (
    bot_detail_keyboard, delete_confirm_keyboard, logs_keyboard,
    packages_keyboard, config_keyboard, config_edit_keyboard,
    update_source_keyboard, pe,
)
import worker_client as wc

WAITING_UPDATE_ZIP = 40


def _get_worker(bot: dict, context) -> dict | None:
    wid = bot.get("worker_id")
    if not wid:
        return None
    wr = context.bot_data.get("worker_registry")
    return wr.get_worker(wid) if wr else None

WAITING_PACKAGES = 10
WAITING_CONFIG = 20


def _is_running(bot: dict, manager) -> bool:
    if bot.get("worker_id"):
        return bot.get("status") == "running"
    return manager.is_running(bot["name"])


def _is_admin(user_id: int, context) -> bool:
    return user_id in context.bot_data.get("admin_ids", set())


def _has_access(user_id: int, bot: dict, context) -> bool:
    return _is_admin(user_id, context) or bot.get("owner_id") == user_id


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _bot_status_text(bot: dict, bot_name: str, is_running: bool) -> str:
    status_icon = "🟢" if is_running else "🔴"
    status_text = "Запущен" if is_running else "Остановлен"
    return (
        f"{pe('bot', '🤖')} <b>{bot.get('display_name', bot_name)}</b>\n\n"
        f"Статус: {status_icon} <b>{status_text}</b>"
    )


# ─── Запуск ───────────────────────────────────────────────────────────────────
async def start_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    worker = _get_worker(bot, context)
    if worker:
        ok, msg = await wc.start(worker, bot_name)
        if ok:
            registry.update_bot(bot_name, status="running")
    else:
        ok, msg = manager.start_bot(bot_name)
        if ok:
            manager.schedule_watch(bot_name)
    bot = registry.get_bot(bot_name)
    is_running = _is_running(bot, manager)
    result_icon = pe('check', '✅') if ok else pe('cross', '❌')
    await query.edit_message_text(
        f"{_bot_status_text(bot, bot_name, is_running)}\n\n"
        f"{result_icon} {_esc(msg)}",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )


# ─── Остановка ────────────────────────────────────────────────────────────────
async def stop_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    worker = _get_worker(bot, context)
    if worker:
        ok, msg = await wc.stop(worker, bot_name)
        if ok:
            registry.update_bot(bot_name, status="stopped")
    else:
        ok, msg = manager.stop_bot(bot_name)
    bot = registry.get_bot(bot_name)
    is_running = _is_running(bot, manager)
    result_icon = pe('check', '✅') if ok else pe('cross', '❌')
    await query.edit_message_text(
        f"{_bot_status_text(bot, bot_name, is_running)}\n\n"
        f"{result_icon} {_esc(msg)}",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )


# ─── Удаление ─────────────────────────────────────────────────────────────────
async def delete_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    await query.edit_message_text(
        f"{pe('trash', '🗑')} <b>Удалить бота?</b>\n\n"
        f"<b>{bot.get('display_name', bot_name)}</b>\n\n"
        f"Все файлы будут удалены безвозвратно.",
        parse_mode="HTML",
        reply_markup=delete_confirm_keyboard(bot_name),
    )


async def confirm_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    user_registry = context.bot_data["user_registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    owner_id = bot.get("owner_id", user_id)
    worker = _get_worker(bot, context)
    if worker:
        ok, msg = await wc.delete(worker, bot_name)
        registry.remove_bot(bot_name)
    else:
        ok, msg = manager.delete_bot(bot_name)
    user_registry.remove_bot_from_user(owner_id, bot_name)
    bots = registry.list_bots_by_owner(user_id) if not _is_admin(user_id, context) else registry.list_bots()
    result_icon = pe('check', '✅') if ok else pe('cross', '❌')
    if bots:
        from keyboards import bot_list_keyboard
        await query.edit_message_text(
            f"{result_icon} {msg}\n\n{pe('bot', '🤖')} <b>Мои боты</b>",
            parse_mode="HTML",
            reply_markup=bot_list_keyboard(bots, manager),
        )
    else:
        await query.edit_message_text(
            f"{result_icon} {msg}\n\nУ вас нет ботов.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]
            ]),
        )


# ─── Логи ─────────────────────────────────────────────────────────────────────
async def logs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    worker = _get_worker(bot, context)
    if worker:
        logs = await wc.logs(worker, bot_name, n=30)
    else:
        logs = manager.get_logs(bot_name, n=30)
    logs_trimmed = logs[-3800:] if len(logs) > 3800 else logs
    await query.edit_message_text(
        f"{pe('eye', '👁')} <b>Логи: {bot.get('display_name', bot_name)}</b>\n\n"
        f"<code>{_esc(logs_trimmed)}</code>",
        parse_mode="HTML",
        reply_markup=logs_keyboard(bot_name),
    )


# ─── Конфиг: просмотр ─────────────────────────────────────────────────────────
async def config_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    worker = _get_worker(bot, context)
    if worker:
        content = await wc.get_config(worker, bot_name)
    else:
        env_file = os.path.join(bot["path"], ".env")
        content = ""
        if os.path.exists(env_file):
            with open(env_file, encoding="utf-8") as f:
                content = f.read().strip()
    display = f"<code>{_esc(content)}</code>" if content else "<i>(пусто)</i>"
    await query.edit_message_text(
        f"{pe('pencil', '⚙️')} <b>Конфиг: {bot.get('display_name', bot_name)}</b>\n\n{display}",
        parse_mode="HTML",
        reply_markup=config_keyboard(bot_name),
    )


# ─── Конфиг: вход в редактирование ───────────────────────────────────────────
async def config_edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return ConversationHandler_END()
    context.user_data["config_for"] = bot_name
    await query.edit_message_text(
        f"{pe('pencil', '✏️')} <b>Редактирование конфига</b>\n"
        f"<b>{bot.get('display_name', bot_name)}</b>\n\n"
        "Отправьте переменные в формате <code>КЛЮЧ=ЗНАЧЕНИЕ</code>,\n"
        "каждая переменная с новой строки:\n\n"
        "<code>BOT_TOKEN=1234567890:ABC...\nADMIN_ID=123456</code>",
        parse_mode="HTML",
        reply_markup=config_edit_keyboard(bot_name),
    )
    return WAITING_CONFIG


def ConversationHandler_END():
    from telegram.ext import ConversationHandler
    return ConversationHandler.END


# ─── Конфиг: сохранение ───────────────────────────────────────────────────────
async def config_save_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram.ext import ConversationHandler
    bot_name = context.user_data.get("config_for")
    if not bot_name:
        await update.message.reply_text("❌ Ошибка сессии. Попробуйте снова.")
        return ConversationHandler.END
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot:
        await update.message.reply_text("❌ Бот не найден.")
        return ConversationHandler.END
    new_content = update.message.text.strip()
    worker = _get_worker(bot, context)
    if worker:
        await wc.save_config(worker, bot_name, new_content)
    else:
        with open(os.path.join(bot["path"], ".env"), "w", encoding="utf-8") as f:
            f.write(new_content + "\n")
    await update.message.reply_text(
        f"{pe('check', '✅')} <b>Конфиг сохранён!</b>\n\n"
        f"<b>{bot.get('display_name', bot_name)}</b>\n\n"
        f"Перезапустите бота, чтобы изменения вступили в силу.",
        parse_mode="HTML",
        reply_markup=config_keyboard(bot_name),
    )
    return ConversationHandler.END


async def cancel_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram.ext import ConversationHandler
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    env_file = os.path.join(bot["path"], ".env") if bot else ""
    content = ""
    if bot and os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            content = f.read().strip()
    display = f"<code>{_esc(content)}</code>" if content else "<i>(пусто)</i>"
    await query.edit_message_text(
        f"{pe('pencil', '⚙️')} <b>Конфиг: {bot.get('display_name', bot_name) if bot else bot_name}</b>\n\n{display}",
        parse_mode="HTML",
        reply_markup=config_keyboard(bot_name),
    )
    return ConversationHandler.END


# ─── Пакеты ───────────────────────────────────────────────────────────────────
async def packages_entry_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    context.user_data["installing_for"] = bot_name
    await query.edit_message_text(
        f"{pe('package', '📦')} <b>Установка пакетов</b>\n"
        f"<b>{bot.get('display_name', bot_name)}</b>\n\n"
        "Напишите названия пакетов через пробел:\n"
        "<code>pyTelegramBotAPI requests aiohttp</code>",
        parse_mode="HTML",
        reply_markup=packages_keyboard(bot_name),
    )
    return WAITING_PACKAGES


async def packages_install_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram.ext import ConversationHandler
    bot_name = context.user_data.get("installing_for")
    if not bot_name:
        await update.message.reply_text("❌ Ошибка сессии.")
        return ConversationHandler.END
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot:
        await update.message.reply_text("❌ Бот не найден.")
        return ConversationHandler.END
    packages = update.message.text.split()
    if not packages:
        await update.message.reply_text("❌ Введите хотя бы один пакет.")
        return WAITING_PACKAGES
    status_msg = await update.message.reply_text(
        f"{pe('loading', '⏳')} Устанавливаю: <code>{' '.join(packages)}</code>...",
        parse_mode="HTML",
    )
    worker = _get_worker(bot, context)
    if worker:
        ok, msg = await wc.install(worker, bot_name, packages)
    else:
        ok, msg = await manager.install_packages(bot["path"], packages)
    result_icon = pe('check', '✅') if ok else pe('cross', '❌')
    await status_msg.edit_text(
        f"{result_icon} {_esc(msg)}",
        parse_mode="HTML",
        reply_markup=packages_keyboard(bot_name),
    )
    return ConversationHandler.END


async def cancel_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram.ext import ConversationHandler
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot:
        await query.edit_message_text("❌ Бот не найден.")
        return ConversationHandler.END
    is_running = _is_running(bot, manager)
    await query.edit_message_text(
        _bot_status_text(bot, bot_name, is_running),
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )
    return ConversationHandler.END


# ─── Перезапуск ───────────────────────────────────────────────────────────────
async def restart_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    await query.edit_message_text(
        f"{pe('loading', '🔄')} Перезапускаю <b>{bot.get('display_name', bot_name)}</b>...",
        parse_mode="HTML",
    )
    worker = _get_worker(bot, context)
    if worker:
        await wc.stop(worker, bot_name)
        ok, msg = await wc.start(worker, bot_name)
        if ok:
            registry.update_bot(bot_name, status="running")
    else:
        manager.stop_bot(bot_name)
        ok, msg = manager.start_bot(bot_name)
        if ok:
            manager.schedule_watch(bot_name)
    bot = registry.get_bot(bot_name)
    is_running = _is_running(bot, manager)
    result_line = f"\n\n{pe('check', '✅')} Перезапущен" if ok else f"\n\n{pe('cross', '❌')} {_esc(msg)}"
    await query.edit_message_text(
        f"{_bot_status_text(bot, bot_name, is_running)}{result_line}",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )


# ─── Оновлення коду ───────────────────────────────────────────────────────────
async def update_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(query.from_user.id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    has_git = bool(bot.get("git_url"))
    await query.edit_message_text(
        f"{pe('upload', '⬆️')} <b>Обновить код</b>\n"
        f"<b>{bot.get('display_name', bot_name)}</b>\n\n"
        "Выберите способ обновления:",
        parse_mode="HTML",
        reply_markup=update_source_keyboard(bot_name, has_git),
    )


async def update_git_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(query.from_user.id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    git_url = bot.get("git_url", "")
    if not git_url:
        await query.answer("❌ Git URL не найден.", show_alert=True)
        return
    worker = _get_worker(bot, context)
    if not worker:
        await query.edit_message_text(
            "❌ Воркер недоступен.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f"bot_info:{bot_name}")]]),
        )
        return
    await query.edit_message_text(
        f"{pe('loading', '🔄')} Обновляю код <b>{bot.get('display_name', bot_name)}</b> из Git...",
        parse_mode="HTML",
    )
    await wc.stop(worker, bot_name)
    ok, result = await wc.deploy_git(worker, bot_name, git_url, bot.get("display_name", bot_name), bot.get("owner_id", 0))
    if not ok:
        await query.edit_message_text(
            f"{pe('cross', '❌')} <b>Ошибка обновления:</b>\n<code>{html.escape(result)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f"bot_info:{bot_name}")]]),
        )
        return
    bot = registry.get_bot(bot_name)
    is_running = _is_running(bot, manager)
    await query.edit_message_text(
        f"{pe('check', '✅')} <b>{bot.get('display_name', bot_name)}</b> обновлён!\n\n"
        f"Запустите бота, чтобы применить изменения.",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )


async def update_zip_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(query.from_user.id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return ConversationHandler.END
    context.user_data["update_for"] = bot_name
    await query.edit_message_text(
        f"{pe('package', '📦')} <b>Обновить {bot.get('display_name', bot_name)}</b>\n\n"
        "Отправьте новый <b>ZIP-архив</b> с кодом бота:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✖️ Отмена", callback_data=f"bot_info:{bot_name}")]]),
    )
    return WAITING_UPDATE_ZIP


async def receive_update_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_name = context.user_data.get("update_for")
    if not bot_name:
        return ConversationHandler.END
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot:
        await update.message.reply_text("❌ Бот не найден.")
        return ConversationHandler.END
    doc = update.message.document
    if not doc or not doc.file_name.endswith(".zip"):
        await update.message.reply_text("❌ Отправьте файл в формате .zip")
        return WAITING_UPDATE_ZIP
    worker = _get_worker(bot, context)
    if not worker:
        await update.message.reply_text("❌ Воркер недоступен.")
        return ConversationHandler.END
    status_msg = await update.message.reply_text(
        f"{pe('loading', '⏳')} Загружаю и обновляю код...",
        parse_mode="HTML",
    )
    tg_file = await doc.get_file()
    zip_bytes = bytes(await tg_file.download_as_bytearray())
    await wc.stop(worker, bot_name)
    ok, result = await wc.deploy_zip(worker, bot_name, zip_bytes, bot.get("display_name", bot_name), bot.get("owner_id", 0))
    if not ok:
        await status_msg.edit_text(
            f"{pe('cross', '❌')} <b>Ошибка обновления:</b>\n<code>{html.escape(result)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f"bot_info:{bot_name}")]]),
        )
        return ConversationHandler.END
    bot = registry.get_bot(bot_name)
    is_running = _is_running(bot, manager)
    await status_msg.edit_text(
        f"{pe('check', '✅')} <b>{bot.get('display_name', bot_name)}</b> обновлён!\n\n"
        f"Запустите бота, чтобы применить изменения.",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )
    return ConversationHandler.END
