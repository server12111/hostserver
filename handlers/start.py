from telegram import Update
from telegram.ext import ContextTypes

from keyboards import main_menu_keyboard


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_registry = context.bot_data.get("user_registry")
    if user_registry and user:
        if not user_registry.exists(user.id):
            user_registry.register(user.id, user.username or "")

    text = (
        "👋 Добро пожаловать в <b>Bot Hosting</b>!\n\n"
        "Здесь вы можете размещать своих Python-ботов "
        "и управлять ими прямо из Telegram.\n\n"
        "Выберите действие:"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=main_menu_keyboard()
        )
