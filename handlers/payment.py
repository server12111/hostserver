import asyncio
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from keyboards import balance_keyboard, plans_keyboard, currency_keyboard, payment_keyboard, ton_payment_keyboard
from payments import (
    PLANS, create_invoice, poll_invoice,
    get_ton_amount, make_ton_comment, poll_ton_payment, check_ton_payment_once,
)


async def balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_registry = context.bot_data["user_registry"]
    u = user_registry.get_user(user_id)
    if not u:
        await query.edit_message_text("❌ Пользователь не найден.")
        return

    plan_name = PLANS.get(u.get("plan", ""), {}).get("name", "—") if u.get("plan") else "—"
    sub_status = user_registry.subscription_status(user_id)
    max_bots = u.get("max_bots", 0)
    bots_count = len(u.get("bots", []))

    await query.edit_message_text(
        f"💰 <b>Ваш аккаунт</b>\n\n"
        f"Тариф: <b>{plan_name}</b>\n"
        f"Подписка: <b>{sub_status}</b>\n"
        f"Ботов: <b>{bots_count} / {max_bots}</b>",
        parse_mode="HTML",
        reply_markup=balance_keyboard(),
    )


async def plans_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📦 <b>Выберите тариф:</b>\n\n"
    for key, plan in PLANS.items():
        text += f"• <b>{plan['name']}</b> — {plan['bots']} бот(ов), {plan['price']} USDT / {plan['days']} дней\n"
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=plans_keyboard()
    )


async def buy_plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_key = query.data.split(":", 1)[1]
    if plan_key not in PLANS:
        await query.answer("❌ Тариф не найден.", show_alert=True)
        return
    plan = PLANS[plan_key]
    context.user_data["selected_plan"] = plan_key
    await query.edit_message_text(
        f"💳 <b>{plan['name']}</b> — {plan['price']} USDT / {plan['days']} дней\n\n"
        "Выберите валюту для оплаты:",
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
        await query.answer("❌ Тариф не найден.", show_alert=True)
        return

    plan = PLANS[plan_key]
    user_id = query.from_user.id
    payload = f"{user_id}:{plan_key}"

    await query.edit_message_text(
        f"⏳ Создаю счёт на оплату {plan['price']} {currency}...",
        parse_mode="HTML",
    )

    inv = await create_invoice(
        amount=plan["price"],
        asset=currency,
        payload=payload,
        description=f"Bot Hosting — {plan['name']} ({plan['days']} дней)",
    )

    if not inv:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        await query.edit_message_text(
            "❌ Не удалось создать счёт. Убедитесь что CRYPTOBOT_TOKEN настроен правильно.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="plans")]
            ]),
        )
        return

    pay_url = inv.get("bot_invoice_url") or inv.get("pay_url", "")
    invoice_id = inv.get("invoice_id")

    await query.edit_message_text(
        f"✅ Счёт создан!\n\n"
        f"Тариф: <b>{plan['name']}</b>\n"
        f"Сумма: <b>{plan['price']} {currency}</b>\n"
        f"Срок: <b>{plan['days']} дней</b>\n\n"
        "Нажмите кнопку ниже для оплаты. После оплаты подписка активируется автоматически.",
        parse_mode="HTML",
        reply_markup=payment_keyboard(pay_url, plan_key),
    )

    user_registry = context.bot_data["user_registry"]
    asyncio.create_task(
        poll_invoice(invoice_id, user_id, plan_key, context.bot, user_registry)
    )


async def ton_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает реквизиты TON-оплаты напрямую через TonCenter."""
    query = update.callback_query
    await query.answer()
    plan_key = query.data.split(":", 1)[1]
    if plan_key not in PLANS:
        await query.answer("❌ Тариф не найден.", show_alert=True)
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
    amount_ton = get_ton_amount(plan["price"])
    comment = make_ton_comment(user_id, plan_key)

    context.user_data["ton_payment"] = {
        "plan_key": plan_key,
        "amount_ton": amount_ton,
        "comment": comment,
    }

    await query.edit_message_text(
        f"💎 <b>Оплата TON напрямую</b>\n\n"
        f"Тариф: <b>{plan['name']}</b>\n"
        f"Сумма: <b>{amount_ton} TON</b>\n\n"
        f"1️⃣ Откройте TonKeeper или любой TON-кошелёк\n"
        f"2️⃣ Отправьте ровно <b>{amount_ton} TON</b> на адрес:\n"
        f"<code>{wallet}</code>\n\n"
        f"3️⃣ В поле <b>Комментарий</b> обязательно укажите:\n"
        f"<code>{comment}</code>\n\n"
        f"⚠️ Без комментария оплата не будет засчитана!\n\n"
        f"После отправки нажмите <b>✅ Я оплатил</b>.",
        parse_mode="HTML",
        reply_markup=ton_payment_keyboard(plan_key),
    )

    user_registry = context.bot_data["user_registry"]
    asyncio.create_task(
        poll_ton_payment(user_id, plan_key, amount_ton, comment, context.bot, user_registry)
    )


async def ton_check_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручная проверка TON-оплаты по кнопке 'Я оплатил'."""
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
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"Тариф <b>{plan['name']}</b> активирован.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Мои боты", callback_data="my_bots")]
            ]),
        )
    else:
        await query.edit_message_text(
            "❌ <b>Транзакция не найдена.</b>\n\n"
            "Убедитесь что:\n"
            f"• Сумма: <b>{amount_ton} TON</b>\n"
            f"• Комментарий: <code>{comment}</code>\n\n"
            "Попробуйте снова через минуту.",
            parse_mode="HTML",
            reply_markup=ton_payment_keyboard(plan_key),
        )
