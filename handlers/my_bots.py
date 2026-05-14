from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from keyboards import bot_list_keyboard, bot_detail_keyboard, STATUS_ICON, pe


def _is_admin(user_id: int, context) -> bool:
    return user_id in context.bot_data.get("admin_ids", set())


async def my_bots_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]

    if _is_admin(user_id, context):
        bots = registry.list_bots()
    else:
        bots = registry.list_bots_by_owner(user_id)

    if not bots:
        await query.edit_message_text(
            f"{pe('bot', '🤖')} <b>Ботов пока нет</b>\n\n"
            f"Нажмите <b>⬆️ Добавить бота</b> в главном меню,\n"
            f"чтобы запустить своего первого бота.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu")]
            ]),
        )
        return

    await query.edit_message_text(
        f"{pe('bot', '🤖')} <b>Мои боты</b>",
        parse_mode="HTML",
        reply_markup=bot_list_keyboard(bots, manager),
    )


async def bot_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]

    bot = registry.get_bot(bot_name)
    if not bot:
        await query.edit_message_text(
            f"{pe('cross', '❌')} Бот не найден.", parse_mode="HTML"
        )
        return

    if not _is_admin(user_id, context) and bot.get("owner_id") != user_id:
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return

    if bot.get("worker_id"):
        is_running = bot.get("status") == "running"
    else:
        is_running = manager.is_running(bot_name)

    status_icon = "🟢" if is_running else "🔴"
    status_text = "Запущен" if is_running else "Остановлен"
    source_text = f"🔗 Git" if bot.get("source") == "git" else f"{pe('package', '📦')} ZIP"
    worker_line = ""
    if bot.get("worker_id"):
        worker_line = f"\n{pe('stats', '🖥')} Воркер: <code>{bot['worker_id']}</code>"

    text = (
        f"{pe('bot', '🤖')} <b>{bot.get('display_name', bot_name)}</b>\n\n"
        f"Статус: {status_icon} <b>{status_text}</b>\n"
        f"Источник: {source_text}\n"
        f"Точка входа: <code>{bot['entry_point']}</code>"
        f"{worker_line}\n"
        f"Добавлен: {bot.get('added_at', '—')}"
    )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )
