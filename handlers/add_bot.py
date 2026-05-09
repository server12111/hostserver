import asyncio
import os
import shutil
import zipfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from keyboards import sanitize_bot_name, make_bot_key, add_source_keyboard, bot_detail_keyboard

WAITING_ZIP = 1
WAITING_GIT_URL = 2
BOTS_DIR = "bots"


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
        if bots_count >= max_bots and max_bots > 0:
            msg = "⛔ Вы достигли лимита ботов для вашего тарифа.\nОбновите тариф в разделе <b>💰 Баланс / Тариф</b>."
        else:
            msg = "⛔ У вас нет активной подписки.\nОформите тариф в разделе <b>💰 Баланс / Тариф</b>."
        await query.edit_message_text(
            msg, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Тарифы", callback_data="plans")],
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
    bot_path = os.path.abspath(os.path.join(BOTS_DIR, bot_name))
    os.makedirs(bot_path, exist_ok=True)
    zip_temp = os.path.join(bot_path, "_upload.zip")

    status_msg = await update.message.reply_text("⏳ Загружаю архив...")
    tg_file = await doc.get_file()
    await tg_file.download_to_drive(zip_temp)

    try:
        with zipfile.ZipFile(zip_temp) as zf:
            for member in zf.namelist():
                if ".." in member or os.path.isabs(member):
                    raise ValueError(f"Небезопасный путь в ZIP: {member}")
            zf.extractall(bot_path)
    except zipfile.BadZipFile:
        shutil.rmtree(bot_path, ignore_errors=True)
        await status_msg.edit_text("❌ Файл не является корректным ZIP-архивом.")
        return ConversationHandler.END
    except ValueError as e:
        shutil.rmtree(bot_path, ignore_errors=True)
        await status_msg.edit_text(f"❌ {e}")
        return ConversationHandler.END
    finally:
        if os.path.exists(zip_temp):
            os.remove(zip_temp)

    return await _finalize_bot(
        update, context, status_msg, bot_name, display_name,
        bot_path, registry, manager, user_registry, user_id, source="zip",
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
    bot_path = os.path.abspath(os.path.join(BOTS_DIR, bot_name))

    status_msg = await update.message.reply_text(
        f"⏳ Клонирую репозиторий <code>{git_url}</code>...",
        parse_mode="HTML",
    )

    ok, err = await asyncio.to_thread(_git_clone, git_url, bot_path)
    if not ok:
        shutil.rmtree(bot_path, ignore_errors=True)
        await status_msg.edit_text(f"❌ Ошибка клонирования:\n<code>{err[:400]}</code>", parse_mode="HTML")
        return ConversationHandler.END

    return await _finalize_bot(
        update, context, status_msg, bot_name, display_name,
        bot_path, registry, manager, user_registry, user_id,
        source="git", git_url=git_url,
    )


def _git_clone(url: str, path: str) -> tuple[bool, str]:
    try:
        import git
        git.Repo.clone_from(url, path, depth=1)
        return True, ""
    except Exception as e:
        return False, str(e)


# ─── Финализация (общий код ZIP и Git) ────────────────────────────────────────
async def _finalize_bot(
    update, context, status_msg,
    bot_name, display_name, bot_path,
    registry, manager, user_registry, user_id,
    source="zip", git_url=None,
):
    entry_point = _find_entry_point(bot_path)
    if not entry_point:
        shutil.rmtree(bot_path, ignore_errors=True)
        await status_msg.edit_text(
            "❌ Не найдено <code>main.py</code> или <code>bot.py</code> в репозитории.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    registry.add_bot(
        bot_name, bot_path, entry_point,
        owner_id=user_id, display_name=display_name,
        source=source, git_url=git_url,
    )
    user_registry.add_bot_to_user(user_id, bot_name)

    await status_msg.edit_text(
        f"📦 Бот <b>{display_name}</b> загружен.\n⚙️ Устанавливаю зависимости...",
        parse_mode="HTML",
    )

    ok, msg = await manager.provision_bot(bot_name, bot_path)
    result_text = (
        f"✅ Бот <b>{display_name}</b> готов!\nТочка входа: <code>{entry_point}</code>"
        if ok else
        f"⚠️ Бот загружен, но есть проблемы с зависимостями:\n<code>{msg}</code>"
    )
    await status_msg.edit_text(
        result_text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ Запустить", callback_data=f"start_bot:{bot_name}"),
                InlineKeyboardButton("🤖 Мои боты", callback_data="my_bots"),
            ]
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
