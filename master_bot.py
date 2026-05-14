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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    start_bot_handler, stop_bot_handler, restart_bot_handler,
    delete_bot_handler, confirm_delete_handler, logs_handler,
    config_view_handler, config_edit_entry, config_save_handler, cancel_config,
    packages_entry_handler, packages_install_handler, cancel_packages,
    update_bot_handler, update_git_handler, update_zip_entry, receive_update_zip,
    WAITING_PACKAGES, WAITING_CONFIG, WAITING_UPDATE_ZIP,
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
    admin_download_db_handler, admin_upload_db_entry,
    admin_receive_db_handler, admin_cancel_db,
    admin_broadcast_entry, admin_broadcast_preview,
    admin_broadcast_confirm, admin_cancel_broadcast,
    admin_gift_entry, admin_gift_receive_user,
    admin_gift_receive_days, admin_cancel_gift,
    admin_stats_handler,
    WAITING_WORKER_URL, WAITING_WORKER_SECRET, WAITING_DB_FILE,
    WAITING_BROADCAST_TEXT, WAITING_BROADCAST_CONFIRM,
    WAITING_GIFT_USER, WAITING_GIFT_DAYS,
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


async def _worker_monitor(bot, bot_data: dict) -> None:
    import worker_client as wc
    await asyncio.sleep(90)  # ждём завершения startup sync
    while True:
        await asyncio.sleep(60)
        wr = bot_data.get("worker_registry")
        registry = bot_data.get("registry")
        admin_ids = bot_data.get("admin_ids", set())
        if not wr or not registry or not admin_ids:
            continue
        for worker in wr.list_workers():
            try:
                events = await wc.poll_events(worker)
            except Exception:
                continue
            for ev in events:
                bot_name = ev.get("bot_name", "")
                ev_type = ev.get("event", "")
                restarts = ev.get("restarts", 0)
                reg_bot = registry.get_bot(bot_name)
                display = reg_bot.get("display_name", bot_name) if reg_bot else bot_name

                if ev_type == "restarted":
                    text = (
                        f"⚠️ <b>Бот упал и был перезапущен</b>\n\n"
                        f"Бот: <b>{display}</b>\n"
                        f"Воркер: <b>{worker['label']}</b>\n"
                        f"Перезапуск #{restarts} из {3}"
                    )
                elif ev_type == "max_restarts":
                    registry.update_bot(bot_name, status="stopped")
                    text = (
                        f"🔴 <b>Бот остановлен — превышен лимит перезапусков</b>\n\n"
                        f"Бот: <b>{display}</b>\n"
                        f"Воркер: <b>{worker['label']}</b>\n"
                        f"Попыток перезапуска: {restarts}\n\n"
                        f"Запустите бота вручную после исправления ошибки."
                    )
                else:
                    continue

                for admin_id in admin_ids:
                    try:
                        await bot.send_message(admin_id, text, parse_mode="HTML")
                    except Exception:
                        pass


async def _sync_worker_states(bot_data: dict) -> None:
    import worker_client as wc
    wr = bot_data.get("worker_registry")
    registry = bot_data["registry"]
    if not wr:
        return
    for worker in wr.list_workers():
        try:
            res = await wc.resources(worker)
            running_names = {r["name"] for r in res}
            for bot in registry.list_bots_by_worker(worker["id"]):
                status = "running" if bot["name"] in running_names else "stopped"
                registry.update_bot(bot["name"], status=status)
            print(f"[sync] {worker['label']}: {len(running_names)} running bots synced")
        except Exception as e:
            print(f"[sync] {worker.get('label', worker['id'])} unavailable: {e}")


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
            if days_left not in (7, 3, 1):
                continue
            if days_left == 7:
                text = (
                    f"⚠️ <b>Хостинг заканчивается через 7 дней</b>\n\n"
                    f"Дата окончания: <b>{dt.strftime('%d.%m.%Y')}</b>\n\n"
                    f"Продлите хостинг заранее, чтобы боты работали без перебоев."
                )
            elif days_left == 3:
                text = (
                    f"⚠️ <b>Хостинг заканчивается!</b>\n\n"
                    f"До окончания: <b>3 дня</b> ({dt.strftime('%d.%m.%Y')})\n\n"
                    f"Продлите хостинг, чтобы боты продолжали работать."
                )
            else:
                text = (
                    f"🔴 <b>Хостинг заканчивается завтра!</b>\n\n"
                    f"Дата окончания: <b>{dt.strftime('%d.%m.%Y')}</b>\n\n"
                    f"Продлите хостинг сейчас, чтобы избежать остановки ботов."
                )
            try:
                await bot.send_message(
                    chat_id=u["user_id"],
                    text=text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🖥 Продлить хостинг", callback_data="plans")]
                    ]),
                )
            except Exception:
                pass


async def _send_trigger(bot, chat_id: int, text: str, markup=None) -> bool:
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=markup)
        return True
    except Exception:
        return False


