import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from keyboards import (
    bot_detail_keyboard, delete_confirm_keyboard, logs_keyboard,
    packages_keyboard, config_keyboard, config_edit_keyboard,
)

WAITING_PACKAGES = 10
WAITING_CONFIG = 20


def _is_admin(user_id: int, context) -> bool:
    return user_id in context.bot_data.get("admin_ids", set())


def _has_access(user_id: int, bot: dict, context) -> bool:
    return _is_admin(user_id, context) or bot.get("owner_id") == user_id


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
    ok, msg = manager.start_bot(bot_name)
    is_running = manager.is_running(bot_name)
    await query.edit_message_text(
        f"🤖 <b>{bot.get('display_name', bot_name)}</b>\n\n"
        f"Статус: {'🟢 Запущен' if is_running else '🔴 Остановлен'}\n\n"
        f"{'✅' if ok else '❌'} {msg}",
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
    ok, msg = manager.stop_bot(bot_name)
    is_running = manager.is_running(bot_name)
    await query.edit_message_text(
        f"🤖 <b>{bot.get('display_name', bot_name)}</b>\n\n"
        f"Статус: {'🟢 Запущен' if is_running else '🔴 Остановлен'}\n\n"
        f"{'✅' if ok else '❌'} {msg}",
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
        f"🗑 Удалить бота <b>{bot.get('display_name', bot_name)}</b>?\n\nВсе файлы будут удалены безвозвратно.",
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
    ok, msg = manager.delete_bot(bot_name)
    user_registry.remove_bot_from_user(owner_id, bot_name)
    bots = registry.list_bots_by_owner(user_id) if not _is_admin(user_id, context) else registry.list_bots()
    if bots:
        from keyboards import bot_list_keyboard
        await query.edit_message_text(
            f"{'✅' if ok else '❌'} {msg}\n\n🤖 <b>Ваши боты:</b>",
            parse_mode="HTML",
            reply_markup=bot_list_keyboard(bots, manager),
        )
    else:
        await query.edit_message_text(
            f"{'✅' if ok else '❌'} {msg}\n\nУ вас нет ботов.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
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
    logs = manager.get_logs(bot_name, n=30)
    logs_trimmed = logs[-3800:] if len(logs) > 3800 else logs
    await query.edit_message_text(
        f"📋 <b>Логи: {bot.get('display_name', bot_name)}</b>\n\n<code>{_esc(logs_trimmed)}</code>",
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
    env_file = os.path.join(bot["path"], ".env")
    content = ""
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            content = f.read().strip()
    display = f"<code>{_esc(content)}</code>" if content else "<i>(пусто)</i>"
    await query.edit_message_text(
        f"📝 <b>Конфиг: {bot.get('display_name', bot_name)}</b>\n\n{display}",
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
        f"✏️ <b>Редактирование конфига: {bot.get('display_name', bot_name)}</b>\n\n"
        "Отправьте конфиг в формате <code>КЛЮЧ=ЗНАЧЕНИЕ</code>, каждая переменная с новой строки:\n\n"
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
    with open(os.path.join(bot["path"], ".env"), "w", encoding="utf-8") as f:
        f.write(update.message.text.strip() + "\n")
    await update.message.reply_text(
        f"✅ Конфиг сохранён для <b>{bot.get('display_name', bot_name)}</b>.\n"
        "Перезапустите бота, чтобы изменения вступили в силу.",
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
        f"📝 <b>Конфиг: {bot.get('display_name', bot_name) if bot else bot_name}</b>\n\n{display}",
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
        f"⚙️ <b>Пакеты для {bot.get('display_name', bot_name)}</b>\n\n"
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
        f"⏳ Устанавливаю: <code>{' '.join(packages)}</code>...", parse_mode="HTML"
    )
    ok, msg = await manager.install_packages(bot["path"], packages)
    await status_msg.edit_text(
        f"{'✅' if ok else '❌'} {_esc(msg)}",
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
    is_running = manager.is_running(bot_name)
    await query.edit_message_text(
        f"🤖 <b>{bot.get('display_name', bot_name)}</b>\n\n"
        f"Статус: {'🟢 Запущен' if is_running else '🔴 Остановлен'}",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )
    return ConversationHandler.END
