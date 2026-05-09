from telegram import Update
from telegram.ext import ContextTypes

from keyboards import main_menu_keyboard

_SEP = "━━━━━━━━━━━━━━━"


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_registry = context.bot_data.get("user_registry")
    if user_registry and user:
        if not user_registry.exists(user.id):
            user_registry.register(user.id, user.username or "")

    text = (
        f"🚀 <b>Bot Hosting</b>\n"
        f"{_SEP}\n"
        f"Запускайте Python-ботов 24/7\n"
        f"без сервера и технических знаний.\n"
        f"{_SEP}\n"
        f"▸ Купите хостинг — получите слот\n"
        f"▸ Загрузите ZIP или Git репозиторий\n"
        f"▸ Бот работает круглосуточно"
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
