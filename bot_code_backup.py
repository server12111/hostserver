"""
Центральное хранилище резервных копий КОДА ботов на главном боте.

В отличие от bot_data_backup.py (БД/.env), тут хранится копия исходного
кода бота — компактная, без .git/venv/__pycache__/логов и без дублирования
данных (те бэкапятся отдельно). Хранится только последняя версия на бота,
без истории — чтобы не занимало много места.

Нужна на случай, если код бота пропал с воркера (пересоздание контейнера)
и его нельзя быстро передеплоить из исходного Git/ZIP (например, у ZIP-бота
исходный архив нигде больше не хранится).
"""
import os

_DATA_DIR = os.getenv("DATA_DIR", "/app/data")
BACKUP_DIR = os.path.join(_DATA_DIR, "bot_code_backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


def _path(bot_name: str) -> str:
    return os.path.join(BACKUP_DIR, f"{bot_name}.zip")


def has_backup(bot_name: str) -> bool:
    return os.path.exists(_path(bot_name))


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


async def pull_from_worker(worker_client, worker: dict, bot_name: str):
    """После успешного деплоя — забирает с воркера актуальный код для хранения тут."""
    backup = await worker_client.download_code_backup(worker, bot_name)
    if backup:
        with open(_path(bot_name), "wb") as f:
            f.write(backup)
