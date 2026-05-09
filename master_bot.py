import asyncio
import os
import sys
import warnings
from datetime import datetime

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
from user_registry import UserRegistry

from handlers.start import start_handler
from handlers.my_bots import my_bots_handler, bot_info_handler
from handlers.add_bot import (
    add_bot_entry, add_zip_entry, add_git_entry,
    receive_zip, receive_git_url, non_zip_handler, cancel_add_bot,
    WAITING_ZIP, WAITING_GIT_URL,
)
from handlers.bot_actions import (
    start_bot_handler, stop_bot_handler,
    delete_bot_handler, confirm_delete_handler, logs_handler,
    config_view_handler, config_edit_entry, config_save_handler, cancel_config,
    packages_entry_handler, packages_install_handler, cancel_packages,
    WAITING_PACKAGES, WAITING_CONFIG,
)
from handlers.files import files_list_handler, download_file_handler
from handlers.payment import (
    balance_handler, plans_handler, buy_plan_handler, pay_currency_handler,
    ton_payment_handler, ton_check_handler,
)
from handlers.admin import (
    admin_command_handler, admin_users_handler, admin_bots_handler,
    admin_resources_handler, admin_user_detail_handler,
    admin_workers_handler, admin_worker_detail_handler,
    admin_worker_resources_handler, admin_worker_delete_handler,
    admin_add_worker_entry, admin_receive_worker_url,
    admin_receive_worker_secret, admin_cancel_worker,
    WAITING_WORKER_URL, WAITING_WORKER_SECRET,
)
from worker_registry import WorkerRegistry

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Создайте файл .env с BOT_TOKEN=...")

ADMIN_IDS: set[int] = set()
for _part in os.getenv("ADMIN_IDS", "").split(","):
    _part = _part.strip()
    if _part.isdigit():
        ADMIN_IDS.add(int(_part))


async def admin_guard(update: Update, context) -> None:
    user = update.effective_user
    if ADMIN_IDS and (user is None or user.id not in ADMIN_IDS):
        # Не блокируем всех — только регистрируем
        pass


async def _renewal_reminder(bot, user_registry):
    while True:
        await asyncio.sleep(3600)
        now = datetime.now()
        for u in user_registry.list_users():
            sub = u.get("subscription_until")
            if not sub:
                continue
            dt = datetime.fromisoformat(sub)
            days_left = (dt - now).days
            if days_left == 3:
                try:
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    await bot.send_message(
                        chat_id=u["user_id"],
                        text=(
                            f"⚠️ <b>Хостинг заканчивается!</b>\n\n"
                            f"До окончания: <b>3 дня</b> ({dt.strftime('%d.%m.%Y')})\n\n"
                            f"Продлите хостинг, чтобы боты продолжали работать."
                        ),
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🖥 Продлить хостинг", callback_data="plans")]
                        ]),
                    )
                except Exception:
                    pass


async def post_init(application: Application) -> None:
    registry = RegistryManager()
    registry.restore_running_bots()
    manager = BotManager(registry)
    user_registry = UserRegistry()
    application.bot_data["registry"] = registry
    application.bot_data["manager"] = manager
    application.bot_data["user_registry"] = user_registry
    application.bot_data["admin_ids"] = ADMIN_IDS
    worker_registry = WorkerRegistry()
    application.bot_data["worker_registry"] = worker_registry
    manager.set_telegram_bot(application.bot)
    asyncio.create_task(_renewal_reminder(application.bot, user_registry))


async def post_shutdown(application: Application) -> None:
    manager = application.bot_data.get("manager")
    if manager:
        manager.stop_all()


async def error_handler(update, context) -> None:
    import logging
    logging.getLogger(__name__).error("Exception:", exc_info=context.error)


