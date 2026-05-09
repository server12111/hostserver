from telegram import Update
from telegram.ext import ContextTypes

from keyboards import main_menu_keyboard

WELCOME_TEXT = (
    "👋 Вітаю! Це <b>Bot Manager</b> — панель керування ботами.\n\n"
    "Оберіть дію:"
)


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            WELCOME_TEXT,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