async def _trigger_messages(bot, bot_data: dict) -> None:
    """Onboarding + win-back triggers. Skips users with active subscription."""
    await asyncio.sleep(240)
    while True:
        await asyncio.sleep(3600)
        user_registry = bot_data.get("user_registry")
        registry = bot_data.get("registry")
        admin_ids = bot_data.get("admin_ids", set())
        if not user_registry or not registry:
            continue
        now = datetime.now()
        plans_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖥 Купить хостинг", callback_data="plans")]
        ])
        for u in user_registry.list_users():
            if u["user_id"] in admin_ids:
                continue
            sub = u.get("subscription_until")
            # Skip users with active subscription
            if sub and datetime.fromisoformat(sub) > now:
                continue
            user_id = u["user_id"]
            sent = set(u.get("sent_triggers", []))
            reg = u.get("registered_at")
            if not reg:
                continue
            try:
                reg_dt = datetime.fromisoformat(reg)
            except Exception:
                continue
            days_since_reg = (now - reg_dt).days
            user_bots = registry.list_bots_by_owner(user_id)
            new_triggers = set()

            # ── Онбординг (никогда не платил) ──────────────────────────────
            if not sub:
                if days_since_reg >= 1 and "ob_day1" not in sent and not user_bots:
                    if await _send_trigger(
                        bot, user_id,
                        "👋 <b>Нужна помощь с первым ботом?</b>\n\n"
                        "Загрузите <b>ZIP-архив</b> или вставьте Git-ссылку —\n"
                        "запустим за 30 секунд.\n\n"
                        "Купите хостинг и добавьте первого бота прямо сейчас.",
                        plans_kb,
                    ):
                        new_triggers.add("ob_day1")

                elif days_since_reg >= 3 and "ob_day3" not in sent and user_bots:
                    if await _send_trigger(
                        bot, user_id,
                        "⚡ <b>Ваш бот ждёт запуска</b>\n\n"
                        "Вы добавили бота, но ещё не купили хостинг.\n\n"
                        "Запустите прямо сейчас — от <b>2$ в месяц</b>.",
                        plans_kb,
                    ):
                        new_triggers.add("ob_day3")

                elif days_since_reg >= 7 and "ob_day7" not in sent:
                    if await _send_trigger(
                        bot, user_id,
                        "🎁 <b>Специальное предложение</b>\n\n"
                        "Хостинг для Telegram-бота — от <b>2$ в месяц</b>.\n"
                        "Никаких скрытых платежей. Запустите за пару минут.",
                        plans_kb,
                    ):
                        new_triggers.add("ob_day7")

            # ── Win-back (подписка истекла) ─────────────────────────────────
            if sub:
                try:
                    exp_dt = datetime.fromisoformat(sub)
                except Exception:
                    continue
                if exp_dt >= now:
                    continue
                days_expired = (now - exp_dt).days

                if days_expired >= 3 and "wb_day3" not in sent:
                    if await _send_trigger(
                        bot, user_id,
                        "😔 <b>Ваш бот остановлен уже 3 дня</b>\n\n"
                        "Все файлы и настройки сохранены.\n\n"
                        "Возобновите хостинг — бот снова заработает.",
                        plans_kb,
                    ):
                        new_triggers.add("wb_day3")

                elif days_expired >= 7 and "wb_day7" not in sent:
                    if await _send_trigger(
                        bot, user_id,
                        "⏰ <b>Прошла неделя</b>\n\n"
                        "Ваш бот не работает уже <b>7 дней</b>.\n"
                        "Файлы в сохранности — просто продлите хостинг.",
                        plans_kb,
                    ):
                        new_triggers.add("wb_day7")

                elif days_expired >= 14 and "wb_day14" not in sent:
                    if await _send_trigger(
                        bot, user_id,
                        "⚠️ <b>2 недели без хостинга</b>\n\n"
                        "Ваш бот всё ещё ждёт вас.\n"
                        "Продлите — и продолжите с того места, где остановились.",
                        plans_kb,
                    ):
                        new_triggers.add("wb_day14")

                elif days_expired >= 30 and "wb_day30" not in sent:
                    if await _send_trigger(
                        bot, user_id,
                        "🔴 <b>Месяц без хостинга</b>\n\n"
                        "Возвращайтесь — все данные вашего бота сохранены.",
                        plans_kb,
                    ):
                        new_triggers.add("wb_day30")

                elif days_expired >= 60 and "wb_day60" not in sent:
                    if await _send_trigger(
                        bot, user_id,
                        "💔 <b>Мы скучаем</b>\n\n"
                        "2 месяца без активного бота.\n\n"
                        "Возвращайтесь — всё ещё можно восстановить.",
                        plans_kb,
                    ):
                        new_triggers.add("wb_day60")

            if new_triggers:
                user_registry.update_user(
                    user_id,
                    sent_triggers=list(sent | new_triggers),
                )


