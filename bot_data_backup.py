"""
Центральное хранилище резервных копий БД ботов на главном боте.

Копия БД каждого бота подтягивается с воркера после каждого успешного
деплоя/обновления и хранится тут отдельно от воркеров. Если воркер
пропадёт или будет пересоздан, при следующем деплое (в том числе на
другой воркер) эта копия заливается туда заново — бот не остаётся без
данных, даже если файловая система старого воркера исчезла целиком.
"""
import os

_DATA_DIR = os.getenv("DATA_DIR", "/app/data")
BACKUP_DIR = os.path.join(_DATA_DIR, "bot_data_backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


def _path(bot_name: str) -> str:
    return os.path.join(BACKUP_DIR, f"{bot_name}.zip")


def save(bot_name: str, zip_bytes: bytes):
    if not zip_bytes:
        return
    with open(_path(bot_name), "wb") as f:
        f.write(zip_bytes)


def load(bot_name: str) -> bytes:
    path = _path(bot_name)
    if not os.path.exists(path):
        return b""
    with open(path, "rb") as f:
        return f.read()


def delete(bot_name: str):
    path = _path(bot_name)
    if os.path.exists(path):
        os.remove(path)


async def push_to_worker(worker_client, worker: dict, bot_name: str):
    """Перед деплоем — заливает на воркер ранее сохранённую копию БД (если есть)."""
    backup = load(bot_name)
    if backup:
        await worker_client.upload_data_backup(worker, bot_name, backup)


async def pull_from_worker(worker_client, worker: dict, bot_name: str):
    """После успешного деплоя — забирает с воркера актуальную копию БД для хранения тут."""
    backup = await worker_client.download_data_backup(worker, bot_name)
    save(bot_name, backup)
