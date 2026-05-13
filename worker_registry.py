import json
import os
import threading
from datetime import datetime

_DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(_DATA_DIR, exist_ok=True)
WORKERS_FILE = os.path.join(_DATA_DIR, "workers_registry.json")


class WorkerRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {"workers": {}}
        self._load()

    def _load(self):
        if os.path.exists(WORKERS_FILE):
            with open(WORKERS_FILE, encoding="utf-8") as f:
                self._data = json.load(f)

    def _save(self):
        with open(WORKERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def add_worker(self, worker_id: str, url: str, secret: str, label: str = ""):
        with self._lock:
            self._data["workers"][worker_id] = {
                "id": worker_id,
                "url": url.rstrip("/"),
                "secret": secret,
                "label": label,
                "added_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._save()

    def remove_worker(self, worker_id: str):
        with self._lock:
            self._data["workers"].pop(worker_id, None)
            self._save()

    def get_worker(self, worker_id: str) -> dict | None:
        with self._lock:
            return self._data["workers"].get(worker_id)

    def list_workers(self) -> list[dict]:
        with self._lock:
            return list(self._data["workers"].values())

    def next_id(self) -> str:
        with self._lock:
            n = len(self._data["workers"]) + 1
            while f"w{n}" in self._data["workers"]:
                n += 1
            return f"w{n}"
