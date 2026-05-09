import asyncio
import os
from datetime import datetime, timedelta

import aiohttp

CRYPTOBOT_API = "https://pay.crypt.bot/api"

PLANS = {
    "starter": {"name": "Starter", "bots": 1,  "price": 1.0, "days": 30},
    "basic":   {"name": "Basic",   "bots": 3,  "price": 2.0, "days": 30},
    "pro":     {"name": "Pro",     "bots": 10, "price": 5.0, "days": 30},
}

CURRENCIES = ["USDT", "TON", "BTC"]


async def create_invoice(amount: float, asset: str, payload: str, description: str) -> dict | None:
    token = os.getenv("CRYPTOBOT_TOKEN")
    if not token:
        return None
    async with aiohttp.ClientSession() as session:
        try:
            r = await session.post(
                f"{CRYPTOBOT_API}/createInvoice",
                headers={"Crypto-Pay-API-Token": token},
                json={
                    "currency_type": "crypto",
                    "asset": asset,
                    "amount": str(amount),
                    "payload": payload,
                    "description": description,
                    "expires_in": 3600,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            )
            data = await r.json()
            if data.get("ok"):
                return data["result"]
        except Exception:
            pass
    return None


async def get_invoice(invoice_id: int) -> dict | None:
    token = os.getenv("CRYPTOBOT_TOKEN")
    if not token:
        return None
    async with aiohttp.ClientSession() as session:
        try:
            r = await session.get(
                f"{CRYPTOBOT_API}/getInvoices",
                headers={"Crypto-Pay-API-Token": token},
                params={"invoice_ids": str(invoice_id)},
                timeout=aiohttp.ClientTimeout(total=15),
            )
            data = await r.json()
            if data.get("ok"):
                items = data["result"].get("items", [])
                return items[0] if items else None
        except Exception:
            pass
    return None


async def poll_invoice(
    invoice_id: int,
    user_id: int,
    plan_key: str,
    bot,
    user_registry,
    timeout: int = 3600,
):
    plan = PLANS[plan_key]
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(15)
        elapsed += 15
        inv = await get_invoice(invoice_id)
        if not inv:
            continue
        if inv.get("status") == "paid":
            u = user_registry.get_user(user_id)
            sub = u.get("subscription_until")
            if sub and datetime.fromisoformat(sub) > datetime.now():
                base = datetime.fromisoformat(sub)
            else:
                base = datetime.now()
            new_until = base + timedelta(days=plan["days"])
            user_registry.update_user(
                user_id,
                subscription_until=new_until.isoformat(timespec="seconds"),
                max_bots=max(u.get("max_bots", 0), plan["bots"]),
                plan=plan_key,
            )
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ Оплата получена!\n\n"
                        f"Тариф: <b>{plan['name']}</b>\n"
                        f"Ботов: до <b>{plan['bots']}</b>\n"
                        f"Подписка до: <b>{new_until.strftime('%d.%m.%Y')}</b>"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return
        if inv.get("status") == "expired":
            return
