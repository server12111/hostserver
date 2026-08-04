"""
Создание страниц Политики конфиденциальности и Пользовательского соглашения
через Telegraph API (telegra.ph).

Разовый скрипт: `python telegraph_pages.py` создаёт аккаунт Telegraph (если ещё
не создан) и две страницы, затем печатает ACCESS_TOKEN и ссылки — их нужно
сохранить в .env (TELEGRAPH_ACCESS_TOKEN, PRIVACY_POLICY_URL, TERMS_URL).
Повторный запуск с уже сохранённым TELEGRAPH_ACCESS_TOKEN обновит содержимое
существующих страниц вместо создания новых (editPage), поэтому ссылки
остаются постоянными.
"""
import asyncio
import os

import aiohttp
from dotenv import load_dotenv

load_dotenv()

API = "https://api.telegra.ph"
AUTHOR_NAME = "FastHost"


def _p(*children) -> dict:
    return {"tag": "p", "children": list(children)}


def _h(text: str) -> dict:
    return {"tag": "h4", "children": [text]}


def _b(text: str) -> dict:
    return {"tag": "b", "children": [text]}


async def _call(session: aiohttp.ClientSession, method: str, **params) -> dict:
    async with session.post(f"{API}/{method}", json=params) as r:
        data = await r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegraph API error ({method}): {data}")
        return data["result"]


async def ensure_account(session: aiohttp.ClientSession) -> str:
    token = os.getenv("TELEGRAPH_ACCESS_TOKEN", "")
    if token:
        return token
    result = await _call(session, "createAccount", short_name=AUTHOR_NAME, author_name=AUTHOR_NAME)
    return result["access_token"]


PRIVACY_CONTENT = [
    _p(_b("Дата вступления в силу: 04.08.2026")),
    _p(
        "FastHost (далее — «Сервис», «мы») предоставляет пользователям возможность "
        "размещать и круглосуточно запускать собственных Telegram-ботов, написанных "
        "на Python, через загрузку ZIP-архива или подключение Git-репозитория. "
        "Настоящая Политика описывает, какие данные мы собираем и как их используем."
    ),
    _h("1. Какие данные мы собираем"),
    _p("— Telegram ID и username пользователя, взаимодействующего с ботом FastHost;"),
    _p(
        "— исходный код и файлы бота, загруженные вами через ZIP-архив или Git-репозиторий, "
        "а также токен вашего Telegram-бота, необходимый для его запуска;"
    ),
    _p(
        "— данные об оплате хостинга: адрес TON-кошелька и хэш транзакции при оплате "
        "криптовалютой, статус и срок действия подписки;"
    ),
    _p("— технические данные о работе вашего бота: логи, статус процесса, потребление ресурсов."),
    _h("2. Как мы используем данные"),
    _p(
        "Собранные данные используются исключительно для запуска и поддержания работы "
        "загруженных вами ботов, обработки оплаты хостинга, автоматического перезапуска "
        "при сбоях, уведомлений об истечении подписки и связи с вами по вопросам, "
        "связанным с использованием Сервиса."
    ),
    _h("3. Хранение и защита данных"),
    _p(
        "Каждый бот работает в изолированном окружении. Мы не передаём код, токены "
        "или данные вашего бота третьим лицам, за исключением случаев, когда это "
        "требуется для обработки платежа (платёжные/блокчейн-сервисы) или прямо "
        "предусмотрено законом."
    ),
    _p(
        "Мы предпринимаем разумные технические меры для сохранности данных вашего бота "
        "(включая его локальную базу данных) при обновлении кода, однако рекомендуем "
        "самостоятельно делать резервные копии критичных данных."
    ),
    _h("4. Права пользователя"),
    _p(
        "Вы можете в любой момент удалить своего бота из личного кабинета — при этом "
        "удаляются его код, токен и связанные данные с наших серверов. Вы можете "
        "запросить полное удаление своих данных из Сервиса, обратившись к администрации."
    ),
    _h("5. Изменения политики"),
    _p(
        "Мы можем время от времени обновлять эту Политику. Актуальная версия всегда "
        "доступна по постоянной ссылке на этой странице."
    ),
    _h("6. Контакты"),
    _p("По вопросам, связанным с обработкой данных, обращайтесь к администрации FastHost через бота."),
]

