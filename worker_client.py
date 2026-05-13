import ssl

import aiohttp

_TIMEOUT_SHORT = aiohttp.ClientTimeout(total=10)
_TIMEOUT_LONG = aiohttp.ClientTimeout(total=300)
_TIMEOUT_DEPLOY = aiohttp.ClientTimeout(total=600)

# Отключаем проверку SSL — bothost.ru использует самоподписанные сертификаты
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _session() -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(ssl=_SSL)
    return aiohttp.ClientSession(connector=connector)


def _url(worker: dict, path: str) -> str:
    return f"{worker['url'].rstrip('/')}{path}"


def _headers(worker: dict) -> dict:
    return {"X-Worker-Secret": worker["secret"]}


async def health(worker: dict) -> dict:
    try:
        async with _session() as s:
            r = await s.get(_url(worker, "/health"), headers=_headers(worker),
                            timeout=aiohttp.ClientTimeout(total=20))
            if r.status == 200:
                return await r.json()
            return {"ok": False, "error": f"HTTP {r.status}"}
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}


async def deploy_zip(worker: dict, bot_name: str, zip_bytes: bytes,
                     display_name: str, owner_id: int) -> tuple[bool, str]:
    try:
        async with _session() as s:
            form = aiohttp.FormData()
            form.add_field("bot_name", bot_name)
            form.add_field("display_name", display_name)
            form.add_field("owner_id", str(owner_id))
            form.add_field("file", zip_bytes, filename=f"{bot_name}.zip",
                           content_type="application/zip")
            r = await s.post(_url(worker, "/deploy"), data=form,
                             headers=_headers(worker), timeout=_TIMEOUT_DEPLOY)
            data = await r.json()
            if data.get("ok"):
                return True, data.get("entry_point", "main.py")
            return False, data.get("error", "Ошибка деплоя")
    except Exception as e:
        return False, str(e) or type(e).__name__


async def deploy_git(worker: dict, bot_name: str, git_url: str,
                     display_name: str, owner_id: int) -> tuple[bool, str]:
    try:
        async with _session() as s:
            r = await s.post(_url(worker, "/deploy_git"),
                             json={"bot_name": bot_name, "git_url": git_url,
                                   "display_name": display_name, "owner_id": owner_id},
                             headers=_headers(worker), timeout=_TIMEOUT_DEPLOY)
            data = await r.json()
            if data.get("ok"):
                return True, data.get("entry_point", "main.py")
            return False, data.get("error", "Ошибка деплоя")
    except Exception as e:
        return False, str(e) or type(e).__name__


async def start(worker: dict, bot_name: str) -> tuple[bool, str]:
    try:
        async with _session() as s:
            r = await s.post(_url(worker, f"/start/{bot_name}"),
                             json={"public_url": worker.get("url", "").rstrip("/")},
                             headers=_headers(worker), timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data.get("ok", False), data.get("msg", "")
    except Exception as e:
        return False, str(e) or type(e).__name__


async def stop(worker: dict, bot_name: str) -> tuple[bool, str]:
    try:
        async with _session() as s:
            r = await s.post(_url(worker, f"/stop/{bot_name}"),
                             headers=_headers(worker), timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data.get("ok", False), data.get("msg", "")
    except Exception as e:
        return False, str(e) or type(e).__name__


async def delete(worker: dict, bot_name: str) -> tuple[bool, str]:
    try:
        async with _session() as s:
            r = await s.delete(_url(worker, f"/bots/{bot_name}"),
                               headers=_headers(worker), timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data.get("ok", False), data.get("msg", "Удалён")
    except Exception as e:
        return False, str(e) or type(e).__name__


async def logs(worker: dict, bot_name: str, n: int = 30) -> str:
    try:
        async with _session() as s:
            r = await s.get(_url(worker, f"/logs/{bot_name}"),
                            params={"n": n}, headers=_headers(worker),
                            timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data.get("logs", "(нет логов)")
    except Exception as e:
        return f"(ошибка связи с воркером: {str(e) or type(e).__name__})"


async def resources(worker: dict) -> list[dict]:
    try:
        async with _session() as s:
            r = await s.get(_url(worker, "/resources"),
                            headers=_headers(worker), timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data if isinstance(data, list) else data.get("resources", [])
    except Exception:
        return []


async def install(worker: dict, bot_name: str, packages: list[str]) -> tuple[bool, str]:
    try:
        async with _session() as s:
            r = await s.post(_url(worker, f"/install/{bot_name}"),
                             json={"packages": packages},
                             headers=_headers(worker), timeout=_TIMEOUT_LONG)
            data = await r.json()
            return data.get("ok", False), data.get("msg", "")
    except Exception as e:
        return False, str(e) or type(e).__name__


async def get_config(worker: dict, bot_name: str) -> str:
    try:
        async with _session() as s:
            r = await s.get(_url(worker, f"/config/{bot_name}"),
                            headers=_headers(worker), timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data.get("content", "")
    except Exception:
        return ""


async def save_config(worker: dict, bot_name: str, content: str) -> tuple[bool, str]:
    try:
        async with _session() as s:
            r = await s.post(_url(worker, f"/config/{bot_name}"),
                             json={"content": content},
                             headers=_headers(worker), timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data.get("ok", False), data.get("msg", "")
    except Exception as e:
        return False, str(e) or type(e).__name__


async def list_files(worker: dict, bot_name: str) -> list[str]:
    try:
        async with _session() as s:
            r = await s.get(_url(worker, f"/files/{bot_name}"),
                            headers=_headers(worker), timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data.get("files", [])
    except Exception:
        return []


async def poll_events(worker: dict) -> list[dict]:
    try:
        async with _session() as s:
            r = await s.get(_url(worker, "/events"),
                            headers=_headers(worker), timeout=_TIMEOUT_SHORT)
            data = await r.json()
            return data.get("events", [])
    except Exception:
        return []


async def download_file(worker: dict, bot_name: str, fname: str) -> bytes | None:
    try:
        async with _session() as s:
            r = await s.get(_url(worker, f"/files/{bot_name}/{fname}"),
                            headers=_headers(worker),
                            timeout=aiohttp.ClientTimeout(total=30))
            if r.status == 200:
                return await r.read()
    except Exception:
        pass
    return None
