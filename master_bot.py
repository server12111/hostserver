import os
import sys
import warnings

warnings.filterwarnings("ignore", message=".*per_message.*")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from bot_manager import BotManager
from registry import RegistryManager
from handlers.start import start_handler
from handlers.my_bots import my_bots_handler, bot_info_handler
from handlers.add_bot import add_bot_entry, receive_zip, non_zip_handler, cancel_add_bot, WAITING_ZIP
from handlers.bot_actions import (
    start_bot_handler,
    stop_bot_handler,
    delete_bot_handler,
    confirm_delete_handler,
    logs_handler,
    packages_entry_handler,
    packages_install_handler,
    cancel_packages,
    WAITING_PACKAGES,
    config_view_handler,
    config_edit_entry,
    config_save_handler,
    cancel_config,
    WAITING_CONFIG,
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не знайдено. Створіть файл .env з BOT_TOKEN=...")

ADMIN_IDS: set[int] = set()
for _part in os.getenv("ADMIN_IDS", "").split(","):
    _part = _part.strip()
    if _part.isdigit():
        ADMIN_IDS.add(int(_part))


async def admin_guard(update: Update, context) -> None:
    user = update.effective_user
    if ADMIN_IDS and (user is None or user.id not in ADMIN_IDS):
        if update.callback_query:
            await update.callback_query.answer("⛔ Доступ заборонено.", show_alert=True)
        elif update.message:
            await update.message.reply_text("⛔ У вас немає доступу до цього бота.")
        raise ApplicationHandlerStop


async def post_init(application: Application) -> None:
    registry = RegistryManager()
    registry.restore_running_bots()
    manager = BotManager(registry)
    application.bot_data["registry"] = registry
    application.bot_data["manager"] = manager


async def post_shutdown(application: Application) -> None:
    manager = application.bot_data.get("manager")
    if manager:
        manager.stop_all()


def build_app() -> Application:
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Admin guard fires before every other handler
    app.add_handler(TypeHandler(Update, admin_guard), group=-1)

    add_bot_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_bot_entry, pattern="^add_bot$")],
        states={
            WAITING_ZIP: [
                MessageHandler(filters.Document.ZIP, receive_zip),
                MessageHandler(filters.Document.ALL & ~filters.Document.ZIP, non_zip_handler),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_add_bot, pattern="^menu$")],
        per_message=False,
    )

    packages_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(packages_entry_handler, pattern="^packages:")],
        states={
            WAITING_PACKAGES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, packages_install_handler),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_packages, pattern="^bot_info:")],
        per_message=False,
    )

    config_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(config_edit_entry, pattern="^edit_config:")],
        states={
            WAITING_CONFIG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, config_save_handler),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_config, pattern="^config:")],
        per_message=False,
    )

    app.add_handler(add_bot_conversation)
    app.add_handler(packages_conversation)
    app.add_handler(config_conversation)
    app.add_handler(CallbackQueryHandler(config_view_handler, pattern="^config:"))
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(start_handler, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(my_bots_handler, pattern="^my_bots$"))
    app.add_handler(CallbackQueryHandler(bot_info_handler, pattern="^bot_info:"))
    app.add_handler(CallbackQueryHandler(start_bot_handler, pattern="^start_bot:"))
    app.add_handler(CallbackQueryHandler(stop_bot_handler, pattern="^stop_bot:"))
    app.add_handler(CallbackQueryHandler(delete_bot_handler, pattern="^delete:"))
    app.add_handler(CallbackQueryHandler(confirm_delete_handler, pattern="^confirm_del:"))
    app.add_handler(CallbackQueryHandler(logs_handler, pattern="^logs:"))
    app.add_error_handler(error_handler)

    return app


async def error_handler(update, context) -> None:
    import logging
    logging.getLogger(__name__).error("Exception:", exc_info=context.error)


if __name__ == "__main__":
    application = build_app()
    ids_str = ", ".join(str(i) for i in ADMIN_IDS) if ADMIN_IDS else "всі (не обмежено)"
    print(f"Bot Manager запущено. Адміни: {ids_str}. Ctrl+C для зупинки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
