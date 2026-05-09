import asyncio
import os
import shutil
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass, field

from registry import RegistryManager


@dataclass
class BotProcess:
    process: subprocess.Popen | None = None
    log_buffer: deque = field(default_factory=lambda: deque(maxlen=200))
    reader_thread: threading.Thread | None = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class BotManager:
    def __init__(self, registry: RegistryManager):
        self._registry = registry
        self._processes: dict[str, BotProcess] = {}

    def is_running(self, name: str) -> bool:
        bp = self._processes.get(name)
        return bp is not None and bp.is_running()

    def get_logs(self, name: str, n: int = 30) -> str:
        bp = self._processes.get(name)
        if bp is None:
            return "(немає логів)"
        lines = list(bp.log_buffer)
        return "\n".join(lines[-n:]) if lines else "(порожньо)"

    @staticmethod
    def _venv_python(bot_path: str) -> str:
        scripts = "Scripts" if os.name == "nt" else "bin"
        exe = "python.exe" if os.name == "nt" else "python"
        return os.path.join(bot_path, "venv", scripts, exe)

    @staticmethod
    def _venv_pip(bot_path: str) -> str:
        scripts = "Scripts" if os.name == "nt" else "bin"
        exe = "pip.exe" if os.name == "nt" else "pip"
        return os.path.join(bot_path, "venv", scripts, exe)

    def _provision_blocking(self, name: str, bot_path: str) -> tuple[bool, str]:
        venv_dir = os.path.join(bot_path, "venv")
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", venv_dir],
                check=True, capture_output=True,
            )
            pip = self._venv_pip(bot_path)
            subprocess.run(
                [pip, "install", "--upgrade", "pip"],
                check=True, capture_output=True, timeout=120,
            )
            req_file = os.path.join(bot_path, "requirements.txt")
            if os.path.exists(req_file):
                subprocess.run(
                    [pip, "install", "-r", req_file],
                    check=True, capture_output=True, timeout=300,
                )
            self._registry.update_bot(name, provisioned=True)
            return True, "Залежності встановлено"
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode("utf-8", errors="replace")
            return False, f"Помилка при встановленні: {err[:500]}"
        except Exception as e:
            return False, str(e)

    async def provision_bot(self, name: str, bot_path: str) -> tuple[bool, str]:
        return await asyncio.to_thread(self._provision_blocking, name, bot_path)

    def _install_packages_blocking(self, bot_path: str, packages: list[str]) -> tuple[bool, str]:
        pip = self._venv_pip(bot_path)
        if not os.path.exists(pip):
            return False, "venv не знайдено — спочатку перевстановіть бота"
        try:
            result = subprocess.run(
                [pip, "install"] + packages,
                capture_output=True, timeout=300,
            )
            out = result.stdout.decode("utf-8", errors="replace")
            err = result.stderr.decode("utf-8", errors="replace")
            if result.returncode != 0:
                return False, (err or out)[:600]
            return True, f"Встановлено: {', '.join(packages)}"
        except Exception as e:
            return False, str(e)

    async def install_packages(self, bot_path: str, packages: list[str]) -> tuple[bool, str]:
        return await asyncio.to_thread(self._install_packages_blocking, bot_path, packages)

    def start_bot(self, name: str) -> tuple[bool, str]:
        if self.is_running(name):
            return False, "Бот вже запущений"
        bot = self._registry.get_bot(name)
        if not bot:
            return False, "Бот не знайдений"
        bot_path = bot["path"]
        entry = bot["entry_point"]
        python_exe = self._venv_python(bot_path)
        if not os.path.exists(python_exe):
            python_exe = sys.executable
        entry_abs = os.path.join(bot_path, entry)
        try:
            env = os.environ.copy()
            env_file = os.path.join(bot_path, ".env")
            if os.path.exists(env_file):
                with open(env_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, _, v = line.partition("=")
                            env[k.strip()] = v.strip()
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                [python_exe, entry_abs],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=bot_path,
                env=env,
                **kwargs,
            )
            bp = BotProcess(process=process)
            self._processes[name] = bp
            self._start_log_reader(bp)
            self._registry.update_bot(name, status="running", pid=process.pid)
            return True, f"Бот запущено (PID {process.pid})"
        except Exception as e:
            return False, str(e)

    def _start_log_reader(self, bp: BotProcess):
        def reader():
            for raw in iter(bp.process.stdout.readline, b""):
                bp.log_buffer.append(raw.decode("utf-8", errors="replace").rstrip())

        bp.reader_thread = threading.Thread(target=reader, daemon=True)
        bp.reader_thread.start()

    def stop_bot(self, name: str) -> tuple[bool, str]:
        bp = self._processes.get(name)
        if bp is None or not bp.is_running():
            self._registry.update_bot(name, status="stopped", pid=None)
            return False, "Бот не запущений"
        try:
            bp.process.terminate()
            try:
                bp.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                bp.process.kill()
            self._registry.update_bot(name, status="stopped", pid=None)
            return True, "Бот зупинено"
        except Exception as e:
            return False, str(e)

    def delete_bot(self, name: str) -> tuple[bool, str]:
        self.stop_bot(name)
        self._processes.pop(name, None)
        bot = self._registry.get_bot(name)
        if bot:
            bot_path = bot["path"]
            try:
                if os.path.exists(bot_path):
                    shutil.rmtree(bot_path)
            except Exception as e:
                return False, f"Помилка видалення файлів: {e}"
        self._registry.remove_bot(name)
        return True, "Бот видалено"

    def stop_all(self):
        for name in list(self._processes.keys()):
            self.stop_bot(name)
