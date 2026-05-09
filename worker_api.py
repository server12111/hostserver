"""
Worker API — запускається на кожному воркер-сервері.
python worker_api.py   або   uvicorn worker_api:app --host 0.0.0.0 --port 8000

Змінні оточення:
  WORKER_SECRET  — секретний ключ (обов'язково)
  WORKER_PORT    — порт (за замовчуванням 8000)
"""
import asyncio
import os
import shutil
import sys
import zipfile

from fastapi import FastAPI, Header, HTTPException, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

WORKER_SECRET = os.getenv("WORKER_SECRET", "")
BOTS_DIR = "bots"

app = FastAPI()

# ─── Ініціалізація менеджера ───────────────────────────────────────────────────
from registry import RegistryManager
from bot_manager import BotManager

_registry = RegistryManager()
_registry.restore_running_bots()
_manager = BotManager(_registry)


# ─── Auth helper ──────────────────────────────────────────────────────────────
def _check(secret: str):
    if WORKER_SECRET and secret != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


# ─── Утиліти ──────────────────────────────────────────────────────────────────
def _find_entry(bot_path: str) -> str | None:
    for name in ("main.py", "bot.py"):
        if os.path.exists(os.path.join(bot_path, name)):
            return name
    subdirs = [d for d in os.listdir(bot_path)
               if os.path.isdir(os.path.join(bot_path, d))
               and d not in ("venv", ".git")]
    if len(subdirs) == 1:
        sub = os.path.join(bot_path, subdirs[0])
        for name in ("main.py", "bot.py"):
            if os.path.exists(os.path.join(sub, name)):
                for item in os.listdir(sub):
                    src, dst = os.path.join(sub, item), os.path.join(bot_path, item)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                shutil.rmtree(sub, ignore_errors=True)
                return name
    return None


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
async def health(x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    try:
        import psutil
        ram_free = psutil.virtual_memory().available // (1024 * 1024)
    except Exception:
        ram_free = 0
    bots = _registry.list_bots()
    running = sum(1 for b in bots if _manager.is_running(b["name"]))
    return {"ok": True, "bots": len(bots), "running": running, "ram_free_mb": ram_free}


# ─── Deploy ZIP ───────────────────────────────────────────────────────────────
@app.post("/deploy")
async def deploy_zip(
    bot_name: str = Form(...),
    display_name: str = Form(...),
    owner_id: int = Form(...),
    file: UploadFile = File(...),
    x_worker_secret: str = Header(...),
):
    _check(x_worker_secret)
    bot_path = os.path.abspath(os.path.join(BOTS_DIR, bot_name))
    os.makedirs(bot_path, exist_ok=True)
    zip_temp = os.path.join(bot_path, "_upload.zip")
    try:
        content = await file.read()
        with open(zip_temp, "wb") as f:
            f.write(content)
        with zipfile.ZipFile(zip_temp) as zf:
            for member in zf.namelist():
                if ".." in member or os.path.isabs(member):
                    shutil.rmtree(bot_path, ignore_errors=True)
                    return JSONResponse({"ok": False, "error": f"Небезопасный путь: {member}"})
            zf.extractall(bot_path)
    except zipfile.BadZipFile:
        shutil.rmtree(bot_path, ignore_errors=True)
        return JSONResponse({"ok": False, "error": "Некорректный ZIP"})
    finally:
        if os.path.exists(zip_temp):
            os.remove(zip_temp)

    entry = _find_entry(bot_path)
    if not entry:
        shutil.rmtree(bot_path, ignore_errors=True)
        return JSONResponse({"ok": False, "error": "main.py или bot.py не найден"})

    _registry.add_bot(bot_name, bot_path, entry, owner_id=owner_id,
                      display_name=display_name, source="zip")
    ok, msg = await _manager.provision_bot(bot_name, bot_path)
    return JSONResponse({"ok": True, "entry_point": entry, "provision": ok, "provision_msg": msg})


# ─── Deploy Git ───────────────────────────────────────────────────────────────
class GitReq(BaseModel):
    bot_name: str
    git_url: str
    display_name: str
    owner_id: int


@app.post("/deploy_git")
async def deploy_git(req: GitReq, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)

    def _clone(url, path):
        try:
            import git
            git.Repo.clone_from(url, path, depth=1)
            return True, ""
        except Exception as e:
            return False, str(e)

    bot_path = os.path.abspath(os.path.join(BOTS_DIR, req.bot_name))
    ok, err = await asyncio.to_thread(_clone, req.git_url, bot_path)
    if not ok:
        shutil.rmtree(bot_path, ignore_errors=True)
        return JSONResponse({"ok": False, "error": err[:300]})

    entry = _find_entry(bot_path)
    if not entry:
        shutil.rmtree(bot_path, ignore_errors=True)
        return JSONResponse({"ok": False, "error": "main.py или bot.py не найден"})

    _registry.add_bot(req.bot_name, bot_path, entry, owner_id=req.owner_id,
                      display_name=req.display_name, source="git", git_url=req.git_url)
    ok2, msg = await _manager.provision_bot(req.bot_name, bot_path)
    return JSONResponse({"ok": True, "entry_point": entry, "provision": ok2, "provision_msg": msg})


# ─── Start / Stop / Delete ────────────────────────────────────────────────────
@app.post("/start/{bot_name}")
async def start_bot(bot_name: str, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    ok, msg = _manager.start_bot(bot_name)
    return {"ok": ok, "msg": msg}


@app.post("/stop/{bot_name}")
async def stop_bot(bot_name: str, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    ok, msg = _manager.stop_bot(bot_name)
    return {"ok": ok, "msg": msg}


@app.delete("/bots/{bot_name}")
async def delete_bot(bot_name: str, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    ok, msg = _manager.delete_bot(bot_name)
    return {"ok": ok, "msg": msg}


# ─── Logs ─────────────────────────────────────────────────────────────────────
@app.get("/logs/{bot_name}")
async def get_logs(bot_name: str, n: int = 30, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    return {"logs": _manager.get_logs(bot_name, n=n)}


# ─── Resources ────────────────────────────────────────────────────────────────
@app.get("/resources")
async def get_resources(x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    return {"resources": _manager.get_all_resources()}


# ─── Packages ─────────────────────────────────────────────────────────────────
class PkgReq(BaseModel):
    packages: list[str]


@app.post("/install/{bot_name}")
async def install_packages(bot_name: str, req: PkgReq, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    bot = _registry.get_bot(bot_name)
    if not bot:
        return {"ok": False, "msg": "Бот не найден"}
    ok, msg = await _manager.install_packages(bot["path"], req.packages)
    return {"ok": ok, "msg": msg}


# ─── Config ───────────────────────────────────────────────────────────────────
class CfgReq(BaseModel):
    content: str


@app.get("/config/{bot_name}")
async def get_config(bot_name: str, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    bot = _registry.get_bot(bot_name)
    if not bot:
        return {"content": ""}
    env_file = os.path.join(bot["path"], ".env")
    content = ""
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            content = f.read().strip()
    return {"content": content}


@app.post("/config/{bot_name}")
async def save_config(bot_name: str, req: CfgReq, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    bot = _registry.get_bot(bot_name)
    if not bot:
        return {"ok": False, "msg": "Бот не найден"}
    with open(os.path.join(bot["path"], ".env"), "w", encoding="utf-8") as f:
        f.write(req.content.strip() + "\n")
    return {"ok": True, "msg": "Сохранено"}


# ─── Files ────────────────────────────────────────────────────────────────────
_HIDDEN = {".env", ".git", "venv", "_upload.zip"}


@app.get("/files/{bot_name}")
async def list_files(bot_name: str, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    bot = _registry.get_bot(bot_name)
    if not bot:
        return {"files": []}
    files = []
    try:
        for fname in sorted(os.listdir(bot["path"])):
            if fname not in _HIDDEN and os.path.isfile(os.path.join(bot["path"], fname)):
                files.append(fname)
    except Exception:
        pass
    return {"files": files}


@app.get("/files/{bot_name}/{fname}")
async def download_file(bot_name: str, fname: str, x_worker_secret: str = Header(...)):
    _check(x_worker_secret)
    bot = _registry.get_bot(bot_name)
    if not bot:
        raise HTTPException(status_code=404)
    path = os.path.join(bot["path"], fname)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404)
    with open(path, "rb") as f:
        data = f.read()
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("WORKER_PORT", "8000"))
    print(f"Worker API running on port {port}. Secret: {'set' if WORKER_SECRET else 'NOT SET'}")
    uvicorn.run(app, host="0.0.0.0", port=port)
