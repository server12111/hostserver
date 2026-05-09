from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from keyboards import (
    admin_menu_keyboard, admin_users_keyboard,
    admin_bots_keyboard, admin_resources_keyboard,
)


def _is_admin(user_id: int, context) -> bool:
    return user_id in context.bot_data.get("admin_ids", set())


async def admin_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_admin(user_id, context):
        if update.message:
            await update.message.reply_text("⛔ Нет доступа.")
        return
    text = "🛠 <b>Панель администратора</b>"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode="HTML", reply_markup=admin_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=admin_menu_keyboard()
        )


async def admin_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    user_registry = context.bot_data["user_registry"]
    users = user_registry.list_users()
    if not users:
        await query.edit_message_text(
            "👥 Пользователей нет.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")]
            ]),
        )
        return
    await query.edit_message_text(
        f"👥 <b>Пользователи ({len(users)}):</b>",
        parse_mode="HTML",
        reply_markup=admin_users_keyboard(users),
    )


async def admin_bots_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    registry = context.bot_data["registry"]
    manager = context.bot_data["manager"]
    bots = registry.list_bots()
    if not bots:
        await query.edit_message_text(
            "🤖 Ботов нет.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu")]
            ]),
        )
        return
    running = sum(1 for b in bots if manager.is_running(b["name"]))
    await query.edit_message_text(
        f"🤖 <b>Все боты ({len(bots)}, запущено: {running}):</b>",
        parse_mode="HTML",
        reply_markup=admin_bots_keyboard(bots, manager),
    )


async def admin_resources_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    manager = context.bot_data["manager"]
    resources = manager.get_all_resources()
    if not resources:
        await query.edit_message_text(
            "📊 <b>Ресурсы</b>\n\n<i>Нет запущенных ботов.</i>",
            parse_mode="HTML",
            reply_markup=admin_resources_keyboard(),
        )
        return
    lines = ["📊 <b>Ресурсы запущенных ботов:</b>\n"]
    for r in resources:
        lines.append(
            f"• <b>{r['display']}</b>\n"
            f"  CPU: {r['cpu']}% | RAM: {r['ram_mb']} MB"
        )
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=admin_resources_keyboard(),
    )


async def admin_user_detail_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id, context):
        await query.answer("⛔ Нет доступа.", show_alert=True)
        return
    user_id = int(query.data.split(":", 1)[1])
    user_registry = context.bot_data["user_registry"]
    u = user_registry.get_user(user_id)
    if not u:
        await query.answer("Пользователь не найден.", show_alert=True)
        return
    from payments import PLANS
    plan_name = PLANS.get(u.get("plan", ""), {}).get("name", "—") if u.get("plan") else "—"
    sub_status = user_registry.subscription_status(user_id)
    bots = u.get("bots", [])
    text = (
        f"👤 <b>Пользователь {u.get('username') or user_id}</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"Тариф: <b>{plan_name}</b>\n"
        f"Подписка: <b>{sub_status}</b>\n"
        f"Ботов: <b>{len(bots)} / {u.get('max_bots', 0)}</b>\n"
        f"Регистрация: {u.get('registered_at', '—')}"
    )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_users")]
        ]),
    )
