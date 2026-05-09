from telegram import Update
from telegram.ext import ContextTypes

from keyboards import bot_list_keyboard, bot_detail_keyboard, STATUS_ICON


async def my_bots_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bots = registry.list_bots()
    if not bots:
        from keyboards import main_menu_keyboard
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
        ])
        await query.edit_message_text(
            "У вас ще немає доданих ботів.\nНатисніть <b>➕ Додати бота</b> в головному меню.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return
    await query.edit_message_text(
        "📦 <b>Ваші боти:</b>",
        parse_mode="HTML",
        reply_markup=bot_list_keyboard(bots, manager),
    )


async def bot_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bot = registry.get_bot(bot_name)
    if not bot:
        await query.edit_message_text("❌ Бот не знайдений.", reply_markup=None)
        return
    is_running = manager.is_running(bot_name)
    status_text = "🟢 Запущений" if is_running else "🔴 Зупинений"
    text = (
        f"🤖 <b>{bot_name}</b>\n\n"
        f"Статус: {status_text}\n"
        f"Точка входу: <code>{bot['entry_point']}</code>\n"
        f"Додано: {bot.get('added_at', '—')}"
    )
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=bot_detail_keyboard(bot_name, is_running),
    )
