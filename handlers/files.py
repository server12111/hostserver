import os

from telegram import Update
from telegram.ext import ContextTypes

from keyboards import files_keyboard


def _is_admin(user_id: int, context) -> bool:
    return user_id in context.bot_data.get("admin_ids", set())


def _has_access(user_id: int, bot: dict, context) -> bool:
    return _is_admin(user_id, context) or bot.get("owner_id") == user_id


HIDDEN = {".env", ".git"}


async def files_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_name = query.data.split(":", 1)[1]
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return

    bot_path = bot["path"]
    try:
        files = sorted([
            f for f in os.listdir(bot_path)
            if os.path.isfile(os.path.join(bot_path, f)) and f not in HIDDEN
        ])
    except Exception:
        files = []

    context.user_data[f"files_{bot_name}"] = files

    if not files:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        await query.edit_message_text(
            f"📁 <b>Файлы: {bot.get('display_name', bot_name)}</b>\n\n<i>(папка пуста)</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data=f"bot_info:{bot_name}")]
            ]),
        )
        return

    await query.edit_message_text(
        f"📁 <b>Файлы: {bot.get('display_name', bot_name)}</b>\n\nНажмите на файл, чтобы скачать:",
        parse_mode="HTML",
        reply_markup=files_keyboard(bot_name, files),
    )


async def download_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, bot_name, idx_str = parts
    user_id = query.from_user.id
    registry = context.bot_data["registry"]
    bot = registry.get_bot(bot_name)
    if not bot or not _has_access(user_id, bot, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return

    files = context.user_data.get(f"files_{bot_name}", [])
    try:
        idx = int(idx_str)
        filename = files[idx]
    except (ValueError, IndexError):
        await query.answer("❌ Файл не найден.", show_alert=True)
        return

    file_path = os.path.join(bot["path"], filename)
    if not os.path.exists(file_path):
        await query.answer("❌ Файл не существует.", show_alert=True)
        return

    try:
        with open(file_path, "rb") as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=filename,
                caption=f"📄 <code>{filename}</code>",
                parse_mode="HTML",
            )
    except Exception as e:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"❌ Ошибка отправки файла: {e}",
        )
