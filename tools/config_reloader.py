from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable, Optional

from ..laser_config import LaserConfigResult, load_laser_director_config

HOT_RELOAD_DISABLE_ENV = "RBSS_DISABLE_HOT_RELOAD"


def _resolve_config_path(config_path: Optional[Path] = None) -> Path:
    if config_path is not None:
        return Path(config_path).expanduser().resolve()
    env_path = os.environ.get("RBSS_LASER_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "config" / "laser_director.json"


class ConfigReloader:
    def __init__(
        self,
        *,
        config_path: Optional[Path] = None,
        poll_interval: float = 1.0,
        on_reload: Optional[Callable[[LaserConfigResult], None]] = None,
    ) -> None:
        self._config_path = _resolve_config_path(config_path)
        self._poll_interval = max(0.05, float(poll_interval))
        self._on_reload = on_reload
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_mtime: Optional[float] = None

    @property
    def config_path(self) -> Path:
        return self._config_path

    def _mtime(self) -> Optional[float]:
        if not self._config_path.exists():
            return None
        try:
            return self._config_path.stat().st_mtime
        except OSError:
            return None

    def start(self) -> None:
        if os.environ.get(HOT_RELOAD_DISABLE_ENV) == "1":
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._last_mtime = self._mtime()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="config-reloader",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._poll_interval):
            current_mtime = self._mtime()
            if current_mtime == self._last_mtime:
                continue
            self._last_mtime = current_mtime
            result = load_laser_director_config(str(self._config_path))
            if self._on_reload is not None:
                self._on_reload(result)