def build_app() -> Application:
    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ── ConversationHandler: добавление бота ──────────────────────────────────
    add_bot_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_bot_entry, pattern="^add_bot$")],
        states={
            WAITING_ZIP: [
                CallbackQueryHandler(add_zip_entry, pattern="^add_zip$"),
                CallbackQueryHandler(add_git_entry, pattern="^add_git$"),
                MessageHandler(filters.Document.ZIP, receive_zip),
                MessageHandler(filters.Document.ALL & ~filters.Document.ZIP, non_zip_handler),
            ],
            WAITING_GIT_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_git_url),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_add_bot, pattern="^menu$")],
        per_message=False,
    )

    # ── ConversationHandler: пакеты ───────────────────────────────────────────
    packages_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(packages_entry_handler, pattern="^packages:")],
        states={
            WAITING_PACKAGES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, packages_install_handler),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_packages, pattern="^bot_info:")],
        per_message=False,
    )

    # ── ConversationHandler: конфиг ───────────────────────────────────────────
    config_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(config_edit_entry, pattern="^edit_config:")],
        states={
            WAITING_CONFIG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, config_save_handler),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_config, pattern="^config:")],
        per_message=False,
    )

    # ── ConversationHandler: добавление воркера ──────────────────────────────
    add_worker_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_worker_entry, pattern="^admin_add_worker$")],
        states={
            WAITING_WORKER_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_worker_url),
            ],
            WAITING_WORKER_SECRET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_worker_secret),
            ],
        },
        fallbacks=[CallbackQueryHandler(admin_cancel_worker, pattern="^admin_workers$")],
        per_message=False,
    )

    app.add_handler(add_bot_conv)
    app.add_handler(packages_conv)
    app.add_handler(config_conv)
    app.add_handler(add_worker_conv)

    # ── Команды ───────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("admin", admin_command_handler))

    # ── Главное меню ──────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(start_handler, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(my_bots_handler, pattern="^my_bots$"))
    app.add_handler(CallbackQueryHandler(bot_info_handler, pattern="^bot_info:"))

    # ── Действия с ботом ──────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(start_bot_handler, pattern="^start_bot:"))
    app.add_handler(CallbackQueryHandler(stop_bot_handler, pattern="^stop_bot:"))
    app.add_handler(CallbackQueryHandler(delete_bot_handler, pattern="^delete:"))
    app.add_handler(CallbackQueryHandler(confirm_delete_handler, pattern="^confirm_del:"))
    app.add_handler(CallbackQueryHandler(logs_handler, pattern="^logs:"))
    app.add_handler(CallbackQueryHandler(config_view_handler, pattern="^config:"))
    app.add_handler(CallbackQueryHandler(files_list_handler, pattern="^files:"))
    app.add_handler(CallbackQueryHandler(download_file_handler, pattern="^dl_file:"))

    # ── Оплата ────────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(balance_handler, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(plans_handler, pattern="^plans$"))
    app.add_handler(CallbackQueryHandler(buy_plan_handler, pattern="^buy_plan:"))
    app.add_handler(CallbackQueryHandler(pay_currency_handler, pattern="^pay_currency:"))
    app.add_handler(CallbackQueryHandler(ton_payment_handler, pattern="^pay_ton:"))
    app.add_handler(CallbackQueryHandler(ton_check_handler, pattern="^ton_check:"))

    # ── Админ-панель ──────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(admin_command_handler, pattern="^admin_menu$"))
    app.add_handler(CallbackQueryHandler(admin_users_handler, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_bots_handler, pattern="^admin_bots$"))
    app.add_handler(CallbackQueryHandler(admin_resources_handler, pattern="^admin_resources$"))
    app.add_handler(CallbackQueryHandler(admin_user_detail_handler, pattern="^admin_user:"))
    app.add_handler(CallbackQueryHandler(admin_workers_handler, pattern="^admin_workers$"))
    app.add_handler(CallbackQueryHandler(admin_worker_detail_handler, pattern="^admin_worker:"))
    app.add_handler(CallbackQueryHandler(admin_worker_resources_handler, pattern="^admin_worker_res:"))
    app.add_handler(CallbackQueryHandler(admin_worker_delete_handler, pattern="^admin_worker_del:"))

    app.add_error_handler(error_handler)
    return app


if __name__ == "__main__":
    application = build_app()
    ids_str = ", ".join(str(i) for i in ADMIN_IDS) if ADMIN_IDS else "не ограничено"
    print(f"Bot Hosting запущен. Админы: {ids_str}. Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
