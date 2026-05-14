from telegram import Update
from telegram.ext import ContextTypes

from keyboards import main_menu_keyboard, pe

_SEP = "━━━━━━━━━━━━━━━"


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_registry = context.bot_data.get("user_registry")
    if user_registry and user:
        if not user_registry.exists(user.id):
            user_registry.register(user.id, user.username or "")

    text = (
        f"{pe('bot', '🤖')} <b>Bot Hosting</b>\n"
        f"{_SEP}\n"
        f"Запускайте Python-ботов <b>24/7</b> без сервера\n"
        f"и технических знаний.\n"
        f"{_SEP}\n"
        f"{pe('upload', '⬆️')} Загрузите ZIP или Git репозиторий\n"
        f"{pe('lock', '🔒')} Изолированное окружение для каждого бота\n"
        f"{pe('money', '💰')} Оплата криптовалютой\n"
        f"{pe('loading', '🔄')} Автоматический перезапуск при сбоях"
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
