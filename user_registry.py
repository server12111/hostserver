import json
import os
import threading
from datetime import datetime

USERS_FILE = "users_registry.json"


class UserRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {"users": {}}
        self._load()

    def _load(self):
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, encoding="utf-8") as f:
                self._data = json.load(f)

    def _save(self):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def exists(self, user_id: int) -> bool:
        with self._lock:
            return str(user_id) in self._data["users"]

    def register(self, user_id: int, username: str = ""):
        with self._lock:
            key = str(user_id)
            if key not in self._data["users"]:
                self._data["users"][key] = {
                    "user_id": user_id,
                    "username": username or "",
                    "registered_at": datetime.now().isoformat(timespec="seconds"),
                    "balance": 0.0,
                    "subscription_until": None,
                    "max_bots": 0,
                    "plan": None,
                    "bots": [],
                }
                self._save()

    def get_user(self, user_id: int) -> dict | None:
        with self._lock:
            return self._data["users"].get(str(user_id))

    def update_user(self, user_id: int, **kwargs):
        with self._lock:
            u = self._data["users"].get(str(user_id))
            if u:
                u.update(kwargs)
                self._save()

    def add_bot_to_user(self, user_id: int, bot_name: str):
        with self._lock:
            u = self._data["users"].get(str(user_id))
            if u and bot_name not in u["bots"]:
                u["bots"].append(bot_name)
                self._save()

    def remove_bot_from_user(self, user_id: int, bot_name: str):
        with self._lock:
            u = self._data["users"].get(str(user_id))
            if u and bot_name in u["bots"]:
                u["bots"].remove(bot_name)
                self._save()

    def list_users(self) -> list[dict]:
        with self._lock:
            return list(self._data["users"].values())

    def can_add_bot(self, user_id: int) -> bool:
        u = self.get_user(user_id)
        if not u:
            return False
        sub = u.get("subscription_until")
        if not sub:
            return False
        if datetime.fromisoformat(sub) < datetime.now():
            return False
        return len(u.get("bots", [])) < u.get("max_bots", 0)

    def subscription_status(self, user_id: int) -> str:
        u = self.get_user(user_id)
        if not u:
            return "не зарегистрирован"
        sub = u.get("subscription_until")
        if not sub:
            return "📅 Хостинг не куплен"
        dt = datetime.fromisoformat(sub)
        if dt < datetime.now():
            return f"📅 Хостинг истёк {dt.strftime('%d.%m.%Y')}"
        return f"📅 Активен до {dt.strftime('%d.%m.%Y')}"
