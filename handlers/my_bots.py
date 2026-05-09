from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from keyboards import bot_list_keyboard, bot_detail_keyboard, STATUS_ICON


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
            "У вас ещё нет ботов.\n\nНажмите <b>➕ Добавить бота</b> в главном меню.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
            ]),
        )
        return

    await query.edit_message_text(
        "🤖 <b>Ваши боты:</b>",
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
        await query.edit_message_text("❌ Бот не найден.")
        return

    if not _is_admin(user_id, context) and bot.get("owner_id") != user_id:
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return

    is_running = manager.is_running(bot_name)
    status = "🟢 Запущен" if is_running else "🔴 Остановлен"
    source = "🔗 Git" if bot.get("source") == "git" else "📦 ZIP"
    text = (
        f"🤖 <b>{bot.get('display_name', bot_name)}</b>\n\n"
        f"Статус: {status}\n"
        f"Источник: {source}\n"
        f"Точка входа: <code>{bot['entry_point']}</code>\n"
        f"Добавлен: {bot.get('added_at', '—')}"
    )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )
