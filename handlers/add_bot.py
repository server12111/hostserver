import asyncio
import io
import os
import shutil
import zipfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from keyboards import sanitize_bot_name, make_bot_key, add_source_keyboard, bot_detail_keyboard
import worker_client

WAITING_ZIP = 1
WAITING_GIT_URL = 2
BOTS_DIR = "bots"
MAX_BOTS_PER_WORKER = 5


def _is_admin(user_id: int, context) -> bool:
    return user_id in context.bot_data.get("admin_ids", set())


# ─── Вход: выбор источника ────────────────────────────────────────────────────
async def add_bot_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_registry = context.bot_data["user_registry"]

    if not _is_admin(user_id, context) and not user_registry.can_add_bot(user_id):
        u = user_registry.get_user(user_id)
        bots_count = len(u.get("bots", [])) if u else 0
        max_bots = u.get("max_bots", 0) if u else 0
        if max_bots > 0 and bots_count >= max_bots:
            msg = (
                "🖥 <b>Все слоты заняты</b>\n\n"
                f"У вас {bots_count} из {max_bots} ботов.\n\n"
                "Купите ещё один хостинг-слот\nчтобы добавить нового бота."
            )
        else:
            msg = (
                "🖥 <b>Необходим хостинг</b>\n\n"
                "▸ 1 бот · 2 ГБ RAM · 10 ГБ диск\n"
                "▸ 3 USDT / 30 дней\n\n"
                "Купите хостинг — и сразу сможете\nдобавить своего бота."
            )
        await query.edit_message_text(
            msg, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖥 Купить хостинг", callback_data="plans")],
                [InlineKeyboardButton("🔙 Назад", callback_data="menu")],
            ]),
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "➕ <b>Добавить бота</b>\n\nВыберите способ загрузки:",
        parse_mode="HTML",
        reply_markup=add_source_keyboard(),
    )
    return WAITING_ZIP  # ждём выбор ZIP или Git


# ─── Выбор ZIP ────────────────────────────────────────────────────────────────
async def add_zip_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📦 Отправьте <b>ZIP-архив</b> с вашим Python-ботом.\n\n"
        "Архив должен содержать <code>main.py</code> или <code>bot.py</code> "
        "и опционально <code>requirements.txt</code>.",
        parse_mode="HTML",
    )
    return WAITING_ZIP


# ─── Выбор Git ────────────────────────────────────────────────────────────────
async def add_git_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔗 Отправьте <b>URL Git-репозитория</b>:\n\n"
        "<code>https://github.com/user/mybot</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="menu")]
        ]),
    )
    return WAITING_GIT_URL


# ─── Получение ZIP ────────────────────────────────────────────────────────────
async def receive_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    user_registry = context.bot_data["user_registry"]
    doc = update.message.document

    display_name = sanitize_bot_name(os.path.splitext(doc.file_name)[0])
    bot_name = _unique_name(make_bot_key(display_name, user_id), registry)

    status_msg = await update.message.reply_text("⏳ Загружаю архив...")
    tg_file = await doc.get_file()
    zip_bytes = await tg_file.download_as_bytearray()

    return await _finalize_bot(
        update, context, status_msg, bot_name, display_name,
        registry, manager, user_registry, user_id,
        source="zip", zip_bytes=bytes(zip_bytes),
    )


# ─── Получение Git URL ────────────────────────────────────────────────────────
async def receive_git_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    user_registry = context.bot_data["user_registry"]
    git_url = update.message.text.strip()

    if not (git_url.startswith("http://") or git_url.startswith("https://")):
        await update.message.reply_text("❌ Неверный URL. Отправьте ссылку на Git-репозиторий.")
        return WAITING_GIT_URL

    raw_name = git_url.rstrip("/").split("/")[-1]
    if raw_name.endswith(".git"):
        raw_name = raw_name[:-4]
    display_name = sanitize_bot_name(raw_name)
    bot_name = _unique_name(make_bot_key(display_name, user_id), registry)

    status_msg = await update.message.reply_text(
        f"⏳ Клонирую репозиторий <code>{git_url}</code>...",
        parse_mode="HTML",
    )

    return await _finalize_bot(
        update, context, status_msg, bot_name, display_name,
        registry, manager, user_registry, user_id,
        source="git", git_url=git_url,
    )


def _git_clone(url: str, path: str) -> tuple[bool, str]:
    try:
        import git
        git.Repo.clone_from(url, path, depth=1)
        return True, ""
    except Exception as e:
        return False, str(e)


# ─── Выбор воркера ────────────────────────────────────────────────────────────
async def _pick_worker(context) -> dict | None:
    wr = context.bot_data.get("worker_registry")
    if not wr:
        return None
    workers = wr.list_workers()
    if not workers:
        return None
    registry = context.bot_data["registry"]
    online = []
    for w in workers:
        h = await worker_client.health(w)
        if h.get("ok"):
            w = dict(w)
            w["_bots"] = len(registry.list_bots_by_worker(w["id"]))
            online.append(w)
    online = [w for w in online if w["_bots"] < MAX_BOTS_PER_WORKER]
    if not online:
        return None
    return min(online, key=lambda w: w["_bots"])


# ─── Нотификации об общей загрузке всех воркеров ─────────────────────────────
async def _notify_global_load(context, bots_before: int):
    admin_ids = context.bot_data.get("admin_ids", set())
    wr = context.bot_data.get("worker_registry")
    if not admin_ids or not wr:
        return
    workers = wr.list_workers()
    if not workers:
        return
    registry = context.bot_data["registry"]
    total_capacity = len(workers) * MAX_BOTS_PER_WORKER
    total_bots = sum(len(registry.list_bots_by_worker(w["id"])) for w in workers)
    bots_after = total_bots
    thresholds = [50, 75] + list(range(80, 101, 10))
    crossed = [
        t for t in thresholds
        if bots_before / total_capacity * 100 < t <= bots_after / total_capacity * 100
    ]
    for t in crossed:
        emoji = "🔴" if t >= 90 else "🟡" if t >= 75 else "🟠"
        text = (
            f"{emoji} <b>Загальне заповнення воркерів: {t}%</b>\n"
            f"Ботів: <b>{bots_after}/{total_capacity}</b> "
            f"({len(workers)} воркерів × {MAX_BOTS_PER_WORKER})"
        )
        for admin_id in admin_ids:
            try:
                await context.bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception:
                pass


# ─── Финализация (общий код ZIP и Git) ────────────────────────────────────────
async def _finalize_bot(
    update, context, status_msg,
    bot_name, display_name,
    registry, manager, user_registry, user_id,
    source="zip", git_url=None, zip_bytes=None,
):
    chosen_worker = await _pick_worker(context)

    if chosen_worker:
        # ── Деплой на воркер ──────────────────────────────────────────────────
        await status_msg.edit_text(
            f"⏳ Деплою бота <b>{display_name}</b> на воркер <b>{chosen_worker['label']}</b>...",
            parse_mode="HTML",
        )
        if source == "zip":
            ok, entry_point = await worker_client.deploy_zip(
                chosen_worker, bot_name, zip_bytes, display_name, user_id
            )
        else:
            ok, entry_point = await worker_client.deploy_git(
                chosen_worker, bot_name, git_url, display_name, user_id
            )
        if not ok:
            await status_msg.edit_text(
                f"❌ Ошибка деплоя на воркер:\n<code>{entry_point}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
                ]),
            )
            return ConversationHandler.END

        wr = context.bot_data.get("worker_registry")
        all_workers = wr.list_workers() if wr else []
        bots_before_global = sum(len(registry.list_bots_by_worker(w["id"])) for w in all_workers)
        registry.add_bot(
            bot_name, "", entry_point,
            owner_id=user_id, display_name=display_name,
            source=source, git_url=git_url, worker_id=chosen_worker["id"],
        )
        user_registry.add_bot_to_user(user_id, bot_name)
        await _notify_global_load(context, bots_before_global)
        await status_msg.edit_text(
            f"✅ Бот <b>{display_name}</b> задеплоен на <b>{chosen_worker['label']}</b>!\n"
            f"Точка входа: <code>{entry_point}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("▶️ Запустить", callback_data=f"start_bot:{bot_name}"),
                    InlineKeyboardButton("🤖 Мои боты", callback_data="my_bots"),
                ]
            ]),
        )
        return ConversationHandler.END

    # ── Всі воркери заповнені або недоступні ─────────────────────────────────
    await status_msg.edit_text(
        "❌ <b>Немає доступних воркерів</b>\n\n"
        "Всі сервери заповнені або недоступні.\n"
        "Зверніться до адміністратора.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
        ]),
    )
    return ConversationHandler.END


# ─── Не-ZIP документ ──────────────────────────────────────────────────────────
async def non_zip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Пожалуйста, отправьте файл в формате <b>.zip</b>.", parse_mode="HTML")
    return WAITING_ZIP


async def cancel_add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from handlers.start import start_handler
    await start_handler(update, context)
    return ConversationHandler.END


# ─── Утилиты ──────────────────────────────────────────────────────────────────
def _unique_name(base: str, registry) -> str:
    name = base
    counter = 2
    while registry.exists(name):
        name = f"{base}_{counter}"
        counter += 1
    return name


def _find_entry_point(bot_path: str) -> str | None:
    for name in ("main.py", "bot.py"):
        if os.path.exists(os.path.join(bot_path, name)):
            return name
    subdirs = [d for d in os.listdir(bot_path)
               if os.path.isdir(os.path.join(bot_path, d)) and d not in ("venv", ".git")]
    if len(subdirs) == 1:
        sub_path = os.path.join(bot_path, subdirs[0])
        for name in ("main.py", "bot.py"):
            if os.path.exists(os.path.join(sub_path, name)):
                _flatten_subdir(bot_path, sub_path)
                return name
    return None


def _flatten_subdir(bot_path: str, sub_path: str):
    for item in os.listdir(sub_path):
        src = os.path.join(sub_path, item)
        dst = os.path.join(bot_path, item)
        if not os.path.exists(dst):
            shutil.move(src, dst)
    shutil.rmtree(sub_path, ignore_errors=True)
