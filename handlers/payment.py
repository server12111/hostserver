import asyncio
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from keyboards import balance_keyboard, plans_keyboard, currency_keyboard, payment_keyboard, ton_payment_keyboard
from payments import (
    PLANS, create_invoice, poll_invoice,
    get_ton_amount, make_ton_comment, poll_ton_payment, check_ton_payment_once,
)

_SEP = "━━━━━━━━━━━━━━━"


async def balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or str(user_id)
    user_registry = context.bot_data["user_registry"]
    u = user_registry.get_user(user_id)
    if not u:
        await query.edit_message_text("❌ Пользователь не найден.")
        return

    sub_status = user_registry.subscription_status(user_id)
    slots = u.get("max_bots", 0)
    bots_count = len(u.get("bots", []))

    await query.edit_message_text(
        f"🖥 <b>Мой хостинг</b>\n"
        f"{_SEP}\n"
        f"👤 @{username}\n"
        f"🤖 Слотов: <b>{slots}</b>  |  Ботов: <b>{bots_count} / {slots}</b>\n"
        f"📅 {sub_status}\n"
        f"{_SEP}",
        parse_mode="HTML",
        reply_markup=balance_keyboard(),
    )


async def plans_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lines = [
        f"🖥 <b>Хостинг для Python-бота</b>\n{_SEP}",
        f"▸ 1 бот · 30 дней · +1 слот за покупку\n{_SEP}",
    ]
    for plan in PLANS.values():
        lines.append(
            f"💾 <b>{plan['ram']} RAM</b> — {plan['price']} USDT\n"
            f"   📁 Диск: {plan['disk']}"
        )
    lines.append(_SEP)
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=plans_keyboard(),
    )


async def buy_plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.split(":", 1)[1]
    if plan_key not in PLANS:
        await query.answer("❌ Хостинг не найден.", show_alert=True)
        return
    plan = PLANS[plan_key]
    context.user_data["selected_plan"] = plan_key
    await query.edit_message_text(
        f"💳 <b>Оплата хостинга</b>\n"
        f"{_SEP}\n"
        f"▸ 1 бот · {plan['ram']} RAM · {plan['disk']} диск\n"
        f"▸ Срок: {plan['days']} дней\n"
        f"▸ Сумма: <b>{plan['price']} USDT</b>\n"
        f"{_SEP}\n"
        f"Выберите способ оплаты:",
        parse_mode="HTML",
        reply_markup=currency_keyboard(plan_key),
    )


async def pay_currency_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":", 2)
    if len(parts) != 3:
        return
    _, plan_key, currency = parts
    if plan_key not in PLANS:
        await query.answer("❌ Хостинг не найден.", show_alert=True)
        return

    plan = PLANS[plan_key]
    user_id = query.from_user.id
    payload = f"{user_id}:{plan_key}"

    await query.edit_message_text(
        f"⏳ Создаю счёт на <b>{plan['price']} {currency}</b>...",
        parse_mode="HTML",
    )

    inv = await create_invoice(
        amount=plan["price"],
        asset=currency,
        payload=payload,
        description=f"Bot Hosting — 1 слот / {plan['days']} дней",
    )

    if not inv:
        await query.edit_message_text(
            "❌ Не удалось создать счёт.\nПроверьте настройки CRYPTOBOT_TOKEN.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="plans")]
            ]),
        )
        return

    pay_url = inv.get("bot_invoice_url") or inv.get("pay_url", "")
    invoice_id = inv.get("invoice_id")

    await query.edit_message_text(
        f"✅ <b>Счёт создан!</b>\n"
        f"{_SEP}\n"
        f"▸ 1 хостинг-слот · {plan['days']} дней\n"
        f"▸ Сумма: <b>{plan['price']} {currency}</b>\n"
        f"{_SEP}\n"
        f"Нажмите кнопку ниже для оплаты.\n"
        f"После оплаты слот добавится автоматически.",
        parse_mode="HTML",
        reply_markup=payment_keyboard(pay_url, plan_key),
    )

    user_registry = context.bot_data["user_registry"]
    asyncio.create_task(
        poll_invoice(invoice_id, user_id, plan_key, context.bot, user_registry)
    )


async def ton_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.split(":", 1)[1]
    if plan_key not in PLANS:
        await query.answer("❌ Хостинг не найден.", show_alert=True)
        return

    wallet = os.getenv("TON_WALLET", "")
    if not wallet:
        await query.edit_message_text(
            "❌ TON-кошелёк не настроен.\nОбратитесь к администратору.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data=f"buy_plan:{plan_key}")]
            ]),
        )
        return

    plan = PLANS[plan_key]
    user_id = query.from_user.id
    amount_ton = await get_ton_amount(plan["price"])
    comment = make_ton_comment(user_id, plan_key)

    context.user_data["ton_payment"] = {
        "plan_key": plan_key,
        "amount_ton": amount_ton,
        "comment": comment,
    }

    await query.edit_message_text(
        f"💎 <b>Оплата через TON</b>\n"
        f"{_SEP}\n"
        f"▸ 1 хостинг-слот · {plan['days']} дней\n"
        f"▸ Сумма: <b>{amount_ton} TON</b>\n"
        f"{_SEP}\n"
        f"Нажмите кнопку ниже — TonKeeper откроется\n"
        f"с заполненными реквизитами.\n\n"
        f"Или вручную:\n"
        f"📋 Адрес: <code>{wallet}</code>\n"
        f"💬 Комментарий: <code>{comment}</code>\n\n"
        f"⚠️ <b>Комментарий обязателен!</b> Без него оплата не засчитается.\n\n"
        f"После отправки нажмите <b>✅ Я оплатил</b>.",
        parse_mode="HTML",
        reply_markup=ton_payment_keyboard(plan_key, wallet, amount_ton, comment),
    )

    user_registry = context.bot_data["user_registry"]
    asyncio.create_task(
        poll_ton_payment(user_id, plan_key, amount_ton, comment, context.bot, user_registry)
    )


async def ton_check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Проверяю транзакцию...")
    plan_key = query.data.split(":", 1)[1]
    user_id = query.from_user.id

    payment_data = context.user_data.get("ton_payment", {})
    amount_ton = payment_data.get("amount_ton")
    comment = payment_data.get("comment")

    wallet = os.getenv("TON_WALLET", "")
    if not wallet or not comment or not amount_ton:
        await query.edit_message_text(
            "❌ Данные платежа не найдены. Начните оплату заново.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="plans")]
            ]),
        )
        return

    found = await check_ton_payment_once(wallet, comment, amount_ton)
    if found:
        plan = PLANS[plan_key]
        user_registry = context.bot_data["user_registry"]
        from payments import _activate_plan
        await _activate_plan(user_id, plan_key, plan, context.bot, user_registry)
        await query.edit_message_text(
            f"✅ <b>Оплата подтверждена!</b>\n"
            f"{_SEP}\n"
            f"🖥 Добавлен 1 хостинг-слот\n"
            f"🤖 Теперь можно запустить ещё одного бота",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Мои боты", callback_data="my_bots")]
            ]),
        )
    else:
        await query.edit_message_text(
            f"❌ <b>Транзакция не найдена.</b>\n"
            f"{_SEP}\n"
            f"Убедитесь что отправили:\n"
            f"▸ Сумма: <b>{amount_ton} TON</b>\n"
            f"▸ Комментарий: <code>{comment}</code>\n"
            f"{_SEP}\n"
            f"Попробуйте снова через минуту.",
            parse_mode="HTML",
            reply_markup=ton_payment_keyboard(plan_key, wallet, amount_ton, comment),
        )