async def _subscription_enforcer(bot, bot_data: dict) -> None:
    import worker_client as wc
    await asyncio.sleep(120)
    while True:
        await asyncio.sleep(3600)
        user_registry = bot_data.get("user_registry")
        registry = bot_data.get("registry")
        manager = bot_data.get("manager")
        wr = bot_data.get("worker_registry")
        admin_ids = bot_data.get("admin_ids", set())
        if not all([user_registry, registry, manager]):
            continue
        now = datetime.now()
        for u in user_registry.list_users():
            if u["user_id"] in admin_ids:
                continue
            sub = u.get("subscription_until")
            if not sub:
                continue
            if datetime.fromisoformat(sub) >= now:
                continue
            user_id = u["user_id"]
            user_bots = registry.list_bots_by_owner(user_id)
            stopped = []
            for bot_rec in user_bots:
                bot_name = bot_rec["name"]
                display = bot_rec.get("display_name", bot_name)
                worker_id = bot_rec.get("worker_id")
                if worker_id:
                    if bot_rec.get("status") != "running":
                        continue
                    w = wr.get_worker(worker_id) if wr else None
                    if w:
                        try:
                            await wc.stop(w, bot_name)
                        except Exception:
                            pass
                    registry.update_bot(bot_name, status="stopped")
                    stopped.append(display)
                else:
                    if not manager.is_running(bot_name):
                        continue
                    try:
                        manager.stop_bot(bot_name)
                    except Exception:
                        pass
                    stopped.append(display)
            if stopped:
                lines = "\n".join(f"• {n}" for n in stopped)
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"🔴 <b>Подписка истекла — боты остановлены</b>\n\n"
                            f"Остановлено: <b>{len(stopped)}</b>\n"
                            f"{lines}\n\n"
                            f"Продлите хостинг, чтобы возобновить работу ботов."
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
    asyncio.create_task(_sync_worker_states(application.bot_data))
    asyncio.create_task(_worker_monitor(application.bot, application.bot_data))
    asyncio.create_task(_renewal_reminder(application.bot, user_registry))
    asyncio.create_task(_subscription_enforcer(application.bot, application.bot_data))
    asyncio.create_task(_trigger_messages(application.bot, application.bot_data))


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

    # ── ConversationHandler: оновлення ZIP ───────────────────────────────────
    update_zip_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(update_zip_entry, pattern="^update_zip:")],
        states={
            WAITING_UPDATE_ZIP: [
                MessageHandler(filters.Document.ZIP, receive_update_zip),
                MessageHandler(filters.Document.ALL & ~filters.Document.ZIP, receive_update_zip),
            ],
        },
        fallbacks=[CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^bot_info:")],
        per_message=False,
    )

    # ── ConversationHandler: загрузка БД ─────────────────────────────────────
    upload_db_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_upload_db_entry, pattern="^admin_upload_db$")],
        states={
            WAITING_DB_FILE: [
                MessageHandler(filters.Document.ALL, admin_receive_db_handler),
            ],
        },
        fallbacks=[CallbackQueryHandler(admin_cancel_db, pattern="^admin_menu$")],
        per_message=False,
    )

    # ── ConversationHandler: рассылка ─────────────────────────────────────────
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_entry, pattern="^admin_broadcast$")],
        states={
            WAITING_BROADCAST_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_preview),
            ],
            WAITING_BROADCAST_CONFIRM: [
                CallbackQueryHandler(admin_broadcast_confirm, pattern="^admin_broadcast_send$"),
                CallbackQueryHandler(admin_cancel_broadcast, pattern="^admin_menu$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(admin_cancel_broadcast, pattern="^admin_menu$")],
        per_message=False,
    )

    # ── ConversationHandler: выдача слота ─────────────────────────────────────
    gift_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_gift_entry, pattern="^admin_gift$")],
        states={
            WAITING_GIFT_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_receive_user),
            ],
            WAITING_GIFT_DAYS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_gift_receive_days),
            ],
        },
        fallbacks=[CallbackQueryHandler(admin_cancel_gift, pattern="^admin_menu$")],
        per_message=False,
    )

    app.add_handler(add_bot_conv)
    app.add_handler(packages_conv)
    app.add_handler(config_conv)
    app.add_handler(add_worker_conv)
    app.add_handler(update_zip_conv)
    app.add_handler(upload_db_conv)
    app.add_handler(broadcast_conv)
    app.add_handler(gift_conv)

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
    app.add_handler(CallbackQueryHandler(restart_bot_handler, pattern="^restart_bot:"))
    app.add_handler(CallbackQueryHandler(delete_bot_handler, pattern="^delete:"))
    app.add_handler(CallbackQueryHandler(confirm_delete_handler, pattern="^confirm_del:"))
    app.add_handler(CallbackQueryHandler(logs_handler, pattern="^logs:"))
    app.add_handler(CallbackQueryHandler(update_bot_handler, pattern="^update_bot:"))
    app.add_handler(CallbackQueryHandler(update_git_handler, pattern="^update_git:"))
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
    app.add_handler(CallbackQueryHandler(admin_download_db_handler, pattern="^admin_download_db$"))
    app.add_handler(CallbackQueryHandler(admin_stats_handler, pattern="^admin_stats$"))

    app.add_error_handler(error_handler)
    return app


if __name__ == "__main__":
    application = build_app()
    ids_str = ", ".join(str(i) for i in ADMIN_IDS) if ADMIN_IDS else "не ограничено"
    print(f"Bot Hosting запущен. Админы: {ids_str}. Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
