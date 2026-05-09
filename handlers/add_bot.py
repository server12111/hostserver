import os
import shutil
import zipfile

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from keyboards import sanitize_bot_name, main_menu_keyboard, bot_detail_keyboard

WAITING_ZIP = 1
BOTS_DIR = "bots"


async def add_bot_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📎 Надішліть <b>ZIP-архів</b> з вашим Python-ботом.\n\n"
        "Архів повинен містити <code>main.py</code> або <code>bot.py</code> "
        "і опціонально <code>requirements.txt</code>.",
        parse_mode="HTML",
    )
    return WAITING_ZIP


async def receive_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    doc = update.message.document

    raw_name = os.path.splitext(doc.file_name)[0]
    base_name = sanitize_bot_name(raw_name)
    bot_name = base_name
    counter = 2
    while registry.exists(bot_name):
        bot_name = f"{base_name}_{counter}"
        counter += 1

    bot_path = os.path.abspath(os.path.join(BOTS_DIR, bot_name))
    os.makedirs(bot_path, exist_ok=True)
    zip_temp = os.path.join(bot_path, "_upload.zip")

    status_msg = await update.message.reply_text("⏳ Завантажую архів...")

    tg_file = await doc.get_file()
    await tg_file.download_to_drive(zip_temp)

    try:
        with zipfile.ZipFile(zip_temp) as zf:
            for member in zf.namelist():
                if ".." in member or os.path.isabs(member):
                    raise ValueError(f"Небезпечний шлях у ZIP: {member}")
            zf.extractall(bot_path)
    except zipfile.BadZipFile:
        shutil.rmtree(bot_path, ignore_errors=True)
        await status_msg.edit_text("❌ Файл не є коректним ZIP-архівом.")
        return ConversationHandler.END
    except ValueError as e:
        shutil.rmtree(bot_path, ignore_errors=True)
        await status_msg.edit_text(f"❌ {e}")
        return ConversationHandler.END
    finally:
        if os.path.exists(zip_temp):
            os.remove(zip_temp)

    entry_point = _find_entry_point(bot_path)
    if not entry_point:
        shutil.rmtree(bot_path, ignore_errors=True)
        await status_msg.edit_text(
            "❌ Не знайдено <code>main.py</code> або <code>bot.py</code> у архіві.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    registry.add_bot(bot_name, bot_path, entry_point)
    await status_msg.edit_text(
        f"📦 Бот <b>{bot_name}</b> завантажено.\n⚙️ Встановлюю залежності...",
        parse_mode="HTML",
    )

    ok, msg = await manager.provision_bot(bot_name, bot_path)
    if ok:
        result_text = (
            f"✅ Бот <b>{bot_name}</b> готовий!\n"
            f"Точка входу: <code>{entry_point}</code>"
        )
    else:
        result_text = (
            f"⚠️ Бот <b>{bot_name}</b> завантажено, але є проблеми з залежностями:\n"
            f"<code>{msg}</code>"
        )

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Запустити зараз", callback_data=f"start_bot:{bot_name}"),
            InlineKeyboardButton("📦 Мої боти", callback_data="my_bots"),
        ]
    ])
    await status_msg.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)
    return ConversationHandler.END


async def non_zip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Будь ласка, надішліть файл у форматі <b>.zip</b>.",
        parse_mode="HTML",
    )
    return WAITING_ZIP


async def cancel_add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from handlers.start import start_handler
    await start_handler(update, context)
    return ConversationHandler.END


def _find_entry_point(bot_path: str) -> str | None:
    for name in ("main.py", "bot.py"):
        if os.path.exists(os.path.join(bot_path, name)):
            return name

    subdirs = [
        d for d in os.listdir(bot_path)
        if os.path.isdir(os.path.join(bot_path, d)) and d != "venv"
    ]
    if len(subdirs) == 1:
        sub = subdirs[0]
        sub_path = os.path.join(bot_path, sub)
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
