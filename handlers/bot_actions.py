from telegram import Update
from telegram.ext import ContextTypes

import os

from keyboards import (
    bot_detail_keyboard, delete_confirm_keyboard, logs_keyboard,
    packages_keyboard, config_keyboard, config_edit_keyboard,
)


async def start_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    manager = context.bot_data["manager"]
    ok, msg = manager.start_bot(bot_name)
    is_running = manager.is_running(bot_name)
    status = "🟢 Запущений" if is_running else "🔴 Зупинений"
    await query.edit_message_text(
        f"🤖 <b>{bot_name}</b>\n\nСтатус: {status}\n\n{'✅' if ok else '❌'} {msg}",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )


async def stop_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    manager = context.bot_data["manager"]
    ok, msg = manager.stop_bot(bot_name)
    is_running = manager.is_running(bot_name)
    status = "🟢 Запущений" if is_running else "🔴 Зупинений"
    await query.edit_message_text(
        f"🤖 <b>{bot_name}</b>\n\nСтатус: {status}\n\n{'✅' if ok else '❌'} {msg}",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )


async def delete_bot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    await query.edit_message_text(
        f"🗑 Ви впевнені, що хочете видалити бота <b>{bot_name}</b>?\n\n"
        "Всі файли будуть видалені безповоротно.",
        parse_mode="HTML",
        reply_markup=delete_confirm_keyboard(bot_name),
    )


async def confirm_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    manager = context.bot_data["manager"]
    ok, msg = manager.delete_bot(bot_name)
    registry = context.bot_data["registry"]
    bots = registry.list_bots()

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    if bots:
        from keyboards import bot_list_keyboard
        await query.edit_message_text(
            f"{'✅' if ok else '❌'} {msg}\n\n📦 <b>Ваші боти:</b>",
            parse_mode="HTML",
            reply_markup=bot_list_keyboard(bots, manager),
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
        ])
        await query.edit_message_text(
            f"{'✅' if ok else '❌'} {msg}\n\nУ вас ще немає ботів.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )


async def logs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    manager = context.bot_data["manager"]
    logs = manager.get_logs(bot_name, n=30)
    logs_trimmed = logs[-3800:] if len(logs) > 3800 else logs
    text = (
        f"📋 <b>Логи: {bot_name}</b>\n\n"
        f"<code>{_escape_html(logs_trimmed)}</code>"
    )
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=logs_keyboard(bot_name),
    )


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


WAITING_PACKAGES = 10


async def packages_entry_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    context.user_data["installing_for"] = bot_name
    await query.edit_message_text(
        f"⚙️ <b>Пакети для {bot_name}</b>\n\n"
        "Напишіть назви пакетів через пробіл:\n"
        "<code>pyTelegramBotAPI requests aiohttp</code>",
        parse_mode="HTML",
        reply_markup=packages_keyboard(bot_name),
    )
    return WAITING_PACKAGES


async def packages_install_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram.ext import ConversationHandler
    bot_name = context.user_data.get("installing_for")
    if not bot_name:
        await update.message.reply_text("❌ Помилка сесії. Спробуйте знову.")
        return ConversationHandler.END
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot:
        await update.message.reply_text("❌ Бот не знайдений.")
        return ConversationHandler.END
    packages = update.message.text.split()
    if not packages:
        await update.message.reply_text("❌ Введіть хоча б один пакет.")
        return WAITING_PACKAGES
    status_msg = await update.message.reply_text(
        f"⏳ Встановлюю: <code>{' '.join(packages)}</code>...",
        parse_mode="HTML",
    )
    ok, msg = await manager.install_packages(bot["path"], packages)
    icon = "✅" if ok else "❌"
    await status_msg.edit_text(
        f"{icon} {_escape_html(msg)}",
        parse_mode="HTML",
        reply_markup=packages_keyboard(bot_name),
    )
    return ConversationHandler.END


WAITING_CONFIG = 20


async def config_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot:
        await query.edit_message_text("❌ Бот не знайдений.")
        return
    env_file = os.path.join(bot["path"], ".env")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            content = f.read().strip()
    else:
        content = ""
    display = f"<code>{_escape_html(content)}</code>" if content else "<i>(порожньо)</i>"
    await query.edit_message_text(
        f"📝 <b>Конфіг: {bot_name}</b>\n\n{display}",
        parse_mode="HTML",
        reply_markup=config_keyboard(bot_name),
    )


async def config_edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    context.user_data["config_for"] = bot_name
    await query.edit_message_text(
        f"✏️ <b>Редагування конфігу: {bot_name}</b>\n\n"
        "Надішліть конфіг у форматі <code>КЛЮЧ=ЗНАЧЕННЯ</code>, кожна змінна з нового рядка:\n\n"
        "<code>BOT_TOKEN=1234567890:ABC...\nADMIN_ID=123456</code>",
        parse_mode="HTML",
        reply_markup=config_edit_keyboard(bot_name),
    )
    return WAITING_CONFIG


async def config_save_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram.ext import ConversationHandler
    bot_name = context.user_data.get("config_for")
    if not bot_name:
        await update.message.reply_text("❌ Помилка сесії. Спробуйте знову.")
        return ConversationHandler.END
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot:
        await update.message.reply_text("❌ Бот не знайдений.")
        return ConversationHandler.END
    content = update.message.text.strip()
    env_file = os.path.join(bot["path"], ".env")
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(content + "\n")
    await update.message.reply_text(
        f"✅ Конфіг збережено для <b>{bot_name}</b>.\n"
        "Перезапустіть бота щоб зміни набрали чинності.",
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
    if not bot:
        await query.edit_message_text("❌ Бот не знайдений.")
        return ConversationHandler.END
    env_file = os.path.join(bot["path"], ".env")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            content = f.read().strip()
    else:
        content = ""
    display = f"<code>{_escape_html(content)}</code>" if content else "<i>(порожньо)</i>"
    await query.edit_message_text(
        f"📝 <b>Конфіг: {bot_name}</b>\n\n{display}",
        parse_mode="HTML",
        reply_markup=config_keyboard(bot_name),
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
    is_running = manager.is_running(bot_name)
    status_text = "🟢 Запущений" if is_running else "🔴 Зупинений"
    await query.edit_message_text(
        f"🤖 <b>{bot_name}</b>\n\nСтатус: {status_text}\n"
        f"Точка входу: <code>{bot['entry_point']}</code>\n"
        f"Додано: {bot.get('added_at', '—')}",
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )
    return ConversationHandler.END