TERMS_CONTENT = [
    _p(_b("Дата вступления в силу: 04.08.2026")),
    _p(
        "Используя FastHost (далее — «Сервис»), вы соглашаетесь с условиями настоящего "
        "Пользовательского соглашения. Если вы не согласны с каким-либо из пунктов — "
        "пожалуйста, не пользуйтесь Сервисом."
    ),
    _h("1. Предмет соглашения"),
    _p(
        "Сервис предоставляет платный хостинг для Telegram-ботов пользователей: "
        "выделенные вычислительные ресурсы, изолированное окружение, автоматический "
        "перезапуск при сбоях и панель управления через Telegram-бота FastHost."
    ),
    _h("2. Тарифы и оплата"),
    _p(
        "Хостинг предоставляется на условиях предоплаты за выбранный период. Оплата "
        "принимается в криптовалюте через TON-кошелёк или иные подключённые платёжные "
        "методы. Внесённая оплата за уже активированный период хостинга не подлежит "
        "возврату, за исключением случаев, предусмотренных законодательством."
    ),
    _p(
        "По истечении оплаченного периода бот автоматически останавливается. Возобновление "
        "работы происходит после продления подписки."
    ),
    _h("3. Обязанности пользователя"),
    _p("Загружая бота на Сервис, вы подтверждаете, что:"),
    _p("— являетесь владельцем или уполномоченным пользователем загружаемого кода и токена бота;"),
    _p(
        "— ваш бот не используется для рассылки спама, мошенничества, распространения "
        "вредоносного ПО, нарушения Условий использования Telegram или законодательства;"
    ),
    _p("— вы несёте полную ответственность за поведение и содержимое своего бота."),
    _h("4. Ограничение ответственности"),
    _p(
        "Сервис прилагает разумные усилия для обеспечения непрерывной работы хостинга, "
        "но не гарантирует бесперебойную доступность 24/7 без единого сбоя. Мы не несём "
        "ответственности за действия ботов пользователей, а также за косвенные убытки, "
        "возникшие в результате использования или невозможности использования Сервиса."
    ),
    _h("5. Приостановка и удаление"),
    _p(
        "Мы вправе приостановить или прекратить хостинг бота, нарушающего пункт 3 "
        "настоящего Соглашения или Условия использования Telegram, без возврата "
        "внесённой оплаты."
    ),
    _h("6. Изменения условий"),
    _p(
        "Мы можем время от времени обновлять условия настоящего Соглашения. "
        "Актуальная версия всегда доступна по постоянной ссылке на этой странице."
    ),
    _h("7. Контакты"),
    _p("По всем вопросам обращайтесь к администрации FastHost через бота."),
]


async def _create_or_update(session: aiohttp.ClientSession, token: str, path: str, title: str, content: list) -> str:
    if path:
        result = await _call(
            session, "editPage", access_token=token, path=path,
            title=title, content=content, author_name=AUTHOR_NAME,
        )
    else:
        result = await _call(
            session, "createPage", access_token=token,
            title=title, content=content, author_name=AUTHOR_NAME, return_content=False,
        )
    return result["url"], result["path"]


def _write_env(updates: dict):
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    keys_left = dict(updates)
    for i, line in enumerate(lines):
        for key in list(keys_left):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={keys_left.pop(key)}"
    if keys_left:
        if lines and lines[-1].strip():
            lines.append("")
        for key, value in keys_left.items():
            lines.append(f"{key}={value}")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


async def main():
    async with aiohttp.ClientSession() as session:
        token = await ensure_account(session)
        privacy_path = os.getenv("PRIVACY_POLICY_URL", "").rsplit("/", 1)[-1]
        terms_path = os.getenv("TERMS_URL", "").rsplit("/", 1)[-1]

        privacy_url, privacy_path = await _create_or_update(
            session, token, privacy_path, "Политика конфиденциальности FastHost", PRIVACY_CONTENT
        )
        terms_url, terms_path = await _create_or_update(
            session, token, terms_path, "Пользовательское соглашение FastHost", TERMS_CONTENT
        )

        _write_env({
            "TELEGRAPH_ACCESS_TOKEN": token,
            "PRIVACY_POLICY_URL": privacy_url,
            "TERMS_URL": terms_url,
        })
        print("OK: .env updated with TELEGRAPH_ACCESS_TOKEN, PRIVACY_POLICY_URL, TERMS_URL")
        print(privacy_url)
        print(terms_url)


if __name__ == "__main__":
    asyncio.run(main())
