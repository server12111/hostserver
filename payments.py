import asyncio
import os
from datetime import datetime, timedelta

import aiohttp

CRYPTOBOT_API = "https://pay.crypt.bot/api"
TONCENTER_API = "https://toncenter.com/api/v2"

PLANS = {
    "hosting_1":   {"name": "Хостинг 1 ГБ",   "bots": 1, "price": 2.0, "days": 30, "ram": "1 ГБ",   "disk": "5 ГБ"},
    "hosting_1_5": {"name": "Хостинг 1.5 ГБ", "bots": 1, "price": 3.0, "days": 30, "ram": "1.5 ГБ", "disk": "7 ГБ"},
    "hosting_2":   {"name": "Хостинг 2 ГБ",   "bots": 1, "price": 5.0, "days": 30, "ram": "2 ГБ",   "disk": "10 ГБ"},
}

CURRENCIES = ["USDT"]


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
            sent = [t for t in u.get("sent_triggers", []) if not t.startswith("wb_")]
            user_registry.update_user(
                user_id,
                subscription_until=new_until.isoformat(timespec="seconds"),
                max_bots=u.get("max_bots", 0) + plan["bots"],
                plan=plan_key,
                sent_triggers=sent,
            )
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ <b>Хостинг оплачен!</b>\n\n"
                        f"🤖 Добавлен 1 слот\n"
                        f"📅 Активен до: <b>{new_until.strftime('%d.%m.%Y')}</b>"
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            return
        if inv.get("status") == "expired":
            return


# ─── TON прямая оплата (TonCenter) ────────────────────────────────────────────

_ton_price_cache: dict = {"price": 3.0, "ts": 0.0}


async def fetch_ton_price_usd() -> float:
    """Получает актуальный курс TON/USD с CoinGecko. Кешируется на 10 минут."""
    import time
    now = time.time()
    if now - _ton_price_cache["ts"] < 600:
        return _ton_price_cache["price"]
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "the-open-network", "vs_currencies": "usd"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
            data = await r.json()
            price = float(data["the-open-network"]["usd"])
            _ton_price_cache["price"] = price
            _ton_price_cache["ts"] = now
            return price
    except Exception:
        return _ton_price_cache["price"]


async def get_ton_amount(usdt_price: float) -> float:
    """Конвертация USDT → TON по актуальному курсу CoinGecko."""
    ton_price = await fetch_ton_price_usd()
    return round(usdt_price / ton_price, 2)


def make_ton_comment(user_id: int, plan_key: str) -> str:
    return f"BH-{user_id}-{plan_key}"


async def get_ton_transactions(address: str, limit: int = 30) -> list:
    api_key = os.getenv("TONCENTER_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}
    async with aiohttp.ClientSession() as session:
        try:
            r = await session.get(
                f"{TONCENTER_API}/getTransactions",
                params={"address": address, "limit": limit},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            )
            data = await r.json()
            if data.get("ok"):
                return data.get("result", [])
        except Exception:
            pass
    return []


async def check_ton_payment_once(
    address: str, comment: str, amount_ton: float
) -> bool:
    """Проверяет последние транзакции — есть ли оплата с нужным комментарием и суммой."""
    txs = await get_ton_transactions(address, limit=30)
    for tx in txs:
        in_msg = tx.get("in_msg", {})
        tx_comment = in_msg.get("message", "").strip()
        tx_value_nano = int(in_msg.get("value", 0))
        tx_value_ton = tx_value_nano / 1_000_000_000
        if tx_comment == comment and tx_value_ton >= amount_ton * 0.99:
            return True
    return False


async def poll_ton_payment(
    user_id: int,
    plan_key: str,
    amount_ton: float,
    comment: str,
    bot,
    user_registry,
    timeout: int = 7200,
):
    wallet = os.getenv("TON_WALLET", "")
    if not wallet:
        return
    plan = PLANS[plan_key]
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(30)
        elapsed += 30
        found = await check_ton_payment_once(wallet, comment, amount_ton)
        if found:
            await _activate_plan(user_id, plan_key, plan, bot, user_registry)
            return


async def _activate_plan(user_id: int, plan_key: str, plan: dict, bot, user_registry):
    u = user_registry.get_user(user_id)
    if not u:
        return
    sub = u.get("subscription_until")
    base = datetime.fromisoformat(sub) if sub and datetime.fromisoformat(sub) > datetime.now() else datetime.now()
    new_until = base + timedelta(days=plan["days"])
    sent = [t for t in u.get("sent_triggers", []) if not t.startswith("wb_")]
    user_registry.update_user(
        user_id,
        subscription_until=new_until.isoformat(timespec="seconds"),
        max_bots=u.get("max_bots", 0) + plan["bots"],
        plan=plan_key,
        sent_triggers=sent,
    )
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"✅ <b>Хостинг оплачен!</b>\n\n"
                f"🤖 Добавлен 1 слот\n"
                f"📅 Активен до: <b>{new_until.strftime('%d.%m.%Y')}</b>"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass
